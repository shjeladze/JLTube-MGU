#!/usr/bin/env python3
"""Build the standalone Inspector tool kit and schema-2 Catalog offline."""
import argparse
import copy
import json
from pathlib import Path
from package import pack, sha, ROOT


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
    (out / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(sha(data) + '  ' + name + '\n')
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
