"""Generate consistent RHMI XML/JSON for the compact ID7 URL keyboard."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
app = root / 'apps/shjeladze_jltube'
manifest = json.loads((app / 'mgu-app.json').read_text())
tree = app / manifest['tree']
specs = [('10', 'title', 'title', 'JLTube — development'),
         ('20', 'label', 'status', 'Locked: vehicle adapter not validated'),
         ('21', 'button', 'google', 'Google (browser unavailable)'),
         ('22', 'button', 'youtube', 'YouTube portal (browser unavailable)'),
         ('23', 'button', 'custom', 'Open saved URL'),
         ('25', 'button', 'enterWeb', 'Enter website URL'),
         ('26', 'button', 'enterYouTube', 'Enter YouTube video URL'),
         ('24', 'button', 'stop', 'Stop'),
         ('30', 'label', 'urlText', ''), ('31', 'button', 'letters', 'a'),
         ('32', 'button', 'nextKeys', 'Next characters'), ('33', 'button', 'erase', 'Delete character'),
         ('34', 'button', 'submitUrl', 'Open'), ('35', 'button', 'cancelUrl', 'Cancel')]
components = {}
application = ET.Element('application')
container = ET.SubElement(application, 'container', id='1', type='state', widget='LT_State_Wide')
titlebar = ET.SubElement(container, 'layoutGroup', id='102', name='Titlebar')
listing = ET.SubElement(container, 'layoutGroup', id='103', name='List')
ET.SubElement(listing, 'property', id='3', value='1')
for identity, kind, name, text in specs:
    hidden = int(identity) >= 30
    props = {'Visible': {'value': 0 if hidden else 1, 'type': 'UInt'},
             'Focusable': {'value': 3 if kind == 'button' and name == 'stop' else 0, 'type': 'UInt'}}
    if hidden and kind == 'button':
        props['Focusable']['value'] = 3
    components[identity] = {'type': kind, 'name': name, 'properties': props,
                            'rows': [{'Text': {'value': text, 'type': 'Text'}}]}
    node = ET.SubElement(titlebar if kind == 'title' else listing, 'component', id=identity, type=kind)
    if kind != 'title':
        node.set('widget', 'LT_Button_1Row' if kind == 'button' else 'LT_Label_4Row_1TextDyn')
    ET.SubElement(node, 'property', id='2', value=str(props['Visible']['value']))
    ET.SubElement(node, 'property', id='3', value=str(props['Focusable']['value']))
desc = {'schemaVersion': '1.3.0', 'containers': {'1': {'type': 'state', 'name': 'JLTubeHome', 'components': components}}}
dest = tree / 'rhmiData/uiDescriptions/ID7'
(dest / 'uiDescription.json').write_text(json.dumps(desc, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
ET.indent(application)
(dest / 'application.xml').write_bytes(ET.tostring(application, encoding='utf-8', xml_declaration=True))
for file in [tree / 'package.json', tree / 'rhmiData/application.json']:
    data = json.loads(file.read_text())
    target = data['application'] if 'application' in data else data
    target['version'] = manifest['version']
    file.write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')
