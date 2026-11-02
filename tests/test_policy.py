import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


p = module('player', ROOT / 'native/jltube-player/player.py')
packager = module('packager', ROOT / 'tools/package.py')


def sample(**changes):
    data = {'schema': 1, 'boot_id': 'test-boot', 'monotonic': 100, 'speed_mps': 0, 'gear': 'P', 'valid': True}
    data.update(changes)
    return data


class PolicyTests(unittest.TestCase):
    def test_only_fresh_valid_park_zero_speed_is_allowed(self):
        self.assertTrue(p.parked(sample(), 100.2, 'test-boot'))
        for data in [None, {}, sample(speed_mps=0.001), sample(speed_mps=-1), sample(gear='N'),
                     sample(gear='D'), sample(valid=1), sample(valid=False), sample(monotonic=99.6),
                     sample(monotonic=101), sample(boot_id='old-boot'), sample(speed_mps=False),
                     sample(speed_mps='0'), sample(speed_mps=math.nan), sample(monotonic=math.inf)]:
            with self.subTest(data=data):
                self.assertFalse(p.parked(data, 100.2, 'test-boot'))

    def test_url_rejection(self):
        for url in ['file:///etc/passwd', 'http://www.youtube.com/', 'https://127.0.0.1/',
                    'https://[::1]/', 'https://localhost/', 'https://x.local/',
                    'https://user:pass@youtube.com/', 'https://youtube.com:8443/',
                    'https://youtube.com.evil.test/', 'https://youtube.com/\n--exec=bad', '-x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                p.validated_url(url, 'youtube')

    def test_youtube_url(self):
        url = 'https://www.youtube.com/watch?v=abcdefghijk'
        self.assertEqual(p.validated_url(url, 'youtube'), url)
        self.assertEqual(p.validated_url('https://www.google.com/', 'web'), 'https://www.google.com/')

    def test_no_unpinned_runtime(self):
        with self.assertRaises(ValueError):
            p.checked_binaries({})

    def test_package_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = packager.build(tmp)
            self.assertEqual(catalog['schema'], 2)
            self.assertEqual(len(catalog['components']), 2)
            for entry in catalog['components']:
                path = Path(tmp) / entry['artifact']['name']
                self.assertEqual(packager.sha(path.read_bytes()), entry['artifact']['sha256'])
                self.assertEqual(path.stat().st_size, entry['artifact']['size'])
                with tarfile.open(path) as archive:
                    members = archive.getmembers()
                    names = {m.name for m in members}
                    self.assertFalse(any('node_modules' in n or 'oap-sdk' in n for n in names))
                    self.assertTrue(all(m.uid == m.gid == m.mtime == 0 for m in members))
                    if entry['kind'] == 'app':
                        self.assertIn('mgu-app.json', names)
                        self.assertEqual(entry['build'], 'unit')
                    else:
                        manifest = json.load(archive.extractfile('component.json'))
                        for f in manifest['files']:
                            self.assertEqual(f['sha256'], packager.sha(archive.extractfile('files/' + f['path']).read()))
                        self.assertIn('units/jltube-player.service', names)

    def test_reproducible_packages(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            packager.build(first)
            packager.build(second)
            for file in Path(first).iterdir():
                self.assertEqual(file.read_bytes(), (Path(second) / file.name).read_bytes())

    def test_pack_refuses_traversal(self):
        for name in ['../evil', '/evil', 'files/../evil', 'C:/evil', 'files\\evil']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                packager.pack({name: (b'bad', 0o644)})

    @unittest.skipUnless(sys.platform == 'linux', 'Linux frame-file IO test')
    def test_frame_header_ring_and_lockout_black_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'frame'
            frame = p.FrameFile(path, 16, 16)
            frame.write(b'\x7f' * (16 * 16 * 3 // 2))
            content = path.read_bytes()
            header = struct.unpack('<16I', content[:64])
            self.assertEqual(header[:9], (0x4656474d, 1, 16, 16, 1, 1, 3, 0, 0))
            self.assertEqual(content[64 + frame.size:64 + 2 * frame.size], b'\x7f' * frame.size)
            frame.black()
            content = path.read_bytes()
            self.assertEqual(content[64 + 2 * frame.size], 16)
            frame.close()
            self.assertFalse(path.exists())

    @unittest.skipUnless(sys.platform == 'linux', 'Linux O_NOFOLLOW test')
    def test_refuses_existing_frame_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'frame'
            path.write_text('do not overwrite')
            with self.assertRaises(FileExistsError):
                p.FrameFile(path, 16, 16)
            self.assertEqual(path.read_text(), 'do not overwrite')


class BrokerTests(unittest.IsolatedAsyncioTestCase):
    def broker(self, valid=True, changes=None):
        return p.Broker({'app_uid': 12250, 'vehicle_adapter_validated': valid},
                        sample_reader=lambda: sample(**(changes or {})), clock=lambda: 100.2, boot_id='test-boot')

    async def test_cannot_unlock_from_control_socket(self):
        broker = self.broker(False)
        for op in ['unlock', 'vehicle', 'set-state']:
            with self.assertRaises(ValueError):
                await broker.dispatch({'op': op, 'gear': 'P', 'speed_mps': 0}, 12250)
        with self.assertRaises(ValueError):
            await broker.dispatch({'op': 'open', 'mode': 'youtube', 'url': 'https://youtu.be/abcdefghijk'}, 12250)

    async def test_peer_uid_and_missing_config(self):
        broker = self.broker()
        for uid in [0, 3921, 12251]:
            with self.assertRaises(ValueError):
                await broker.dispatch({'op': 'status'}, uid)
        broker.config = {}
        with self.assertRaises(ValueError):
            await broker.dispatch({'op': 'status'}, 12250)

    async def test_browser_returns_truthful_unavailable(self):
        broker = self.broker()
        with self.assertRaisesRegex(ValueError, 'browser engine'):
            await broker.dispatch({'op': 'open', 'mode': 'web', 'url': 'https://www.google.com/'}, 12250)

    async def test_moving_locks_even_with_configuration(self):
        broker = self.broker(changes={'speed_mps': 1})
        self.assertFalse(broker.allowed())
        self.assertFalse((await broker.dispatch({'op': 'status'}, 12250))['allowed'])

    async def test_watchdog_stops_on_motion_and_lost_client(self):
        for change in [{'speed_mps': 2}, {}]:
            broker = self.broker(changes=change)
            cancelled = asyncio.Event()
            async def fake_playback():
                try:
                    await asyncio.sleep(100)
                finally:
                    cancelled.set()
            broker.task = asyncio.create_task(fake_playback())
            await asyncio.sleep(0)
            broker.last_client = 0 if not change else 100.2
            watchdog = asyncio.create_task(broker.watchdog())
            await asyncio.wait_for(cancelled.wait(), 0.5)
            watchdog.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await watchdog
            self.assertEqual(broker.state, 'idle')

    async def test_resolver_output_cap(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b'x' * 100)
        reader.feed_eof()
        with self.assertRaises(ValueError):
            await p.bounded_read(reader, 20)


if __name__ == '__main__':
    unittest.main()
