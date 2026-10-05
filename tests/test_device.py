"""Device controls never execute user-provided paths or shell commands."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import device


class Handler:
    def __init__(self, data=None, origin='http://127.0.0.1:8080', address='127.0.0.1'):
        body = json.dumps(data or {}).encode()
        self.headers = {'Host':'127.0.0.1:8082','Origin':origin,'Content-Type':'application/json','Content-Length':str(len(body))}
        self.client_address=(address, 1000); self.rfile=io.BytesIO(body)
    def _send(self, status, body): self.status, self.body = status, json.loads(body)


class DeviceTests(unittest.TestCase):
    def test_counters_exclude_loopback_and_guest_double_counting(self):
        self.assertEqual(device.cpu_counters('cpu 100 0 50 800 50 0 0 0 30 0'), (1000, 850))
        self.assertEqual(device.net_counters('header\nheader\n lo: 9 0 0 0 0 0 0 0 8 0\n wlan0: 100 0 0 0 0 0 0 0 200 0'), {'wlan0':(100,200)})
    def test_brightness_cannot_black_out_display(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name); (path/'max_brightness').write_text('255'); (path/'brightness').write_text('255')
            d=device.Device(); d.backlight=path
            self.assertEqual(d.control('brightness',0)['value'],10)
            self.assertEqual((path/'brightness').read_text(),'26')
            self.assertEqual(d.control('brightness',100)['value'],100)
    def test_invalid_controls_do_not_spawn_commands(self):
        d=device.Device()
        with patch.object(device, 'run') as run:
            for action,value in [('brightness',-1),('volume',101),('volume',True),('volume',float('nan')),('volume','50; reboot'),('mute','toggle'),('/tmp/foo',50)]:
                with self.subTest(action=action,value=value), self.assertRaises(ValueError): d.control(action,value)
            run.assert_not_called()
    def test_control_boundary_and_get_cannot_mutate(self):
        for handler in [Handler(origin='https://example.org'),Handler(origin='null'),Handler(address='192.168.1.10')]:
            with patch.object(device.DEVICE, 'control') as control:
                device.handle_device_request(handler,'POST','/api/device/control')
                self.assertEqual(handler.status,403); control.assert_not_called()
        handler=Handler({'action':'screenshot'})
        with patch.object(device.DEVICE,'control') as control:
            device.handle_device_request(handler,'GET','/api/device/control')
            self.assertEqual(handler.status,405); control.assert_not_called()
    def test_rates_and_cpu_derive_from_elapsed_samples(self):
        d=device.Device(); d.audio_at=1e12
        initial={'/proc/stat':'cpu 100 0 50 850 0 0 0 0', '/proc/net/dev':'h\nh\n wlan0: 100 0 0 0 0 0 0 0 200', '/proc/net/route':'h\nwlan0 00000000 0 0003', '/proc/meminfo':'MemTotal: 1000 kB\nMemAvailable: 400 kB', '/sys/class/thermal/thermal_zone0/temp':'55000','/proc/net/wireless':'h\nh\nwlan0: 0000 35. -65. 0', '/proc/uptime':'200 0'}
        with patch.object(device,'read',side_effect=lambda p:initial.get(str(p),'')), patch.object(device.time,'monotonic',return_value=100):
            a=d.status(); self.assertIsNone(a['cpu_percent']); self.assertIsNone(a['network']['rx_bps'])
        initial['/proc/stat']='cpu 200 0 50 950 0 0 0 0'; initial['/proc/net/dev']='h\nh\n wlan0: 1124 0 0 0 0 0 0 0 2248'
        with patch.object(device,'read',side_effect=lambda p:initial.get(str(p),'')), patch.object(device.time,'monotonic',return_value=102):
            b=d.status(); self.assertEqual(b['cpu_percent'],50); self.assertEqual(b['network']['rx_bps'],512); self.assertEqual(b['network']['tx_bps'],1024)
        initial['/proc/net/dev']='h\nh\n wlan0: 0 0 0 0 0 0 0 0 0'
        with patch.object(device,'read',side_effect=lambda p:initial.get(str(p),'')), patch.object(device.time,'monotonic',return_value=104):
            self.assertIsNone(d.status()['network']['rx_bps'])

if __name__=='__main__': unittest.main()
