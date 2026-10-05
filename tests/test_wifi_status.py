import ast
from pathlib import Path
import re
import unittest


class WifiStatusTests(unittest.TestCase):
    def test_monitor_adapter_does_not_hide_connected_radio(self):
        source = Path(__file__).resolve().parents[1] / 'backend/server.py'
        tree = ast.parse(source.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'connected_wifi')
        replies = {'iw dev': 'Interface wlan1\nInterface wlan0', 'ip route show default': 'default via 172.20.10.1 dev wlan0',
                   'iw dev wlan1 link': 'Not connected.', 'iw dev wlan0 link': 'Connected to ab:cd:ef:00:11:22\n SSID: iPhone'}
        ns = {'re': re, '_run': lambda cmd: (0, replies.get(cmd, ''))}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), ns)
        self.assertEqual(ns['connected_wifi'](), ('wlan0', 'iPhone'))
        replies['iw dev wlan0 link'] = 'Not connected.'
        self.assertEqual(ns['connected_wifi'](), (None, ''))


if __name__ == '__main__': unittest.main()
