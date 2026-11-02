#!/usr/bin/env python3
"""JLTube privileged safety broker. No network listener; no shell execution."""
# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
try:
    import grp
except ImportError:  # Offline policy tests also run on Windows; the service is Linux-only.
    grp = None
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import sys
import time
from urllib.parse import urlsplit

VERSION = '0.3.0'
INSTALL = Path('/var/opt/jltube-player/current')
RUNTIME = Path('/run/jltube-player')
CONFIG = Path('/var/opt/jltube-player/config.json')
SIGNAL_DIR = Path('/run/jltube-vehicle')
VIDEO = Path('/dev/shm/mgu-video-jltube')
WORKER_UID = 3921
WIDTH, HEIGHT = 640, 360
FRAME_SIZE = WIDTH * HEIGHT * 3 // 2


def trusted_json(path, limit=16384, expected_uid=0):
    """Reject symlinks, mutable parent directories and untrusted owners."""
    path = Path(path)
    for parent in path.parents:
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != expected_uid or s.st_mode & 0o022:
            raise ValueError('Untrusted parent directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != expected_uid or s.st_mode & 0o022 or s.st_size > limit:
            raise ValueError('Untrusted or oversized state file')
        raw = os.read(fd, limit + 1)
        if len(raw) > limit:
            raise ValueError('Oversized state file')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('Expected object')
        return value
    finally:
        os.close(fd)


def parked(sample, now, boot_id):
    """No tolerance for motion; missing/ambiguous values always lock."""
    if not isinstance(sample, dict) or sample.get('schema') != 1 or sample.get('boot_id') != boot_id:
        return False
    stamp, speed = sample.get('monotonic'), sample.get('speed_mps')
    if type(stamp) not in (int, float) or type(speed) not in (int, float):
        return False
    return (math.isfinite(stamp) and math.isfinite(speed) and 0 <= now - stamp <= 0.5
            and speed == 0 and sample.get('gear') == 'P' and sample.get('valid') is True)


def validated_url(value, mode):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) <= 32 for c in value):
        raise ValueError('Invalid URL')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only HTTPS URLs without credentials on port 443 are supported')
    host = p.hostname.lower()
    if host.endswith('.') or host == 'localhost' or host.endswith(('.local', '.localhost')):
        raise ValueError('Local addresses are blocked')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP literals are blocked')
    if mode == 'youtube':
        if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
            raise ValueError('Use a YouTube video URL')
    elif mode != 'web':
        raise ValueError('Unsupported mode')
    return value


class FrameFile:
    """mgu-render MGVF v1, three I420 slots, little endian."""
    def __init__(self, path=VIDEO, width=WIDTH, height=HEIGHT):
        if width % 2 or height % 2 or not 16 <= width <= 2048 or not 16 <= height <= 2048:
            raise ValueError('Invalid video dimensions')
        self.path, self.size = Path(path), width * height * 3 // 2
        self.fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        os.fchmod(self.fd, 0o644)
        self.seq, self.slot = 0, 0
        os.ftruncate(self.fd, 64 + 3 * self.size)
        os.pwrite(self.fd, struct.pack('<16I', 0x4656474d, 1, width, height, 0, 0, 3, 0, 0, *([0] * 7)), 0)

    def write(self, frame):
        if len(frame) != self.size:
            raise ValueError('Incomplete I420 frame')
        self.slot = (self.slot + 1) % 3
        os.pwrite(self.fd, frame, 64 + self.slot * self.size)
        self.seq = (self.seq + 1) & 0xffffffff
        os.pwrite(self.fd, struct.pack('<I', self.slot), 20)
        os.pwrite(self.fd, struct.pack('<I', self.seq), 16)

    def black(self):
        self.write(bytes([16]) * (self.size * 2 // 3) + bytes([128]) * (self.size // 3))

    def close(self):
        self.black()
        os.close(self.fd)
        self.path.unlink(missing_ok=True)


def checked_binaries(config, root=INSTALL):
    """No auto-update/downloader. Only reviewed local binaries by hash."""
    lock = config.get('binaries', {})
    result = {}
    versions = {'yt-dlp': '2026.10.26', 'ffmpeg': '9.0.2', 'qjs': '2026-06-04'}
    for name, version in versions.items():
        item = lock.get(name, {})
        if item.get('version') != version or len(item.get('sha256', '')) != 64:
            raise ValueError('Missing pinned runtime: ' + name)
        path = root / 'bin' / name
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError('Untrusted runtime: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Runtime hash mismatch: ' + name)
        result[name] = str(path)
    return result


async def bounded_read(stream, limit):
    chunks, size = [], 0
    while True:
        data = await stream.read(min(8192, limit + 1 - size))
        if not data:
            return b''.join(chunks)
        chunks.append(data)
        size += len(data)
        if size > limit:
            raise ValueError('Resolver output limit exceeded')


class Broker:
    def __init__(self, config, sample_reader=None, clock=time.monotonic, frame_factory=FrameFile, boot_id=None):
        self.config, self.clock = config, clock
        self.boot_id = boot_id or Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.sample_reader = sample_reader or (lambda: trusted_json(SIGNAL_DIR / 'state.json'))
        self.frame_factory = frame_factory
        self.task, self.process, self.frames = None, None, None
        self.state, self.reason = 'locked', 'Vehicle safety adapter not validated'
        self.last_client = 0
        self.dns_updated = 0
        self.control_lock = asyncio.Lock()

    def allowed(self):
        if self.config.get('vehicle_adapter_validated') is not True:
            return False
        try:
            return parked(self.sample_reader(), self.clock(), self.boot_id)
        except (OSError, ValueError, TypeError):
            return False

    def status(self):
        allowed = self.allowed()
        return {'version': VERSION, 'allowed': allowed, 'state': self.state if allowed else 'locked',
                'reason': self.reason if allowed else 'Locked: no fresh validated Park + zero-speed signal',
                'browser': 'unavailable', 'audio': 'unvalidated; disabled',
                'video': '/dev/shm/mgu-video-jltube' if allowed and self.state == 'playing' else None}

    async def stop(self, reason='Stopped'):
        task, self.task = self.task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
        if self.process:
            await self.kill_process(self.process)
            self.process = None
        if self.frames:
            self.frames.close()
            self.frames = None
        self.state, self.reason = 'idle', reason

    async def kill_process(self, proc):
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await proc.wait()

    async def spawn(self, *args):
        # Launcher drops root before loading any network-facing executable.
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(INSTALL / 'player.py'), 'worker', *args,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
            env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C',
                 'SSL_CERT_FILE': '/var/opt/mgu-python/current/ssl/cacert.pem'})
        return self.process

    async def play(self, url, binaries):
        try:
            self.state, self.reason = 'resolving', 'Resolving YouTube video'
            proc = await self.spawn(binaries['yt-dlp'], '--ignore-config', '--no-playlist',
                                    '--no-cache-dir', '--no-progress', '--no-warnings',
                                    '--js-runtimes', 'quickjs:' + binaries['qjs'],
                                    '-f', 'bestvideo[height<=360][vcodec^=avc1]/best[height<=360]',
                                    '--get-url', '--', url)
            raw = await asyncio.wait_for(bounded_read(proc.stdout, 8192), timeout=30)
            code = await proc.wait()
            if code != 0:
                raise ValueError('YouTube resolver failed; consult runtime versions/connectivity')
            urls = raw.decode('utf8').splitlines()
            if len(urls) != 1:
                raise ValueError('Expected exactly one media stream')
            media = validated_url(urls[0], 'web')
            host = urlsplit(media).hostname
            if not host.endswith('.googlevideo.com'):
                raise ValueError('Resolver returned an unexpected media host')
            if not self.allowed():
                raise ValueError('Vehicle locked during resolution')
            self.frames = self.frame_factory()
            self.frames.black()
            proc = await self.spawn(binaries['ffmpeg'], '-nostdin', '-hide_banner', '-loglevel', 'error',
                                    '-protocol_whitelist', 'https,tls,tcp', '-rw_timeout', '10000000', '-re',
                                    '-tls_verify', '1', '-ca_file', '/var/opt/mgu-python/current/ssl/cacert.pem',
                                    '-i', media, '-an', '-sn', '-dn', '-vf',
                                    'scale=640:360:force_original_aspect_ratio=decrease:out_color_matrix=bt601:out_range=tv,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1',
                                    '-r', '24', '-pix_fmt', 'yuv420p', '-f', 'rawvideo', 'pipe:1')
            self.state, self.reason = 'playing', 'Playing video (audio disabled)'
            while self.allowed():
                frame = await asyncio.wait_for(proc.stdout.readexactly(FRAME_SIZE), timeout=10)
                if not self.allowed():
                    break
                self.frames.write(frame)
        except asyncio.CancelledError:
            raise
        except asyncio.IncompleteReadError:
            self.reason = 'Playback ended'
        except Exception as exc:
            # Never log URLs, tokens, resolver stdout or subprocess arguments.
            self.reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        finally:
            if self.process:
                await self.kill_process(self.process)
                self.process = None
            if self.frames:
                self.frames.close()
                self.frames = None
            self.state = 'idle'

    async def dispatch(self, message, uid):
        if not isinstance(message, dict):
            raise ValueError('Expected JSON object')
        if (type(self.config.get('app_uid')) is not int or not 10000 <= self.config['app_uid'] < 65534
                or uid != self.config['app_uid']):
            raise ValueError('Configure the installed JLTube app UID before use')
        op = message.get('op')
        if op == 'status':
            self.last_client = self.clock()
            return self.status()
        if op == 'stop':
            await self.stop()
            return self.status()
        if op != 'open':
            raise ValueError('Unsupported operation')
        if not self.allowed():
            raise ValueError('Locked: parked-state verification required')
        mode = message.get('mode')
        url = validated_url(message.get('url'), mode)
        if mode == 'web':
            raise ValueError('Full browser engine is not validated or included in this development build')
        # Hashing large runtime files must never block the watchdog while media is running.
        await self.stop()
        binaries = checked_binaries(self.config)
        if not self.dns_updated or self.clock() - self.dns_updated > 3:
            raise ValueError('mgu-uplink DNS lease unavailable')
        if not self.allowed():
            raise ValueError('Locked during runtime verification')
        self.last_client = self.clock()
        self.task = asyncio.create_task(self.play(url, binaries))
        return {'ok': True}

    async def watchdog(self):
        while True:
            async with self.control_lock:
                if self.task and (not self.allowed() or self.clock() - self.last_client > 1.5):
                    await self.stop('Locked: vehicle signal or app heartbeat lost')
            self.update_dns()
            await asyncio.sleep(0.1)

    def update_dns(self):
        try:
            # Uplink owns this file. Only its DNS is used; never modify the host resolver.
            lease = trusted_json('/run/mgu-uplink/lease.json')
            servers = [str(ipaddress.ip_address(x)) for x in lease.get('dns', [])][:3]
            if not servers:
                return
            with (RUNTIME / 'resolv.conf').open('w') as f:
                f.write(''.join('nameserver ' + x + '\n' for x in servers))
            self.dns_updated = self.clock()
        except (OSError, ValueError, TypeError):
            if self.dns_updated and self.clock() - self.dns_updated > 3:
                self.dns_updated = 0


async def serve(config):
    broker = Broker(config)
    async def client(reader, writer):
        try:
            creds = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _, uid, _ = struct.unpack('3i', creds)
            raw = await asyncio.wait_for(reader.readline(), 1)
            if len(raw) > 4096 or not raw.endswith(b'\n'):
                raise ValueError('Malformed request')
            async with broker.control_lock:
                response = await broker.dispatch(json.loads(raw), uid)
        except Exception as exc:
            response = {'ok': False, 'error': str(exc) if isinstance(exc, ValueError) else 'Request failed'}
        writer.write(json.dumps(response, allow_nan=False).encode() + b'\n')
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    sock = RUNTIME / 'control.sock'
    sock.unlink(missing_ok=True)
    server = await asyncio.start_unix_server(client, str(sock), limit=4097)
    os.chown(sock, 0, grp.getgrnam('tm_oap_app').gr_gid)
    os.chmod(sock, 0o660)
    watchdog = asyncio.create_task(broker.watchdog())
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        async with server:
            await stop_event.wait()
    finally:
        watchdog.cancel()
        await broker.stop('Service stopped')
        sock.unlink(missing_ok=True)


def prepare():
    import pwd
    try:
        pwd.getpwuid(WORKER_UID)
    except KeyError:
        pass
    else:
        raise ValueError('Worker UID 3921 is already assigned to an account; do not start')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            uid_line = next(line for line in path.read_text().splitlines() if line.startswith('Uid:'))
            if WORKER_UID in [int(x) for x in uid_line.split()[1:]]:
                raise ValueError('Worker UID 3921 is already in use; inspect before installing')
        except (FileNotFoundError, ProcessLookupError):
            pass
    RUNTIME.mkdir(mode=0o755, exist_ok=True)
    s = RUNTIME.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
        raise ValueError('Untrusted runtime directory')
    fd = os.open(RUNTIME / 'resolv.conf', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    os.write(fd, b'nameserver 127.0.0.1\n')
    os.close(fd)
    # O_EXCL refuses leftover frame files; remove only our regular root-owned file at startup.
    try:
        s = VIDEO.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0:
            raise ValueError('Untrusted existing video file')
        VIDEO.unlink()
    except FileNotFoundError:
        pass


def worker(argv):
    # Only this root-owned script can choose the three fixed executable paths.
    if not argv or Path(argv[0]) not in {INSTALL / 'bin' / n for n in ('yt-dlp', 'ffmpeg', 'qjs')}:
        raise ValueError('Invalid worker executable')
    os.setgroups([])
    os.setgid(WORKER_UID)
    os.setuid(WORKER_UID)
    os.umask(0o077)
    if Path(argv[0]).name == 'yt-dlp':
        # Small official zipimport executable, with bundled EJS, using mgu-python.
        os.execv(sys.executable, [sys.executable] + argv)
    os.execv(argv[0], argv)


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'serve'
    if command == 'worker':
        worker(sys.argv[2:])
    elif command == 'prepare':
        prepare()
    elif command == 'serve':
        try:
            config = trusted_json(CONFIG)
        except FileNotFoundError:
            config = {}
        asyncio.run(serve(config))
    elif command == 'diagnostics':
        config = trusted_json(CONFIG) if CONFIG.exists() else {}
        report = {'version': VERSION, 'configPresent': CONFIG.exists(), 'socket': (RUNTIME / 'control.sock').exists(),
                  'vehicleAdapterValidated': config.get('vehicle_adapter_validated') is True,
                  'browser': 'not implemented', 'audio': 'disabled', 'workerUID': WORKER_UID}
        try:
            checked_binaries(config)
            report['runtimeHashes'] = 'verified'
        except (ValueError, OSError) as exc:
            report['runtimeHashes'] = str(exc)
        print(json.dumps(report, indent=2))
    else:
        raise SystemExit('Unknown command')
