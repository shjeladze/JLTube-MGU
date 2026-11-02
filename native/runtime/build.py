#!/usr/bin/env python3
"""Build static, baseline-x86-64 media candidates on Linux; never runs on the vehicle."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LOCK = json.loads((Path(__file__).parent / 'sources.lock.json').read_text())
WORK = ROOT / 'work/runtime-build'
OUT = ROOT / 'dist/runtime'
PREFIX = WORK / 'prefix'


def run(argv, cwd=None, env=None):
    print('+', shlex.join([str(x) for x in argv]), flush=True)
    subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=True, timeout=900)


def download(url, target, digest):
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return
    with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as dest:
        shutil.copyfileobj(response, dest)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('Download hash mismatch: ' + target.name)


def source(name, item):
    folder = WORK / name
    if not folder.exists():
        folder.mkdir()
        run(['git', 'init', folder])
        run(['git', '-C', folder, 'fetch', '--depth=1', item['repo'], item['commit']])
        run(['git', '-C', folder, 'checkout', '--detach', 'FETCH_HEAD'])
    head = subprocess.check_output(['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True).strip()
    if head != item['commit']:
        raise ValueError('Source commit mismatch: ' + name)
    run(['git', '-C', folder, 'fsck', '--no-reflogs'])
    # Corresponding source is distributed beside the runtime artifact, not installed on the car.
    archive = OUT / 'sources' / (name + '-' + item['version'] + '.tar.gz')
    with archive.open('wb') as dest, gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as compressed:
        process = subprocess.Popen(['git', '-C', str(folder), 'archive', '--format=tar', 'HEAD'], stdout=subprocess.PIPE)
        shutil.copyfileobj(process.stdout, compressed)
        if process.wait():
            raise ValueError('Could not archive corresponding source')
    return folder


def wrapper(name, args):
    file = WORK / name
    file.write_text('#!/bin/sh\nexec ' + shlex.join([str(x) for x in args]) + ' "$@"\n')
    file.chmod(0o755)
    return str(file)


def build():
    if not sys.platform.startswith('linux'):
        raise SystemExit('Runtime compilation requires Linux; the car is never used as a build host.')
    WORK.mkdir(parents=True, exist_ok=True)
    (OUT / 'sources').mkdir(parents=True, exist_ok=True)
    archive = WORK / 'zig.tar.xz'
    download(LOCK['zig']['url'], archive, LOCK['zig']['sha256'])
    zigdir = WORK / ('zig-linux-x86_64-' + LOCK['zig']['version'])
    if not zigdir.exists():
        with tarfile.open(archive) as packed:
            packed.extractall(WORK, filter='data')
    zig = zigdir / 'zig'
    cc = wrapper('target-cc', [zig, 'cc', '-target', LOCK['target'], '-mcpu=baseline'])
    ar = wrapper('target-ar', [zig, 'ar'])
    ranlib = wrapper('target-ranlib', [zig, 'ranlib'])
    env = dict(os.environ, CC=cc, AR=ar, RANLIB=ranlib, SOURCE_DATE_EPOCH='1793577600',
               CFLAGS='-O2 -fno-ident -ffile-prefix-map=' + str(WORK) + '=.',
               PKG_CONFIG_PATH=str(PREFIX / 'lib/pkgconfig'), PKG_CONFIG_LIBDIR=str(PREFIX / 'lib/pkgconfig'))
    sources = {name: source(name, item) for name, item in LOCK['sources'].items()}
    openssl = sources['openssl']
    run(['perl', 'Configure', 'linux-x86_64', 'no-shared', 'no-tests', 'no-asm', 'no-dso', 'no-engine',
         'no-module', 'no-async', '--prefix=' + str(PREFIX), '--libdir=lib'], cwd=openssl, env=env)
    run(['make', '-j2', 'build_libs'], cwd=openssl, env=env)
    run(['make', 'install_dev'], cwd=openssl, env=env)
    qjs = sources['qjs']
    run(['make', '-j2', 'qjs', 'CC=' + cc, 'AR=' + ar, 'CONFIG_LTO=', 'LDFLAGS=-static'], cwd=qjs, env=env)
    shutil.copyfile(qjs / 'qjs', OUT / 'qjs')
    ffmpeg = sources['ffmpeg']
    run(['./configure', '--disable-everything', '--disable-autodetect', '--disable-programs', '--enable-ffmpeg',
         '--disable-doc', '--disable-debug', '--disable-asm', '--disable-shared', '--enable-static',
         '--disable-avdevice', '--disable-postproc', '--disable-swresample', '--enable-version3',
         '--enable-openssl', '--enable-network', '--cc=' + cc, '--ar=' + ar, '--ranlib=' + ranlib,
         '--arch=x86_64', '--target-os=linux', '--pkg-config-flags=--static',
         '--extra-cflags=-I' + str(PREFIX / 'include'),
         '--extra-ldflags=-static -L' + str(PREFIX / 'lib'),
         '--enable-protocol=file,pipe,http,https,tcp,tls', '--enable-demuxer=mov',
         '--enable-parser=h264', '--enable-decoder=h264', '--enable-encoder=rawvideo',
         '--enable-muxer=rawvideo', '--enable-bsf=h264_mp4toannexb,extract_extradata',
         '--enable-filter=buffer,buffersink,scale,pad,setsar,format,fps,null'], cwd=ffmpeg, env=env)
    run(['make', '-j2', 'ffmpeg'], cwd=ffmpeg, env=env)
    shutil.copyfile(ffmpeg / 'ffmpeg', OUT / 'ffmpeg')
    download(LOCK['yt-dlp']['url'], OUT / 'yt-dlp', LOCK['yt-dlp']['sha256'])
    runtime_lock = {}
    for name in ('yt-dlp', 'qjs', 'ffmpeg'):
        file = OUT / name
        file.chmod(0o755)
        version = LOCK[name]['version'] if name == 'yt-dlp' else LOCK['sources'][name]['version']
        runtime_lock[name] = {'version': version, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
        if name != 'yt-dlp':
            headers = subprocess.check_output(['readelf', '-l', str(file)], text=True)
            if 'INTERP' in headers:
                raise ValueError('Runtime is not statically linked: ' + name)
    (OUT / 'runtime-lock.json').write_text(json.dumps(runtime_lock, sort_keys=True, indent=2) + '\n')
    notices = []
    for name, license_name in [('ffmpeg', 'COPYING.LGPLv3'), ('ffmpeg', 'LICENSE.md'),
                               ('qjs', 'LICENSE'), ('openssl', 'LICENSE.txt')]:
        notices.append('\n=== ' + name + ' / ' + license_name + ' ===\n' + (sources[name] / license_name).read_text())
    notices.append('\nyt-dlp 2026.10.26: Unlicense; official executable includes its EJS components. '
                   'See its included licenses and pinned upstream source. QuickJS: MIT. OpenSSL: Apache-2.0. '
                   'FFmpeg: LGPL-3.0-or-later (no GPL/nonfree codecs enabled). '
                   'Corresponding library source archives are included in sources/.\n')
    (OUT / 'LICENSES.txt').write_text(''.join(notices))
    shutil.copyfile(Path(__file__).parent / 'sources.lock.json', OUT / 'sources.lock.json')
    run([OUT / 'ffmpeg', '-version'])
    run([OUT / 'qjs', '-e', 'if (123n * 123n !== 15129n) throw Error("BigInt failure"); print("QuickJS OK")'])
    run([sys.executable, OUT / 'yt-dlp', '--version'])
    fixture = WORK / 'fixture.mp4'
    run(['ffmpeg', '-y', '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
         '-i', 'testsrc=size=640x360:rate=24', '-t', '1', '-pix_fmt', 'yuv420p', '-c:v', 'libx264', fixture])
    frame = WORK / 'frame.i420'
    run([OUT / 'ffmpeg', '-y', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', fixture,
         '-an', '-vf', 'scale=640:360:out_color_matrix=bt601:out_range=tv,setsar=1',
         '-pix_fmt', 'yuv420p', '-frames:v', '1', '-f', 'rawvideo', frame])
    if frame.stat().st_size != 640 * 360 * 3 // 2:
        raise ValueError('Native decoder did not produce a complete I420 frame')
    print('Static runtime build and offline decode passed; real-MGU/audio/vehicle-signal behavior remains unvalidated.')


if __name__ == '__main__':
    build()
