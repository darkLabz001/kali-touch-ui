import ast
from pathlib import Path
import unittest

class ReconSnapshotTests(unittest.TestCase):
    def test_snapshot_reads_csv_once_and_preserves_both_bands(self):
        path=Path(__file__).resolve().parents[1]/'backend/server.py'
        cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='ReconManager')
        scope={}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),scope)
        manager=scope['ReconManager'](); calls=[]
        data={'aps':[{'channel':'6'},{'channel':'36'}],'clients':[{'station':'client'}]}
        manager.data=lambda:(calls.append(True) or data)
        manager.running=lambda:True
        manager.log_tail=lambda:'scan'
        manager.iface='wlan1'
        result=manager.snapshot()
        self.assertEqual(len(calls),1)
        self.assertEqual(result['d'],data)
        self.assertEqual(result['st']['aps'],2)
        self.assertEqual(result['lg'],{'log':'scan'})

if __name__=='__main__': unittest.main()
