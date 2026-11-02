import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'native/mgu-inspector'))
sys.path.insert(0, str(ROOT / 'tools'))
import agent
import inspector
import inspector_pair_client as client


class AccessTests(unittest.TestCase):
    def test_pairing_is_short_lived_one_use_and_sessions_expire(self):
        clock = [0]
        a = agent.Access(lambda: clock[0])
        code = a.begin()['code']
        token = a.pair(code)['token']
        self.assertTrue(a.authorized(token))
        with self.assertRaises(ValueError): a.pair(code)
        self.assertFalse(a.authorized('x' * 64))
        self.assertFalse(a.authorized('é' * 64))
        clock[0] = 900
        self.assertFalse(a.authorized(token))
        a.begin(); clock[0] = 1020
        with self.assertRaises(ValueError): a.pair(code)

    def test_new_code_and_revoke_invalidate_old_sessions(self):
        a = agent.Access()
        token = a.pair(a.begin()['code'])['token']
        a.begin(); self.assertFalse(a.authorized(token))
        token = a.pair(a.begin()['code'])['token']
        a.revoke(); self.assertFalse(a.authorized(token))

    def test_five_bad_attempts_destroy_pairing_window(self):
        a = agent.Access(); code = a.begin()['code']
        wrong = ('1' if code[0] != '1' else '2') + code[1:]
        for _ in range(5):
            with self.assertRaises(ValueError): a.pair(wrong)
        with self.assertRaises(ValueError): a.pair(code)

    def test_authoritative_app_uid_only(self):
        row = {'kind': 'app', 'id': agent.APP_ID, 'uid': 12345}
        self.assertEqual(agent.registry_uid({'components': [row]}), 12345)
        for rows in [[row, row], [dict(row, uid=0)], [dict(row, uid=True)], [dict(row, kind='tool')], []]:
            self.assertIsNone(agent.registry_uid({'components': rows}))
        a = agent.Agent(); a.uid, a.uid_until = 12345, time.monotonic() + 10
        for uid in (0, 12346):
            with self.assertRaises(ValueError): a.local(uid, {'op': 'begin'})
        self.assertEqual(len(a.local(12345, {'op': 'begin'})['code']), 12)
        a.uid_until = 0
        with self.assertRaises(ValueError): a.local(12345, {'op': 'begin'})

    def test_client_refuses_public_lan_addresses_and_fake_peers(self):
        for address in ('192.168.1.1', '8.8.8.8', '127.0.0.1', 'mgu.example.com', '::1', '100.128.0.1'):
            with self.assertRaises(ValueError): client.Connection(address)
        client.Connection('100.64.1.2')
        state = {'BackendState': 'Running', 'Peer': {'p': {'Online': True, 'TailscaleIPs': ['100.64.1.2']}}}
        self.assertTrue(client.peer_verified(state, '100.64.1.2'))
        self.assertFalse(client.peer_verified(state, '100.64.1.3'))
        state['BackendState'] = 'Stopped'
        self.assertFalse(client.peer_verified(state, '100.64.1.2'))

    def test_network_inventory_never_reads_wifi_secrets_or_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = root / 'sys/class/net/wlan1'; (device / 'wireless').mkdir(parents=True)
            (device / 'operstate').write_text('up')
            (device / 'address').write_text('SECRET_MAC')
            (device / 'ssid').write_text('SECRET_SSID')
            result = inspector.Inventory(root).network()
            self.assertEqual(result['interfaces'], [{'name': 'wlan1', 'state': 'up', 'wireless': True}])
            self.assertNotIn('SECRET_', json.dumps(result))


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = agent.Agent(inspector.Inventory(Path(self.tmp.name)))
        self.agent.uid, self.agent.uid_until = 12345, time.monotonic() + 100
        self.server = await asyncio.start_server(self.agent.http, '127.0.0.1', 0, limit=8193)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close(); await self.server.wait_closed(); self.tmp.cleanup()

    async def raw(self, data):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        writer.write(data); await writer.drain()
        response = await asyncio.wait_for(reader.read(), 5)
        writer.close(); await writer.wait_closed()
        head, body = response.split(b'\r\n\r\n', 1)
        return head, json.loads(body)

    async def post(self, path, value, token=None, extra=b''):
        body = json.dumps(value).encode()
        headers = b'POST ' + path.encode() + b' HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n'
        if token: headers += b'Authorization: Bearer ' + token.encode() + b'\r\n'
        return await self.raw(headers + extra + b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)

    async def test_end_to_end_pair_inventory_and_revoke(self):
        code = self.agent.local(12345, {'op': 'begin'})['code']
        head, pair = await self.post('/v1/pair', {'code': code})
        self.assertIn(b'200 OK', head)
        token = pair['token']
        head, report = await self.post('/v1/inventory', {'operation': 'report'}, token)
        self.assertIn(b'200 OK', head); self.assertTrue(report['readOnly'])
        self.assertIn('network', report['results'])
        head, _ = await self.post('/v1/revoke', {}, token)
        self.assertIn(b'200 OK', head)
        head, _ = await self.post('/v1/inventory', {'operation': 'report'}, token)
        self.assertIn(b'403 Forbidden', head)

    async def test_actual_laptop_client_protocol_on_loopback_fixture(self):
        previous = client.PORT
        client.PORT = self.port
        try:
            c = client.Connection('127.0.0.1', development=True)
            code = self.agent.local(12345, {'op': 'begin'})['code']
            await asyncio.to_thread(c.pair, code)
            report = await asyncio.to_thread(c.collect, 'network')
            self.assertEqual(report['operation'], 'network')
            await asyncio.to_thread(c.revoke)
            self.assertIsNone(c.token)
        finally:
            client.PORT = previous

    async def test_no_auth_no_registration_and_arbitrary_commands_are_refused(self):
        head, _ = await self.post('/v1/inventory', {'operation': 'report'})
        self.assertIn(b'403 Forbidden', head)
        token = self.agent.access.pair(self.agent.access.begin()['code'])['token']
        for path, value in [('/v1/exec', {'command': 'id'}), ('/v1/inventory', {'operation': 'reboot'}),
                            ('/v1/inventory', {'operation': 'report', 'path': '/etc/shadow'})]:
            head, _ = await self.post(path, value, token); self.assertIn(b'403 Forbidden', head)
        self.agent.uid_until = 0
        head, _ = await self.post('/v1/inventory', {'operation': 'report'}, token)
        self.assertIn(b'403 Forbidden', head)

    async def test_browser_origins_duplicate_lengths_and_oversized_bodies_refused(self):
        for extra in [b'Origin: https://example.com\r\n', b'Content-Length: 2\r\n', b'Transfer-Encoding: chunked\r\n']:
            head, _ = await self.post('/v1/pair', {'code': '0' * 12}, extra=extra)
            self.assertIn(b'403 Forbidden', head)
        head, _ = await self.post('/v1/pair', {'code': 'x' * 1100})
        self.assertIn(b'403 Forbidden', head)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux SO_PEERCRED integration')
    async def test_unix_socket_uses_kernel_peer_uid_not_request_uid(self):
        socket_path = str(Path(self.tmp.name) / 'control.sock')
        server = await asyncio.start_unix_server(self.agent.unix, path=socket_path, limit=1025)
        self.agent.uid = os.getuid()
        async def ask(value):
            reader, writer = await asyncio.open_unix_connection(socket_path)
            writer.write(json.dumps(value).encode() + b'\n'); await writer.drain()
            reply = json.loads(await reader.readline())
            writer.close(); await writer.wait_closed()
            return reply
        try:
            self.assertEqual(len((await ask({'op': 'begin'}))['code']), 12)
            self.agent.uid = os.getuid() + 1
            self.assertIn('error', await ask({'op': 'begin', 'uid': self.agent.uid}))
            self.assertIn('error', await ask({'op': 'begin'}))
        finally:
            server.close(); await server.wait_closed()
