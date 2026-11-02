#!/usr/bin/env python3
"""Reproducible offline Catalog builder. Never fetches dependencies or BMW SDK."""
import argparse
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/shjeladze_jltube'
TOOL = ROOT / 'native/jltube-player'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or value.startswith('/') or ':' in value or '..' in value.split('/'):
        raise ValueError('Unsafe package path: ' + str(value))
    return value


def validate():
    app, tool = load(APP / 'mgu-app.json'), load(TOOL / 'component.json')
    tree = APP / safe_path(app['tree'])
    pkg = load(tree / 'package.json')
    if (app['id'], app['version']) != (pkg['name'], pkg['version']):
        raise ValueError('App identity/version mismatch')
    supported = ['ID7', 'ID8']
    if app['schema'] != 1 or app['mguHmi'] != supported or pkg['mguHmi'] != supported or app['internet'] is not True or pkg['mguInternet'] is not True:
        raise ValueError('App compatibility/network declaration mismatch')
    if tool['mguHmi'] != supported or tool['internet'] is not True or tool['uids'] != [3921]:
        raise ValueError('Tool compatibility/network declaration mismatch')
    if app['requires']['jltube-player'] != tool['version']:
        raise ValueError('Player dependency mismatch')
    for component_id, version in [(app['id'], app['version']), (tool['id'], tool['version'])]:
        if not re.fullmatch(r'[a-z][a-z0-9_-]+', component_id) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Invalid component identity')
    for module in app['modules']:
        if not (APP / safe_path(module)).is_file():
            raise ValueError('Missing app module: ' + module)
    if (tree / 'javascript/app.js').exists() or (tree / pkg['main']).exists():
        raise ValueError('Source package must use the head unit donor entry point')
    for p in APP.rglob('*'):
        if p.is_symlink() or p.name == 'node_modules' or 'oap-sdk' in p.parts:
            raise ValueError('SDK/symlink content forbidden')
    appdesc = load(tree / 'rhmiData/application.json')['application']
    if appdesc['name'] != app['id'] or appdesc['version'] != app['version']:
        raise ValueError('RHMI app identity mismatch')
    if sorted(h for ui in appdesc['uiDescriptions'] for h in ui['hmi']) != supported:
        raise ValueError('Missing or duplicate HMI UI description')
    for ui in appdesc['uiDescriptions']:
        if len(ui['hmi']) != 1 or ui['hmi'][0] not in supported:
            raise ValueError('Unexpected HMI')
        xml = ET.parse(tree / 'rhmiData' / safe_path(ui['applicationFilePath'].removeprefix('./')))
        desc = load(tree / 'rhmiData' / safe_path(ui['uiDescriptionFilePath'].removeprefix('./')))
        for state_id, state in desc['containers'].items():
            node = xml.find('./container[@id="' + state_id + '"]')
            if node is None:
                raise ValueError('Missing RHMI state')
            xml_ids = {c.attrib['id'] for c in node.findall('.//component')}
            if xml_ids != set(state['components']):
                raise ValueError('RHMI XML/JSON component mismatch')
            for comp in state['components'].values():
                expected_cell = 'PrimaryText' if ui['hmi'] == ['ID8'] and comp['type'] == 'button' else 'Text'
                if expected_cell not in comp['rows'][0]:
                    raise ValueError('Wrong text cell for ' + ui['hmi'][0])
    for ep in appdesc['entryPoints']:
        if ep['icon'] and not (tree / 'rhmiData/variantGroups/Common/images' / safe_path(ep['icon'])).is_file():
            raise ValueError('Missing app icon')
    for item in tool['files'] + tool['units']:
        if not (TOOL / safe_path(item['from'])).is_file():
            raise ValueError('Missing tool source file')
    service = (TOOL / 'jltube-player.service').read_text()
    if 'NoNewPrivileges=true' not in service or 'KillMode=control-group' not in service:
        raise ValueError('Missing service restrictions')
    return app, tool


def pack(entries):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, (data, mode) in sorted(entries.items()):
            info = tarfile.TarInfo(safe_path(name))
            info.size, info.mode = len(data), mode
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=out, mode='wb', mtime=0, compresslevel=9) as zipped:
        zipped.write(raw.getvalue())
    return out.getvalue()


def build(out, runtime_dir=None, base_url=None):
    app, tool = validate()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    entries = {}
    # Explicit source-package allowlist: no cache, donor, repository or SDK files.
    for name in ['mgu-app.json'] + app['modules']:
        entries[name] = ((APP / name).read_bytes(), 0o644)
    for path in (APP / app['tree']).rglob('*'):
        if path.is_file():
            entries[path.relative_to(APP).as_posix()] = (path.read_bytes(), 0o644)
    entries[app['tree'] + '/LICENSE'] = ((ROOT / 'LICENSE').read_bytes(), 0o644)
    artifacts = []
    artifacts.append((app['id'], app['version'], 'app', pack(entries), app['requires']))
    manifest = copy.deepcopy(tool)
    manifest['files'], manifest['units'] = [], []
    tool_entries = {}
    for item in tool['files']:
        data = (TOOL / item['from']).read_bytes()
        tool_entries['files/' + safe_path(item['path'])] = (data, int(item['mode'], 8))
        manifest['files'].append({'path': item['path'], 'mode': item['mode'], 'sha256': sha(data)})
    for item in tool['units']:
        tool_entries['units/' + safe_path(item['name'])] = ((TOOL / item['from']).read_bytes(), 0o644)
        manifest['units'].append({'name': item['name']})
    if runtime_dir:
        runtime_dir = Path(runtime_dir)
        lock = load(runtime_dir / 'runtime-lock.json')
        pins = load(ROOT / 'dependencies.lock.json')['runtimes']
        for name, pin in pins.items():
            item = lock[name]
            data = (runtime_dir / name).read_bytes()
            if item['version'] != pin['version'] or sha(data) != item['sha256']:
                raise ValueError('Runtime pin/hash mismatch: ' + name)
            if name != 'yt-dlp' and not data.startswith(b'\x7fELF\x02\x01'):
                raise ValueError('Expected Linux ELF64 runtime: ' + name)
            if name != 'yt-dlp' and int.from_bytes(data[18:20], 'little') != 62:
                raise ValueError('Expected x86-64 runtime: ' + name)
            path = 'bin/' + name
            tool_entries['files/' + path] = (data, 0o755)
            manifest['files'].append({'path': path, 'mode': '0755', 'sha256': sha(data)})
        notices = (runtime_dir / 'LICENSES.txt').read_bytes()
        tool_entries['files/runtime-lock.json'] = (json.dumps(lock, sort_keys=True, indent=2).encode(), 0o644)
        tool_entries['files/RUNTIME_LICENSES.txt'] = (notices, 0o644)
        for path in ['runtime-lock.json', 'RUNTIME_LICENSES.txt']:
            manifest['files'].append({'path': path, 'mode': '0644', 'sha256': sha(tool_entries['files/' + path][0])})
    tool_entries['files/LICENSE'] = ((ROOT / 'LICENSE').read_bytes(), 0o644)
    manifest['files'].append({'path': 'LICENSE', 'mode': '0644', 'sha256': sha((ROOT / 'LICENSE').read_bytes())})
    tool_entries['component.json'] = (json.dumps(manifest, sort_keys=True, indent=2).encode(), 0o644)
    artifacts.append((tool['id'], tool['version'], 'tool', pack(tool_entries), tool['requires']))
    catalog = {'schema': 2, 'components': []}
    for identity, version, kind, data, requires in artifacts:
        name = identity + '@' + version + '.tgz'
        (out / name).write_bytes(data)
        component = {'id': identity, 'version': version, 'kind': kind, 'title': identity + ' (development)',
                     'description': 'Development package; parked-state adapter and media runtimes require validation.',
                     'mguHmi': app['mguHmi'] if kind == 'app' else tool['mguHmi'], 'requires': requires, 'uninstallable': True,
                     'artifact': {'name': name, 'url': base_url.rstrip('/') + '/' + name if base_url else name,
                                  'size': len(data), 'sha256': sha(data)}}
        if kind == 'app':
            component['build'] = 'unit'
        else:
            component['optional'] = True
        catalog['components'].append(component)
    (out / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf8')
    (out / 'SHA256SUMS').write_text(''.join(sha((out / name).read_bytes()) + '  ' + name + '\n'
                                         for name in sorted(p.name for p in out.glob('*.tgz'))), encoding='utf8')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'dist'))
    parser.add_argument('--runtime-dir')
    parser.add_argument('--base-url', help='Public HTTPS release download directory for a GitHub catalog release')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        validate()
        print('Manifests, source tree, RHMI structure and tool source references: OK')
    else:
        if args.base_url and not args.base_url.startswith('https://'):
            parser.error('--base-url must use HTTPS')
        result = build(args.out, args.runtime_dir, args.base_url)
        print('Built', len(result['components']), 'development artifacts and Catalog; playback remains gated.')
