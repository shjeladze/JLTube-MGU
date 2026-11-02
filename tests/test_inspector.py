import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


inspector = module('inspector', ROOT / 'native/mgu-inspector/inspector.py')
client = module('inspector_client', ROOT / 'tools/inspector_connect.py')
packager = module('inspector_package', ROOT / 'tools/package_inspector.py')


class InspectorTests(unittest.TestCase):
    def test_id7_id8_and_ambiguous_platforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inv = inspector.Inventory(root)
            self.assertEqual(inv.platform()['hmi'], 'unknown')
            (root / 'usr/lib/oap-mainapp21').mkdir(parents=True)
            self.assertEqual(inv.platform()['hmi'], 'ID8')
            (root / 'usr/lib/oap-mainapp').mkdir()
            self.assertEqual(inv.platform()['hmi'], 'unknown')
            (root / 'usr/lib/oap-mainapp21').rmdir()
            self.assertEqual(inv.platform()['hmi'], 'ID7')

    def test_allowlisted_release_fields_and_no_privacy_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'etc').mkdir()
            (root / 'etc/os-release').write_text('ID=mgu\nVERSION_ID="42"\nVIN=SECRET_VIN\nTOKEN=SECRET_TOKEN\n')
            (root / 'etc/shadow').write_text('SECRET_PASSWORD')
            result = inspector.Inventory(root).collect('report')
            text = json.dumps(result)
            self.assertNotIn('SECRET_', text)
            self.assertEqual(result['results']['platform']['release'], {'ID': 'mgu', 'VERSION_ID': '42'})
            self.assertTrue(result['readOnly'])
            self.assertFalse(result['networkListener'])
            self.assertFalse(result['results']['summary']['productionReady'])

    def test_component_metadata_does_not_leak_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'var/opt/mgu-python/current'
            p.mkdir(parents=True)
            (p / 'component.json').write_text('{"version":"1.0.2", "password":"SECRET"}')
            result = inspector.Inventory(root).components()
            self.assertEqual(result['mgu-python']['version'], '1.0.2')
            self.assertNotIn('SECRET', json.dumps(result))

    def test_browser_and_audio_presence_never_claims_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in [('usr/bin/chromium', ''), ('proc/sys/user/max_user_namespaces', '100'),
                               ('proc/sys/kernel/unprivileged_userns_clone', '1'), ('proc/asound/cards', 'device')]:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(data)
            inv = inspector.Inventory(root)
            self.assertTrue(inv.browser()['executablesPresent']['/usr/bin/chromium'])
            self.assertFalse(inv.browser()['sandboxVerified'])
            self.assertEqual(inv.browser()['maxUserNamespaces'], 100)
            self.assertEqual(inv.audio()['alsaCards'], 'device')
            self.assertFalse(inv.audio()['routeVerified'])
            self.assertFalse(inv.audio()['playbackAttempted'])

    def test_oversized_inventory_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'etc').mkdir()
            (root / 'etc/os-release').write_text('ID=' + 'x' * (inspector.MAX_FILE + 1))
            self.assertEqual(inspector.Inventory(root).platform()['release'], {})

    def test_no_arbitrary_operation_or_remote_shell_arguments(self):
        for op in ['exec', 'install', 'reboot', 'report; id', '../etc/shadow', '__dict__']:
            with self.subTest(op=op):
                with self.assertRaises(ValueError):
                    inspector.Inventory().collect(op)
                with self.assertRaises(ValueError):
                    client.ssh_argv('mgu', op)
        for host in ['-oProxyCommand=evil', 'mgu;id', 'root@mgu', 'mgu\nhello']:
            with self.assertRaises(ValueError):
                client.ssh_argv(host, 'report')
        argv = client.ssh_argv('my-mgu', 'audio')
        self.assertIn('StrictHostKeyChecking=yes', argv)
        self.assertIn('ForwardAgent=no', argv)
        self.assertIn('ClearAllForwardings=yes', argv)
        self.assertEqual(argv[-1], '/var/opt/mgu-python/current/bin/python3 /var/opt/mgu-inspector/current/inspector.py audio')

    def test_bounded_client_accepts_only_report_envelope(self):
        good = {'schema': 1, 'tool': 'mgu-inspector', 'operation': 'summary', 'readOnly': True}
        result = client.request([sys.executable, '-c', 'print(' + repr(json.dumps(good)) + ')'])
        self.assertEqual(result, good)
        for output in ['{}', '{"schema":1,"tool":"mgu-inspector","readOnly":false}', 'x' * (client.LIMIT + 2)]:
            # Build a small child program even for the oversized-output test.
            program = "print('x' * 140000)" if len(output) > client.LIMIT else 'print(' + repr(output) + ')'
            with self.assertRaises(ValueError):
                client.request([sys.executable, '-c', program])

    def test_reproducible_kit_hashes_and_restricted_service(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            c = packager.build(a)
            packager.build(b)
            artifact = c['components'][0]['artifact']
            data = (Path(a) / artifact['name']).read_bytes()
            self.assertEqual(data, (Path(b) / artifact['name']).read_bytes())
            self.assertEqual(packager.sha(data), artifact['sha256'])
            self.assertEqual(len(data), artifact['size'])
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                manifest = json.load(archive.extractfile('component.json'))
                self.assertFalse(manifest['internet'])
                self.assertEqual(manifest['units'], [{'name': 'mgu-inspector.service'}])
                service = archive.extractfile('units/mgu-inspector.service').read().decode()
                self.assertIn('ProtectSystem=strict', service)
                self.assertIn('NoNewPrivileges=true', service)
                for item in manifest['files']:
                    content = archive.extractfile('files/' + item['path']).read()
                    self.assertEqual(packager.sha(content), item['sha256'])
                    self.assertEqual(archive.getmember('files/' + item['path']).mode, int(item['mode'], 8))
            self.assertEqual(c['components'][1]['build'], 'unit')
            app_artifact = c['components'][1]['artifact']
            app_data = (Path(a) / app_artifact['name']).read_bytes()
            self.assertEqual(packager.sha(app_data), app_artifact['sha256'])
            self.assertEqual(app_data, (Path(b) / app_artifact['name']).read_bytes())


if __name__ == '__main__':
    unittest.main()
