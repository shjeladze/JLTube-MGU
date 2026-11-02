"""No-SSH client. Only verified online peers in the owner's existing tailnet."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.request

OPERATIONS = ('summary', 'platform', 'graphics', 'browser', 'audio', 'network', 'safety', 'report')
PORT = 5891


def peer_verified(status, address):
    if not isinstance(status, dict) or status.get('BackendState') != 'Running':
        return False
    peers = status.get('Peer', {})
    if not isinstance(peers, dict):
        return False
    return any(isinstance(p, dict) and p.get('Online') is True and isinstance(p.get('TailscaleIPs'), list)
               and address in p['TailscaleIPs'] for p in peers.values())


def verify_peer(address):
    executable = shutil.which('tailscale')
    if not executable and os.name == 'nt':
        candidate = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tailscale/tailscale.exe'
        if candidate.is_file(): executable = str(candidate)
    if not executable:
        raise ValueError('Tailscale is not installed on this laptop')
    proc = subprocess.Popen([executable, 'status', '--json'], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = []
    def read():
        data.append(proc.stdout.read(2 * 1024 * 1024 + 1))
        if len(data[0]) > 2 * 1024 * 1024: proc.kill()
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        proc.wait(timeout=5); thread.join(timeout=1)
        if thread.is_alive() or proc.returncode or not data or len(data[0]) > 2 * 1024 * 1024:
            raise ValueError('Could not verify private network peer')
        if not peer_verified(json.loads(data[0]), address):
            raise ValueError('The MGU is not an online peer in this laptop tailnet')
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait(timeout=2)
        proc.stdout.close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirects are refused')


class Connection:
    def __init__(self, address, development=False):
        ip = ipaddress.ip_address(address)
        if ip.version != 4 or (ip not in ipaddress.ip_network('100.64.0.0/10') and not (development and str(ip) == '127.0.0.1')):
            raise ValueError('Use the car Tailscale IPv4 address, not its Wi-Fi/LAN address')
        self.address, self.development, self.token = str(ip), development, None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def post(self, path, data, authenticated=True):
        if not self.development: verify_peer(self.address)
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            if not self.token: raise ValueError('Pair with the car first')
            headers['Authorization'] = 'Bearer ' + self.token
        req = urllib.request.Request('http://' + self.address + ':' + str(PORT) + path,
                                     data=json.dumps(data).encode(), headers=headers, method='POST')
        with self.opener.open(req, timeout=8) as response:
            raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024 or response.status != 200:
                raise ValueError('Unexpected response')
        value = json.loads(raw)
        if not isinstance(value, dict) or 'error' in value:
            raise ValueError('Request refused')
        return value

    def pair(self, code):
        code = code.replace(' ', '').replace('-', '')
        if len(code) != 12 or not code.isascii() or not code.isdigit():
            raise ValueError('Enter the twelve-digit code shown in the car')
        self.token = None
        value = self.post('/v1/pair', {'code': code}, authenticated=False)
        token = value.get('token')
        if not isinstance(token, str) or len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid session response')
        self.token = token

    def collect(self, operation):
        if operation not in OPERATIONS: raise ValueError('Unsupported operation')
        value = self.post('/v1/inventory', {'operation': operation})
        if value.get('schema') != 1 or value.get('tool') != 'mgu-inspector' or value.get('operation') != operation or value.get('readOnly') is not True:
            raise ValueError('Unexpected report')
        return value

    def revoke(self):
        try:
            return self.post('/v1/revoke', {})
        finally:
            self.token = None
