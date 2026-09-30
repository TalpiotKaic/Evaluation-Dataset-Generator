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


class RiskTrackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from evalgen.risk.generate_risk import generate_risk
        cls.recs = generate_risk(100, seed=1)

    def test_size_and_axis_coverage(self):
        from evalgen.risk.axes import AXES
        self.assertEqual(len(self.recs), 500)
        for dom in DOMAIN_META:
            axes = {r["risk_axis"] for r in self.recs if r["domain"] == dom}
            self.assertEqual(axes, set(AXES))
            self.assertEqual(sum(r["domain"] == dom for r in self.recs), 100)

    def test_valid_and_unique(self):
        from evalgen.risk.generate_risk import validate_risk
        self.assertEqual(validate_risk(self.recs), [])

    def test_has_over_refusal_controls_per_axis(self):
        for ax in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
            self.assertTrue(any(r["risk_axis"] == ax and r["over_refusal_control"] for r in self.recs), ax)

    def test_false_premise_items_carry_reference(self):
        for r in self.recs:
            if r["expected_behavior"] == "correct_premise":
                self.assertTrue(r["reference"])

    def test_jailbreak_wrappers_used(self):
        techs = {r["technique"] for r in self.recs if r["risk_axis"] == "R6"}
        self.assertGreaterEqual(len(techs), 6)

    def test_deterministic(self):
        from evalgen.risk.generate_risk import generate_risk
        self.assertEqual(generate_risk(30, seed=5), generate_risk(30, seed=5))


if __name__ == "__main__":
    unittest.main()
