#!/usr/bin/env python3
"""Read-only, allowlisted target diagnostics. No VIN, keys, tokens, logs or network probes."""
import json
from pathlib import Path
import platform
import shutil
import subprocess


def command(argv):
    try:
        run = subprocess.run(argv, capture_output=True, text=True, timeout=2, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
        return run.stdout.strip()[:1024] if run.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def collect():
    report = {'schema': 1, 'readOnly': True, 'platform': platform.system(), 'architecture': platform.machine(),
              'kernel': platform.release(), 'python': platform.python_version(), 'libc': platform.libc_ver(),
              'firmware': {}, 'commands': {}, 'components': {}, 'checks': {}}
    for file in ['/etc/os-release-id-dlt', '/etc/os-release']:
        try:
            # Explicit release identifiers only; never include arbitrary file contents.
            for line in Path(file).read_text().splitlines():
                key, sep, value = line.partition('=')
                if sep and key in {'ID', 'VERSION_ID', 'BUILD_ID', 'VERSION', 'PRETTY_NAME'}:
                    report['firmware'][key] = value.strip('"')[:256]
        except OSError:
            pass
    for name in ['node', 'unshare', 'mount', 'nft', 'systemctl', 'systemd-analyze']:
        report['commands'][name] = shutil.which(name)
    report['commands']['nodeVersion'] = command(['node', '--version'])
    report['commands']['systemdVersion'] = command(['systemctl', '--version'])
    report['commands']['glibcVersion'] = command(['getconf', 'GNU_LIBC_VERSION'])
    for name in ['mgu-render', 'mgu-uplink', 'mgu-python', 'mgu-deploy', 'jltube-player']:
        path = Path('/var/opt') / name / 'current'
        entry = {'present': path.exists()}
        try:
            meta = json.loads((path / 'component.json').read_text())
            entry['version'] = meta.get('version')
        except (OSError, ValueError):
            pass
        report['components'][name] = entry
    report['checks']['id7MainAppPresent'] = Path('/usr/lib/oap-mainapp').is_dir()
    report['checks']['rendererSocketPresent'] = Path('/run/mgu-render/render.sock').exists()
    report['checks']['uplinkLeasePresent'] = Path('/run/mgu-uplink/lease.json').exists()
    report['checks']['trustedCaBundlePresent'] = Path('/var/opt/mgu-python/current/ssl/cacert.pem').is_file()
    report['checks']['userNamespaceLimit'] = None
    try:
        report['checks']['userNamespaceLimit'] = int(Path('/proc/sys/user/max_user_namespaces').read_text())
    except (OSError, ValueError):
        pass
    # Presence is useful, but deliberately does not claim browser sandbox compatibility.
    report['browser'] = {'engineSelected': False, 'sandboxVerified': False, 'status': 'needs target-specific validation'}
    report['audio'] = {'routeVerified': False, 'status': 'disabled pending BMW media-session validation'}
    return report


if __name__ == '__main__':
    print(json.dumps(collect(), sort_keys=True, indent=2))
