#!/usr/bin/env python3
"""Build the standalone Inspector tool kit and schema-2 Catalog offline."""
import argparse
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from package import pack, sha, ROOT, safe_path


def build(out, base_url=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'native/mgu-inspector'
    manifest = json.loads((source / 'component.json').read_text())
    kit = copy.deepcopy(manifest)
    kit['files'] = []
    entries = {}
    for item in manifest['files']:
        data = (source / item['from']).read_bytes()
        entries['files/' + item['path']] = (data, int(item['mode'], 8))
        kit['files'].append({'path': item['path'], 'mode': item['mode'], 'sha256': sha(data)})
    kit['units'] = []
    for unit in manifest.get('units', []):
        entries['units/' + safe_path(unit['name'])] = ((source / unit['from']).read_bytes(), 0o644)
        kit['units'].append({'name': unit['name']})
    for name, path in [('LICENSE', ROOT / 'LICENSE'), ('README.md', source / 'README.md')]:
        data = path.read_bytes()
        entries['files/' + name] = (data, 0o644)
        kit['files'].append({'path': name, 'mode': '0644', 'sha256': sha(data)})
    entries['component.json'] = (json.dumps(kit, indent=2, sort_keys=True).encode(), 0o644)
    data = pack(entries)
    name = kit['id'] + '@' + kit['version'] + '.tgz'
    (out / name).write_bytes(data)
    catalog = {'schema': 2, 'components': [{key: kit[key] for key in (
        'id', 'kind', 'version', 'title', 'description', 'requires', 'mguHmi', 'optional', 'uninstallable')}]}
    catalog['components'][0]['artifact'] = {'name': name, 'url': base_url.rstrip('/') + '/' + name if base_url else name,
                                             'size': len(data), 'sha256': sha(data)}
    appdir = ROOT / 'apps/shjeladze_inspector'
    app = json.loads((appdir / 'mgu-app.json').read_text())
    tree = appdir / safe_path(app['tree'])
    pkg = json.loads((tree / 'package.json').read_text())
    desc = json.loads((tree / 'rhmiData/application.json').read_text())['application']
    if (app['id'], app['version']) != (pkg['name'], pkg['version']) or app['requires']['mgu-inspector'] != kit['version']:
        raise ValueError('Inspector app identity/dependency mismatch')
    if app['mguHmi'] != ['ID7', 'ID8'] or pkg['mguHmi'] != app['mguHmi']:
        raise ValueError('Inspector HMI mismatch')
    if sorted(h for ui in desc['uiDescriptions'] for h in ui['hmi']) != app['mguHmi']:
        raise ValueError('Inspector RHMI variants missing')
    for ui in desc['uiDescriptions']:
        ui_data = json.loads((tree / 'rhmiData' / safe_path(ui['uiDescriptionFilePath'].removeprefix('./'))).read_text())
        xml = ET.parse(tree / 'rhmiData' / safe_path(ui['applicationFilePath'].removeprefix('./')))
        comps = ui_data['containers']['1']['components']
        if set(comps) != {c.attrib['id'] for c in xml.findall('.//component')}:
            raise ValueError('Inspector RHMI XML/JSON mismatch')
        for comp in comps.values():
            cell = 'PrimaryText' if ui['hmi'] == ['ID8'] and comp['type'] == 'button' else 'Text'
            if cell not in comp['rows'][0]: raise ValueError('Inspector RHMI text cell mismatch')
    app_entries = {'mgu-app.json': ((appdir / 'mgu-app.json').read_bytes(), 0o644)}
    for module in app['modules']:
        app_entries[safe_path(module)] = ((appdir / safe_path(module)).read_bytes(), 0o644)
    for path in tree.rglob('*'):
        if path.is_symlink() or path.name == 'node_modules' or 'oap-sdk' in path.parts:
            raise ValueError('SDK/symlink content forbidden')
        if path.is_file(): app_entries[path.relative_to(appdir).as_posix()] = (path.read_bytes(), 0o644)
    if (tree / pkg['main']).exists(): raise ValueError('Donor entry must not be shipped')
    app_entries[app['tree'] + '/LICENSE'] = ((ROOT / 'LICENSE').read_bytes(), 0o644)
    app_data = pack(app_entries)
    app_name = app['id'] + '@' + app['version'] + '.tgz'
    (out / app_name).write_bytes(app_data)
    catalog['components'].append({'id': app['id'], 'version': app['version'], 'kind': 'app',
        'title': 'MGU Inspector (development)', 'description': 'Private pairing and revoke controls; read-only diagnostics',
        'mguHmi': app['mguHmi'], 'requires': app['requires'], 'build': 'unit', 'uninstallable': True,
        'artifact': {'name': app_name, 'url': base_url.rstrip('/') + '/' + app_name if base_url else app_name,
                     'size': len(app_data), 'sha256': sha(app_data)}})
    (out / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(sha(data) + '  ' + name + '\n' + sha(app_data) + '  ' + app_name + '\n')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='dist/inspector')
    parser.add_argument('--base-url')
    args = parser.parse_args()
    if args.base_url and not args.base_url.startswith('https://'):
        parser.error('--base-url must use HTTPS')
    build(args.out, args.base_url)
    print('Built on-demand read-only Inspector tool. No vehicle was accessed.')
