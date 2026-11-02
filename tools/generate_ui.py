"""Generate separate native RHMI layouts for ID7 and ID8 from one UI spec."""
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
         ('22', 'button', 'youtube', 'Search YouTube'),
         ('23', 'button', 'custom', 'Open saved URL'),
         ('25', 'button', 'enterWeb', 'Enter website URL'),
         ('26', 'button', 'enterYouTube', 'Enter YouTube video URL'),
         ('24', 'button', 'stop', 'Stop'), ('27', 'button', 'results', ''),
         ('30', 'label', 'urlText', ''), ('31', 'button', 'letters', 'a'),
         ('32', 'button', 'nextKeys', 'Next characters'), ('33', 'button', 'erase', 'Delete character'),
         ('34', 'button', 'submitUrl', 'Open'), ('35', 'button', 'cancelUrl', 'Cancel')]
for hmi in manifest['mguHmi']:
    id8 = hmi == 'ID8'
    components = {}
    application = ET.Element('application')
    container = ET.SubElement(application, 'container', id='1', type='state', widget='LT_State_Wide_List' if id8 else 'LT_State_Wide')
    titlebar = ET.SubElement(container, 'layoutGroup', id='102', name='Titlebar')
    listing = ET.SubElement(container, 'layoutGroup', id='103', name='List')
    ET.SubElement(listing, 'property', id='3', value='1')
    for identity, kind, name, text in specs + [('90', 'label', 'jltubeHmi' + hmi, hmi)]:
        hidden = int(identity) >= 30 or name == 'results'
        props = {'Visible': {'value': 0 if hidden else 1, 'type': 'UInt'},
                 'Focusable': {'value': 3 if kind == 'button' and (hidden or name == 'stop') else 0, 'type': 'UInt'}}
        row = {('PrimaryText' if id8 and kind == 'button' else 'Text'): {'value': text, 'type': 'Text'}}
        if id8 and kind == 'button':
            row['FrequencyText'] = {'value': '', 'type': 'Text'}
            for cell in ['FrequencyVisible', 'IconVisible', 'ProgressVisible', 'IsPlaying']:
                row[cell] = {'value': False, 'type': 'Bool'}
        components[identity] = {'type': kind, 'name': name, 'properties': props, 'rows': [row]}
        node = ET.SubElement(titlebar if kind == 'title' else listing, 'component', id=identity, type=kind)
        if kind != 'title':
            widget = ('LT_Button_MediaEntry_1Row' if kind == 'button' else 'LT_ScrollLabel') if id8 else (
                'LT_Button_1Row' if kind == 'button' else 'LT_Label_4Row_1TextDyn')
            node.set('widget', widget)
        ET.SubElement(node, 'property', id='2', value=str(props['Visible']['value']))
        ET.SubElement(node, 'property', id='3', value=str(props['Focusable']['value']))
    desc = {'schemaVersion': '1.3.0', 'containers': {'1': {'type': 'state', 'name': 'JLTubeHome', 'components': components}}}
    dest = tree / 'rhmiData/uiDescriptions' / hmi
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'uiDescription.json').write_text(json.dumps(desc, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    ET.indent(application)
    (dest / 'application.xml').write_bytes(ET.tostring(application, encoding='utf-8', xml_declaration=True))
for file in [tree / 'package.json', tree / 'rhmiData/application.json']:
    data = json.loads(file.read_text())
    target = data['application'] if 'application' in data else data
    target['version'] = manifest['version']
    if 'application' in data:
        target['uiDescriptions'] = [{'applicationFilePath': './uiDescriptions/' + hmi + '/application.xml',
                                    'uiDescriptionFilePath': './uiDescriptions/' + hmi + '/uiDescription.json',
                                    'hmi': [hmi]} for hmi in manifest['mguHmi']]
        for group in target['variantGroups']:
            group['hmi'] = manifest['mguHmi']
    else:
        target['mguHmi'] = manifest['mguHmi']
    file.write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')
