import unittest

from evalgen.facts import load_all
from evalgen.generate import (DOMAIN_META, fmt_date, generate, validate_facts,
                              validate_records)


class GenerateTest(unittest.TestCase):
    def test_fact_bank_is_valid(self):
        self.assertEqual(validate_facts(load_all()), [])

    def test_default_size_and_balance(self):
        recs = generate(100, seed=1)
        self.assertEqual(len(recs), 500)
        for dom in DOMAIN_META:
            self.assertEqual(sum(r["domain"] == dom for r in recs), 100)
        self.assertEqual(validate_records(recs), [])

    def test_deterministic(self):
        self.assertEqual(generate(20, seed=7), generate(20, seed=7))

    def test_ko_en_parity(self):
        for r in generate(30, seed=3):
            self.assertEqual(len(r["ko"]["choices"]), len(r["en"]["choices"]))
            self.assertIn(r["answer"], "ABCD")

    def test_date_format(self):
        self.assertEqual(fmt_date("2025-03-26", "ko"), "2025년 3월 26일")
        self.assertEqual(fmt_date("2025-03-26", "en"), "26 March 2025")
        self.assertEqual(fmt_date("2026-Q4", "en"), "Q4 2026")


if __name__ == "__main__":
    unittest.main()
