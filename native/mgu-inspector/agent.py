#!/usr/bin/env python3
"""Pairing + fixed inventory API on loopback, reached through an owner's tailnet."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import struct
import time
from inspector import Inventory, OPERATIONS

PORT = 5891
APP_ID = 'shjeladze_inspector'


async def bounded_read(reader):
    data = bytearray()
    while True:
        chunk = await reader.read(4096)
        if not chunk: return bytes(data)
        data.extend(chunk)
        if len(data) > 65536: raise ValueError('Registry response too large')


class Access:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.code_hash = None
        self.code_until = 0
        self.token_hash = None
        self.token_until = 0
        self.failures = 0

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode('ascii')).digest()

    def revoke(self):
        self.code_hash = self.token_hash = None
        self.code_until = self.token_until = 0

    def begin(self):
        self.revoke()
        self.failures = 0
        code = ''.join(str(secrets.randbelow(10)) for _ in range(12))
        self.code_hash, self.code_until = self.digest(code), self.clock() + 120
        return {'code': code, 'expiresIn': 120}

    def pair(self, code):
        if (not isinstance(code, str) or len(code) != 12 or not code.isascii() or not code.isdigit()
                or self.code_hash is None or self.clock() >= self.code_until
                or not hmac.compare_digest(self.digest(code), self.code_hash)):
            self.failures += 1
            if self.failures >= 5:
                self.code_hash = None
            raise ValueError('Pairing failed; create a fresh code on the car')
        token = secrets.token_hex(32)
        self.code_hash = None
        self.token_hash, self.token_until = self.digest(token), self.clock() + 900
        return {'token': token, 'expiresIn': 900}

    def authorized(self, token):
        return (isinstance(token, str) and len(token) == 64 and token.isascii()
                and self.token_hash is not None and self.clock() < self.token_until
                and hmac.compare_digest(self.digest(token), self.token_hash))

    def status(self):
        return {'pairingActive': self.code_hash is not None and self.clock() < self.code_until,
                'connected': self.token_hash is not None and self.clock() < self.token_until,
                'sessionSeconds': max(0, int(self.token_until - self.clock())) if self.token_hash else 0,
                'port': PORT, 'readOnly': True}


def registry_uid(value):
    if not isinstance(value, dict) or not isinstance(value.get('components'), list):
        return None
    entries = [x for x in value['components'] if isinstance(x, dict) and x.get('kind') == 'app' and x.get('id') == APP_ID]
    if len(entries) != 1:
        return None
    uid = entries[0].get('uid')
    return uid if type(uid) is int and 10000 <= uid < 2 ** 31 else None


class Agent:
    def __init__(self, inventory=None, access=None):
        self.inventory = inventory or Inventory()
        self.access = access or Access()
        self.uid = None
        self.uid_until = 0
        self.slots = 0

    def registered(self):
        return self.uid is not None and time.monotonic() < self.uid_until

    async def registry(self):
        while True:
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    '/bin/sh', '/var/opt/mgu-deploy/mgu-deploy.sh', 'status', '--json',
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
                raw = await asyncio.wait_for(bounded_read(proc.stdout), 2)
                if len(raw) > 65536 or await asyncio.wait_for(proc.wait(), 1):
                    raise ValueError('Registry unavailable')
                new = registry_uid(json.loads(raw))
                if new != self.uid:
                    self.access.revoke()
                self.uid, self.uid_until = new, time.monotonic() + 15
            except (OSError, ValueError, asyncio.TimeoutError):
                self.uid = None
                self.access.revoke()
            finally:
                if proc:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if proc.stdout:
                        # Drain the finite kernel/asyncio pipe buffer after killing the entire group.
                        await asyncio.wait_for(proc.stdout.read(), 2)
                    await asyncio.wait_for(proc.wait(), 2)
            await asyncio.sleep(5)

    def local(self, uid, request):
        if not self.registered() or uid != self.uid:
            raise ValueError('Inspector app registration unavailable')
        if not isinstance(request, dict) or set(request) != {'op'}:
            raise ValueError('Invalid local operation')
        if request['op'] == 'begin':
            return self.access.begin()
        if request['op'] == 'revoke':
            self.access.revoke()
            return self.access.status()
        if request['op'] == 'status':
            return self.access.status()
        raise ValueError('Unknown local operation')

    def remote(self, path, headers, request):
        if not self.registered():
            raise ValueError('Inspector app not registered')
        if not isinstance(request, dict):
            raise ValueError('Expected object')
        if path == '/v1/pair' and set(request) == {'code'}:
            return self.access.pair(request['code'])
        token = headers.get('authorization', '')
        if not token.startswith('Bearer ') or not self.access.authorized(token[7:]):
            raise ValueError('Session unavailable; pair again')
        if path == '/v1/inventory' and set(request) == {'operation'} and request['operation'] in OPERATIONS:
            value = self.inventory.collect(request['operation'])
            value['networkListener'] = True
            value['transport'] = 'private-tailnet-to-loopback:5891'
            return value
        if path == '/v1/revoke' and not request:
            self.access.revoke()
            return {'revoked': True}
        raise ValueError('Unknown operation')

    async def unix(self, reader, writer):
        try:
            _, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            raw = await asyncio.wait_for(reader.readline(), 2)
            if len(raw) > 1024 or not raw.endswith(b'\n'):
                raise ValueError('Invalid request')
            value = self.local(uid, json.loads(raw))
        except (OSError, ValueError, asyncio.TimeoutError):
            value = {'error': 'Local request refused'}
        try:
            writer.write(json.dumps(value).encode() + b'\n')
            await asyncio.wait_for(writer.drain(), 2)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()

    async def http(self, reader, writer):
        if self.slots >= 8:
            writer.close()
            return
        self.slots += 1
        try:
            raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)
            if len(raw) > 8192:
                raise ValueError('Headers too large')
            lines = raw.decode('ascii').split('\r\n')
            method, path, protocol = lines[0].split(' ')
            if method != 'POST' or protocol != 'HTTP/1.1' or len(path) > 64:
                raise ValueError('Invalid request line')
            headers = {}
            for line in lines[1:-2]:
                name, sep, value = line.partition(':')
                name = name.lower()
                if not sep or name in headers or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz-' for c in name):
                    raise ValueError('Invalid header')
                headers[name] = value.strip()
            if ('origin' in headers or 'transfer-encoding' in headers or not headers.get('host')
                    or headers.get('content-type') != 'application/json'):
                raise ValueError('Unsupported request')
            length = headers.get('content-length', '')
            if not length.isdigit() or not 0 < int(length) <= 1024:
                raise ValueError('Invalid length')
            body = await asyncio.wait_for(reader.readexactly(int(length)), 3)
            value = self.remote(path, headers, json.loads(body))
            status = '200 OK'
        except (OSError, ValueError, TypeError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            status, value = '403 Forbidden', {'error': 'Request refused; check pairing and operation'}
        try:
            body = json.dumps(value, ensure_ascii=True).encode()
            if len(body) > 128 * 1024:
                status, body = '413 Content Too Large', b'{}'
            writer.write(('HTTP/1.1 ' + status + '\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: ' + str(len(body)) + '\r\n\r\n').encode() + body)
            await asyncio.wait_for(writer.drain(), 3)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            self.slots -= 1


async def serve():
    import grp
    agent = Agent()
    path = Path('/run/mgu-inspector/control.sock')
    # RuntimeDirectory is created by systemd, never by a network request.
    unix = await asyncio.start_unix_server(agent.unix, path=str(path), limit=1025)
    os.chown(path, 0, grp.getgrnam('tm_oap_app').gr_gid)
    os.chmod(path, 0o660)
    http = await asyncio.start_server(agent.http, '127.0.0.1', PORT, limit=8193)
    registry = asyncio.create_task(agent.registry())
    stop = asyncio.Event()
    registry.add_done_callback(lambda _: stop.set())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with unix, http:
            await stop.wait()
    finally:
        agent.access.revoke()
        registry.cancel()
        await asyncio.gather(registry, return_exceptions=True)
        path.unlink(missing_ok=True)


if __name__ == '__main__':
    asyncio.run(serve())
