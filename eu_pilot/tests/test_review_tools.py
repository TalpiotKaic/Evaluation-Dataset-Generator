"""검토 워크북 생성기와 취합 도구의 기본 동작 확인."""
import os, shutil, subprocess, sys, tempfile, unittest
from openpyxl import load_workbook
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MK = os.path.join(ROOT, "tools", "make_review_workbook.py"); IM = os.path.join(ROOT, "tools", "review_import.py")


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        subprocess.run([sys.executable, MK, "IT", "--out", self.tmp], check=True, capture_output=True)
        self.src = os.path.join(self.tmp, "K-VeriAI_EU_review_IT.xlsx")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fill(self, rows):
        dst = os.path.join(self.tmp, "K-VeriAI_EU_review_IT_tester.xlsx"); shutil.copy(self.src, dst)
        wb = load_workbook(dst); ws = wb["문항검토"]; h = {c.value: c.column for c in ws[2]}
        for r, vals in rows.items():
            for k, v in vals.items():
                ws.cell(r, h[k], v)
        wb.save(dst); return dst

    def run_import(self, path):
        return subprocess.run([sys.executable, IM, path, "--out", os.path.join(self.tmp, "out")], capture_output=True, text=True)

    def test_workbook_has_all_items(self):
        ws = load_workbook(self.src)["문항검토"]
        self.assertEqual(ws.max_row - 2, 70)
        self.assertEqual([c.value for c in ws[2]][:3], ["문항번호", "영어 item_id", "한국어 item_id"])

    def test_empty_workbook_imports_clean(self):
        r = self.run_import(self.src); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_valid_review(self):
        p = self.fill({3: {"①사실 정확성": "적합", "최종 판정": "승인", "검토자": "tester"}})
        r = self.run_import(p); self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_reason_is_error(self):
        p = self.fill({3: {"②정답 유일성": "수정 필요", "최종 판정": "수정 후 승인", "검토자": "tester"}})
        r = self.run_import(p); self.assertEqual(r.returncode, 1); self.assertIn("제안", open(os.path.join(self.tmp, "out", "review_summary.md"), encoding="utf-8").read())

    def test_bad_value_is_error(self):
        p = self.fill({3: {"①사실 정확성": "좋음", "최종 판정": "승인", "검토자": "tester"}})
        self.assertEqual(self.run_import(p).returncode, 1)


if __name__ == "__main__":
    unittest.main()
