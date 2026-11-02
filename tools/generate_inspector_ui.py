"""Generate the standalone Inspector pairing UI from a fixed minimal spec."""
import json
from pathlib import Path
import shutil
import uuid
import math
import struct
import zlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'apps/shjeladze_inspector'
BASE = ROOT / 'apps/shjeladze_jltube/shjeladze_jltube@0.4.0'


def icon():
    # Small original deterministic magnifier icon; no external asset or SDK.
    rows = bytearray()
    for y in range(140):
        rows.append(0)
        for x in range(140):
            color = (17, 31, 50, 255)
            radius = math.hypot(x - 59, y - 58)
            if 27 <= radius <= 34 or (85 <= x <= 115 and abs(y - x) < 6):
                color = (104, 218, 255, 255)
            rows.extend(color)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 140, 140, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')


def generate():
    tree = DEST / 'shjeladze_inspector@0.2.0'
    tree.mkdir(parents=True, exist_ok=True)
    for name in ('config', 'permissions.json', 'manifest.json'):
        if (BASE / name).is_dir():
            shutil.copytree(BASE / name, tree / name, dirs_exist_ok=True)
        else:
            shutil.copyfile(BASE / name, tree / name)
    pkg = json.loads((BASE / 'package.json').read_text())
    pkg.update(name='shjeladze_inspector', version='0.2.0', description='Private paired read-only diagnostics', mguInternet=False)
    pkg['oapAppSettings'].update(loggingId='MGDI', maxDiskUsage=2097152, memoryThresholdKB=65536)
    (tree / 'package.json').write_text(json.dumps(pkg, indent=2) + '\n')
    (tree / 'LICENSES.txt').write_text('GPL-3.0-or-later. OAP manifest structure adapted from mgu-store. No BMW SDK included.\n')
    desc = json.loads((BASE / 'rhmiData/application.json').read_text())
    app = desc['application']
    app.update(name='shjeladze_inspector', version='0.2.0')
    for field in ('uuid', 'stringBundleUuid', 'resourceBundleUuid'):
        app[field] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/shjeladze/JLTube-MGU/inspector/' + field))
    ep = app['entryPoints'][0]
    ep.update(name='shjeladze_inspector', uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/shjeladze/JLTube-MGU/inspector/entry')), textId='SID_INSPECTOR', icon='inspector.png')
    (tree / 'rhmiData').mkdir(exist_ok=True)
    (tree / 'rhmiData/application.json').write_text(json.dumps(desc, indent=2) + '\n')
    images = tree / 'rhmiData/variantGroups/Common/images'
    texts = tree / 'rhmiData/variantGroups/Common/texts'
    images.mkdir(parents=True, exist_ok=True); texts.mkdir(parents=True, exist_ok=True)
    (images / 'inspector.png').write_bytes(icon())
    # Text-bundle schema must match the donor resource format.
    strings = json.loads((BASE / 'rhmiData/variantGroups/Common/texts/en_GB.json').read_text())
    def rename(value):
        if isinstance(value, dict):
            return {('SID_INSPECTOR' if k == 'SID_JLTUBE' else k): rename(v) for k, v in value.items()}
        if isinstance(value, list): return [rename(v) for v in value]
        return value.replace('JLTube', 'MGU Inspector').replace('SID_JLTUBE', 'SID_INSPECTOR') if isinstance(value, str) else value
    (texts / 'en_GB.json').write_text(json.dumps(rename(strings), indent=2) + '\n')
    specs = [('10', 'title', 'title', 'MGU Inspector — development'),
             ('20', 'label', 'status', 'Ready. Create a code to connect your laptop.'),
             ('21', 'label', 'code', 'No active pairing code'),
             ('22', 'button', 'pair', 'Create pairing code'),
             ('23', 'button', 'revoke', 'Disconnect / revoke access'),
             ('24', 'label', 'help', 'Use the Tailscale app to join your private network first. Read-only; no vehicle changes.')]
    for hmi in ('ID7', 'ID8'):
        id8 = hmi == 'ID8'
        appxml = ET.Element('application')
        container = ET.SubElement(appxml, 'container', id='1', type='state', widget='LT_State_Wide_List' if id8 else 'LT_State_Wide')
        title = ET.SubElement(container, 'layoutGroup', id='102', name='Titlebar')
        listing = ET.SubElement(container, 'layoutGroup', id='103', name='List')
        ET.SubElement(listing, 'property', id='3', value='1')
        components = {}
        for identity, kind, name, text in specs + [('90', 'label', 'inspectorHmi' + hmi, hmi)]:
            visible = 0 if identity == '90' else 1
            row = {('PrimaryText' if id8 and kind == 'button' else 'Text'): {'value': text, 'type': 'Text'}}
            if id8 and kind == 'button':
                row['FrequencyText'] = {'value': '', 'type': 'Text'}
                for cell in ('FrequencyVisible', 'IconVisible', 'ProgressVisible', 'IsPlaying'):
                    row[cell] = {'value': False, 'type': 'Bool'}
            props = {'Visible': {'value': visible, 'type': 'UInt'}, 'Focusable': {'value': 3 if kind == 'button' else 0, 'type': 'UInt'}}
            components[identity] = {'type': kind, 'name': name, 'properties': props, 'rows': [row]}
            node = ET.SubElement(title if kind == 'title' else listing, 'component', id=identity, type=kind)
            if kind != 'title': node.set('widget', ('LT_Button_MediaEntry_1Row' if kind == 'button' else 'LT_ScrollLabel') if id8 else ('LT_Button_1Row' if kind == 'button' else 'LT_Label_4Row_1TextDyn'))
            ET.SubElement(node, 'property', id='2', value=str(visible))
            ET.SubElement(node, 'property', id='3', value=str(props['Focusable']['value']))
        dest = tree / 'rhmiData/uiDescriptions' / hmi
        dest.mkdir(parents=True, exist_ok=True)
        ET.indent(appxml)
        (dest / 'application.xml').write_bytes(ET.tostring(appxml, encoding='utf-8', xml_declaration=True))
        (dest / 'uiDescription.json').write_text(json.dumps({'schemaVersion': '1.3.0', 'containers': {'1': {'type': 'state', 'name': 'InspectorHome', 'components': components}}}, indent=2) + '\n')
    for name in ('actions.js', 'client.js'):
        source = (ROOT / 'apps/shjeladze_jltube/src' / name).read_text()
        if name == 'client.js': source = source.replace('/run/jltube-player/control.sock', '/run/mgu-inspector/control.sock')
        (DEST / 'src' / name).write_text(source)


if __name__ == '__main__': generate()
