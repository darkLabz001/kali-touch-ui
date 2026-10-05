import ast
import io
from pathlib import Path
import tempfile
import time
import unittest


class ReconLogTests(unittest.TestCase):
    def test_chatty_scanner_keeps_only_latest_64_kib(self):
        source = Path(__file__).resolve().parents[1] / 'backend/server.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'bounded_scan_log')
        scope = {'time': time}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.log'
            raw = b'old console redraw' * 20000 + b'LATEST OUTPUT'
            scope['bounded_scan_log'](io.BytesIO(raw), path)
            self.assertEqual(path.read_bytes(), raw[-65536:])


if __name__ == '__main__': unittest.main()
