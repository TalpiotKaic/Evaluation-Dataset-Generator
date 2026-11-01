"""검증기가 실제로 오류를 잡는지 확인하는 부정 테스트. 실행: python -m unittest discover -s eu_pilot/tests -v"""
import json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "validate_schema.py")


def run(rel_dir):
    r = subprocess.run([sys.executable, TOOL, "IT", "--release-dir", rel_dir], capture_output=True, text=True)
    return r.returncode, r.stdout


def mutate_jsonl(path, fn):
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh]
    fn(rows)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "release", "IT"), os.path.join(self.tmp, "IT"))
        self.d = os.path.join(self.tmp, "IT")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_clean_passes(self):
        code, out = run(self.tmp)
        self.assertEqual(code, 0, out)

    def test_bad_enum(self):
        mutate_jsonl(f"{self.d}/items_en_draft.jsonl", lambda r: r[0]["metadata"].__setitem__("domain", "sports"))
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("domain", out)

    def test_missing_key(self):
        mutate_jsonl(f"{self.d}/items_en_draft.jsonl", lambda r: r[0]["input"].pop("question"))
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("question", out)

    def test_three_options(self):
        mutate_jsonl(f"{self.d}/items_en_draft.jsonl", lambda r: r[0]["input"]["options"].pop())
        code, out = run(self.tmp); self.assertEqual(code, 1)

    def test_key_points_to_missing_option(self):
        mutate_jsonl(f"{self.d}/answer_keys_en_draft.jsonl", lambda r: r[0].__setitem__("correct_option_id", "o9"))
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("o9", out)

    def test_two_correct_scores(self):
        def f(r):
            for s in r[0]["option_scores"]:
                s["score"] = 1
        mutate_jsonl(f"{self.d}/answer_keys_en_draft.jsonl", f)
        code, out = run(self.tmp); self.assertEqual(code, 1)

    def test_wrong_jurisdiction(self):
        def f(r):
            for x in r:
                if x["metadata"]["extensions"].get("jurisdiction_basis") == "national_law":
                    x["metadata"]["jurisdiction"] = ["FR"]; return
        mutate_jsonl(f"{self.d}/items_en_draft.jsonl", f)
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("jurisdiction", out)

    def test_dangling_source(self):
        mutate_jsonl(f"{self.d}/items_en_draft.jsonl", lambda r: r[0]["metadata"]["source_refs"].append("SRC-IT-999"))
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("SRC-IT-999", out)

    def test_checksum_mismatch(self):
        with open(f"{self.d}/sources_draft.jsonl", "a", encoding="utf-8") as f:
            f.write("\n")
        code, out = run(self.tmp); self.assertEqual(code, 1); self.assertIn("sha256", out)

    def test_missing_translation(self):
        mutate_jsonl(f"{self.d}/relations_draft.jsonl", lambda r: r.pop(0))
        code, out = run(self.tmp); self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
