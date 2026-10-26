import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.server import Handler, STATE


class AccessOriginTests(unittest.TestCase):
    def handler(self, headers):
        handler = Handler.__new__(Handler)
        handler.headers = headers
        handler.server = SimpleNamespace(server_port=8018)
        return handler

    def test_local_hosts_are_not_public_https_origins(self):
        with patch.dict(STATE.cfg['server'], trust_proxy_headers=True):
            for host in ('127.0.0.1:8018', 'localhost:8018', '[::1]:8018', '192.168.1.5:8018'):
                self.assertEqual(self.handler({'Host': host})._public_origin(), '')

    def test_forwarded_cloud_origin_is_preserved(self):
        with patch.dict(STATE.cfg['server'], trust_proxy_headers=True):
            self.assertEqual(self.handler({'Host': '127.0.0.1', 'X-Forwarded-Host': 'xiaoyin.onrender.com', 'X-Forwarded-Proto': 'https'})._public_origin(), 'https://xiaoyin.onrender.com')

    def test_scan_uses_actual_listening_port(self):
        with patch.dict(STATE.cfg['server'], public_base_url='', trust_proxy_headers=False), patch('backend.netutil.all_ipv4', return_value=['192.168.1.5']), patch('backend.netutil.primary_ip', return_value='192.168.1.5'):
            h = self.handler({'Host': '127.0.0.1:8018'})
            self.assertEqual(h._access_info()['port'], 8018)
            self.assertEqual(h._qrcode_target({}), 'http://192.168.1.5:8018/scan')
