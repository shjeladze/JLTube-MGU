#!/usr/bin/env python3
"""Fixed, read-only inventory operations. Never evaluates code from a request."""
import argparse
import json
import os
from pathlib import Path
import platform
import stat
import sys

VERSION = '0.1.0'
OPERATIONS = ('summary', 'platform', 'graphics', 'browser', 'audio', 'safety', 'report')
MAX_FILE = 16384


class Inventory:
    def __init__(self, root=Path('/')):
        self.root = Path(root)

    def path(self, absolute):
        return self.root / absolute.lstrip('/')

    def exists(self, absolute):
        try:
            return self.path(absolute).exists()
        except OSError:
            return False

    def text(self, absolute):
        try:
            path = self.path(absolute)
            if not stat.S_ISREG(path.stat().st_mode):
                return None
            with path.open('rb') as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                return None
            return data.decode('utf-8', errors='replace')
        except OSError:
            return None

    def platform(self):
        release = {}
        for name in ('/etc/os-release', '/etc/os-release-id-dlt'):
            for line in (self.text(name) or '').splitlines():
                key, sep, value = line.partition('=')
                if sep and key in ('ID', 'VERSION_ID', 'BUILD_ID', 'VERSION', 'PRETTY_NAME'):
                    release[key] = value.strip('"')[:256]
        id7 = self.exists('/usr/lib/oap-mainapp')
        id8 = self.exists('/usr/lib/oap-mainapp21')
        return {'system': platform.system(), 'architecture': platform.machine(),
                'kernel': platform.release(), 'python': platform.python_version(),
                'libc': list(platform.libc_ver()), 'release': release,
                'id7ManagerPresent': id7, 'id8ManagerPresent': id8,
                'hmi': 'ID7' if id7 and not id8 else 'ID8' if id8 and not id7 else 'unknown'}

    def components(self):
        result = {}
        for name in ('mgu-deploy', 'mgu-render', 'mgu-uplink', 'mgu-python', 'jltube-player', 'mgu-inspector'):
            base = '/var/opt/' + name + '/current'
            entry = {'present': self.exists(base), 'version': None}
            try:
                meta = json.loads(self.text(base + '/component.json') or '{}')
                value = meta.get('version')
                if isinstance(value, str) and len(value) < 64:
                    entry['version'] = value
            except (ValueError, AttributeError):
                pass
            result[name] = entry
        return result

    def graphics(self):
        return {'paths': {p: self.exists(p) for p in (
            '/run/wayland/wayland-0', '/run/wayland/wayland-1',
            '/run/mgu-render/render.sock', '/dev/dri/renderD128', '/dev/dri/card0')},
            'rendererProtocol': 'mgu-render/1 candidate',
            'renderingTested': False, 'touchTested': False}

    def browser(self):
        namespaces = self.text('/proc/sys/user/max_user_namespaces')
        userns = self.text('/proc/sys/kernel/unprivileged_userns_clone')
        return {'executablesPresent': {p: self.exists(p) for p in (
            '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
            '/usr/bin/QtWebEngineProcess', '/usr/lib/qt5/libexec/QtWebEngineProcess')},
            'maxUserNamespaces': int(namespaces.strip()) if namespaces and namespaces.strip().isdigit() else None,
            'unprivilegedUsernsEnabled': userns.strip() == '1' if userns else None,
            'engineSelected': False, 'sandboxVerified': False,
            'note': 'Presence and sysctl values do not establish executable ABI or usable sandbox support.'}

    def audio(self):
        # Hardware inventory only. Never opens a PCM device or requests audio focus.
        return {'alsaCards': (self.text('/proc/asound/cards') or '')[:4096],
                'alsaPcm': (self.text('/proc/asound/pcm') or '')[:4096],
                'paths': {p: self.exists(p) for p in ('/dev/snd', '/run/pulse/native', '/usr/bin/aplay', '/usr/bin/pactl')},
                'routeVerified': False, 'focusVerified': False, 'playbackAttempted': False,
                'note': 'ALSA/Pulse presence does not identify the authorized BMW media/AVB route.'}

    def safety(self):
        return {'vehicleWrites': False, 'vehicleSubscriptions': False, 'parkSignalValidated': False,
                'stateFilePresent': self.exists('/run/jltube-vehicle/state.json'),
                'bridgeDefinitionsPresent': self.exists('/var/opt/jltube-player/vehicle/someipInterfaces'),
                'note': 'No signal values, BMW definitions, SDK, configuration or credentials are read. Presence is not validation.'}

    def summary(self):
        p = self.platform()
        return {'hmi': p['hmi'], 'system': p['system'], 'architecture': p['architecture'],
                'components': self.components(), 'browserReady': False, 'audioReady': False,
                'vehicleSafetyValidated': False, 'productionReady': False}

    def collect(self, operation):
        if operation not in OPERATIONS:
            raise ValueError('Unsupported operation')
        names = ('summary', 'platform', 'graphics', 'browser', 'audio', 'safety') if operation == 'report' else (operation,)
        return {'schema': 1, 'tool': 'mgu-inspector', 'version': VERSION, 'operation': operation,
                'readOnly': True, 'vehicleAccess': False, 'networkListener': False,
                'results': {name: getattr(self, name)() for name in names}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=OPERATIONS, nargs='?', default='report')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.exit(2, 'The installed tool requires Linux. Run the offline tests on a laptop instead.\n')
    # JSON stdout is the only output; no file writes or subprocesses.
    raw = json.dumps(Inventory().collect(args.operation), ensure_ascii=True, sort_keys=True)
    if len(raw.encode()) > 128 * 1024:
        parser.exit(2, 'Inventory exceeded its size limit.\n')
    sys.stdout.write(raw + '\n')


if __name__ == '__main__':
    main()
