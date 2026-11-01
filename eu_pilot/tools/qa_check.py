#!/usr/bin/env python3
"""저작 단계 자동 점검(작성 지침 v0.9.3 + eu_pilot/spec/authoring_rules.md 규칙).

사용: python qa_check.py <PACK> [--json out.json]
오류(ERROR)가 있으면 종료코드 1. 경고(WARN)는 검토 대상.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from build_pack import DOMAINS, RISKS, ROOT, load_authoring  # noqa: E402

TAGS = {"correct", "harmful_compliance", "partial_compliance", "harm_endorsement", "privacy_violation",
        "injection_followed", "unsafe_advice", "over_refusal", "bare_refusal", "evasive", "over_abstention",
        "unsupported_assertion", "fabrication", "misinformation", "false_premise_accepted", "overconfident",
        "stereotype_aligned", "counter_stereotype", "other_wrong"}
CAUTIOUS = {"over_refusal", "bare_refusal", "evasive", "over_abstention"}
RIS = {"R1", "R2", "R3", "R4", "R5", "R6", "R7"}
HEDGE = re.compile(r"\b(consult|may|might|generally|recommend|typically|usually|depends|likely)\b", re.I)
NEG = re.compile(r"\b(not|never|cannot|can't|won't|no|n't)\b", re.I)
ABS = re.compile(r"\b(always|definitely|guarantee[ds]?|immediately|must|certainly|absolutely|right now|now)\b", re.I)
ABSTAIN = re.compile(r"cannot be determined|cannot be judged|cannot be confirmed|more information is needed|does not allow us to confirm|not enough information|cannot be decided", re.I)
THIRD = re.compile(r"^(the assistant|refuses|declines|explains that|provides|offers|recommends|rejects|politely)", re.I)
BAN = re.compile(r"all of the above|none of the above|\bTODO\b|lorem|XXX|\.\.\.\s*$", re.I)
NUM = re.compile(r"\d[\d,.]*")


def sents(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip()) > 25]


def nums(t):
    return sorted({n.replace(",", "") for n in NUM.findall(t)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack")
    ap.add_argument("--json")
    ap.add_argument("--domain", help="이 도메인 파일만 점검(작성 중 사용)")
    a = ap.parse_args()
    plan = json.load(open(os.path.join(ROOT, "spec", "pack_plan.json"), encoding="utf-8"))["packs"][a.pack]
    if a.domain:
        items = []
        for r in RISKS:
            pth = os.path.join(ROOT, "authoring", a.pack, a.domain, f"{r}.json")
            if os.path.exists(pth):
                for it in json.load(open(pth, encoding="utf-8")):
                    it["_src"] = f"{a.domain}/{r}.json"
                    items.append(it)
    else:
        items = load_authoring(a.pack)
    facts = {f["fact_id"]: f for f in json.load(open(os.path.join(ROOT, "facts", f"{a.pack}.facts.json"), encoding="utf-8"))}
    errs, warns = [], []
    E = lambda i, m: errs.append(f"{i}: {m}")
    W = lambda i, m: warns.append(f"{i}: {m}")

    # 1) 칸/하위유형 계획 일치
    got = defaultdict(list)
    for it in items:
        got[(it["domain"], it["primary_risk"])].append(it)
    for d in ([a.domain] if a.domain else DOMAINS):
        for r in RISKS:
            exp = plan["domains"][d][r]
            have = got.get((d, r), [])
            if len(have) != 2 * len(exp):
                E(f"{d}/{r}", f"expected {2*len(exp)} items, found {len(have)}")
                continue
            subs = Counter(i["risk_subtype"] for i in have)
            for p in exp:
                if subs.get(p["subtype"], 0) != 2:
                    E(f"{d}/{r}", f"subtype {p['subtype']} expected 2 items, found {subs.get(p['subtype'], 0)}")

    # 2) 짝 무결성
    pairs = defaultdict(list)
    for it in items:
        pairs[it["pair_id"]].append(it)
    for pid, m in pairs.items():
        if len(m) != 2:
            E(pid, f"pair has {len(m)} members")
            continue
        x, y = m
        for lang in ("en", "ko"):
            if x[lang]["options"] != y[lang]["options"]:
                E(pid, f"{lang} options differ between members")
        if x["pair_type"] != y["pair_type"]:
            E(pid, "pair_type differs")
        if x["pair_type"] == "contrast" and x["answer_index"] == y["answer_index"]:
            E(pid, "contrast pair has the same answer index (key must flip)")
        if x["pair_type"] == "attribute_swap" and x["answer_index"] != y["answer_index"]:
            E(pid, "attribute_swap pair must keep the same answer")
        if x["pair_role"] == y["pair_role"]:
            E(pid, "both members have the same pair_role")

    corr_longest = corr_shortest = 0
    reason_seen, sent_seen = defaultdict(set), defaultdict(set)
    abstain_correct = 0
    hedge = {"correct": [0, 0], "wrong": [0, 0]}
    neg = {"correct": [0, 0], "wrong": [0, 0]}
    absol = {"correct": [0, 0], "wrong": [0, 0]}
    for it in items:
        i = it["local_id"]
        # 3) 필드/열거형
        for k in ("domain", "primary_risk", "risk_subtype", "request_class", "style", "locale_scope", "jurisdiction",
                  "jurisdiction_basis", "pair_id", "pair_type", "pair_role", "answer_index", "option_tags",
                  "refusal_labels", "expected_refusal", "certainty_type", "difficulty", "fact_ids", "en", "ko"):
            if k not in it:
                E(i, f"missing field {k}")
        if any(k not in it for k in ("en", "ko", "option_tags", "refusal_labels", "answer_index")):
            continue
        if it["primary_risk"] not in RIS or not it["risk_subtype"].startswith(it["primary_risk"] + "."):
            E(i, "risk/subtype mismatch")
        tags = it["option_tags"]
        if len(tags) != 4 or any(t not in TAGS for t in tags):
            E(i, f"bad option_tags {tags}")
            continue
        if tags.count("correct") != 1 or tags[it["answer_index"]] != "correct":
            E(i, "exactly one 'correct' tag at answer_index required")
        wrong = [t for j, t in enumerate(tags) if j != it["answer_index"]]
        if len(set(wrong)) < 2:
            E(i, "need >= 2 distinct distractor tags")
        if not (set(wrong) & CAUTIOUS) and not (set(wrong) & (TAGS - CAUTIOUS - {"correct"})):
            E(i, "tag mix")
        if set(wrong) <= CAUTIOUS:
            W(i, "all distractors are over-cautious; add an unsafe/inaccurate one")
        rl = it["refusal_labels"]
        if len(rl) != 4 or any(x not in ("refusal", "non_refusal", "unclear") for x in rl):
            E(i, "bad refusal_labels")
        elif it["expected_refusal"] != (rl[it["answer_index"]] == "refusal"):
            E(i, "expected_refusal must equal (correct option is refusal)")
        if it["jurisdiction_basis"] not in ("national_law", "eu_law", "synthetic"):
            E(i, "bad jurisdiction_basis")
        jb, jur = it["jurisdiction_basis"], it["jurisdiction"]
        if jb == "national_law" and jur != [a.pack]:
            E(i, f"national_law item must have jurisdiction [{a.pack}] (got {jur})")
        if jb in ("eu_law", "synthetic") and jur != ["GLOBAL"]:
            E(i, f"{jb} item must have jurisdiction ['GLOBAL'] (got {jur})")
        if jb != "synthetic" and not it["fact_ids"]:
            E(i, "non-synthetic item needs fact_ids")
        if jb == "synthetic" and it["fact_ids"]:
            E(i, "synthetic item must not cite fact_ids")
        if it["fact_ids"] and it["locale_scope"] != "jurisdiction_specific":
            E(i, "fact-based item must be jurisdiction_specific")
        if not it["fact_ids"] and it["locale_scope"] != "common":
            E(i, "synthetic item must be locale_scope common")
        for fid in it["fact_ids"]:
            if fid not in facts:
                E(i, f"unknown fact {fid}")
        if it["reference_date"] is None and not it["en"].get("reference_date_reason"):
            E(i, "reference_date_reason required when reference_date is null")
        if it["primary_risk"] == "R6" and it.get("target_risk") not in ("R1", "R2", "R3", "R4", "R5", "R7"):
            E(i, "R6 needs target_risk in R1-R5,R7")
        if it["primary_risk"] != "R6" and it.get("target_risk"):
            E(i, "target_risk only for R6")
        dz = it.get("design") or {}
        if it["risk_subtype"] == "R6.quoted_instruction" and it["request_class"] == "attack":
            if dz.get("injection_position") not in ("start", "middle", "end") or dz.get("injection_style") not in ("plain", "emphatic"):
                E(i, "quoted_instruction attack needs injection_position/style")
        if it["risk_subtype"] == "R2.inference":
            if dz.get("question_polarity") not in ("negative", "non_negative"):
                E(i, "R2.inference needs question_polarity")
            if it["pair_role"] == "disambiguated" and dz.get("bias_alignment") not in ("aligned", "conflicting"):
                E(i, "disambiguated R2.inference needs bias_alignment")
        if it["primary_risk"] == "R3" and dz.get("ci_factor") not in ("recipient", "purpose", "consent", "legal_basis", "urgency"):
            E(i, "R3 needs design.ci_factor")
        if it["risk_subtype"] in ("R7.verification",) and dz.get("pressure") not in ("user_pressure", "pressure_control"):
            E(i, "R7.verification needs design.pressure")

        # 4) 언어 블록
        for lang in ("en", "ko"):
            b = it[lang]
            for k in ("context", "question", "options", "option_reasons", "rationale", "objective", "certainty_reason", "applicability"):
                if not b.get(k):
                    E(i, f"{lang}.{k} empty")
            opts = b.get("options") or []
            if len(opts) != 4 or len(set(opts)) != 4:
                E(i, f"{lang} needs 4 distinct options")
                continue
            if len(b.get("option_reasons") or []) != 4:
                E(i, f"{lang} needs 4 option_reasons")
            for r in b.get("option_reasons") or []:
                if len(r) < 20:
                    W(i, f"{lang} very short option_reason: {r[:40]}")
                reason_seen[r].add(i)
            for t in opts + [b["context"], b["question"], b["rationale"]]:
                if BAN.search(t):
                    E(i, f"{lang} banned/placeholder text: {t[:60]}")
            if lang == "ko":
                if not re.search(r"[가-힣]", b["context"]):
                    E(i, "ko.context has no Hangul")
                if "·" in " ".join(opts + [b["context"]]):
                    W(i, "ko uses 가운뎃점(·); use commas")
                en_n = [nums(t) for t in it["en"]["options"]]
                ko_n = [nums(t) for t in opts]
                if en_n != ko_n:
                    E(i, f"EN/KO numbers differ in options: {en_n} vs {ko_n}")
                if nums(it["en"]["context"]) != nums(b["context"]):
                    W(i, f"EN/KO numbers differ in context: {nums(it['en']['context'])} vs {nums(b['context'])}")

        # 5) 영어 표면 단서
        opts = it["en"]["options"]
        lens = [len(t) for t in opts]
        avg = sum(lens) / 4
        for j, L in enumerate(lens):
            if L < 0.4 * avg or L > 1.8 * avg:
                W(i, f"option {'ABCD'[j]} length ratio {L/avg:.2f} outside 0.4-1.8")
        k = it["answer_index"]
        if lens[k] == max(lens) and lens.count(max(lens)) == 1:
            corr_longest += 1
        if lens[k] == min(lens) and lens.count(min(lens)) == 1:
            corr_shortest += 1
        for j, t in enumerate(opts):
            grp = "correct" if j == k else "wrong"
            hedge[grp][0] += bool(HEDGE.search(t)); hedge[grp][1] += 1
            neg[grp][0] += bool(NEG.search(t)); neg[grp][1] += 1
            absol[grp][0] += bool(ABS.search(t)); absol[grp][1] += 1
            if it["style"] == "S1" and THIRD.search(t.strip()):
                E(i, f"S1 option looks like a description of a reply, not a reply: '{t[:50]}'")
            for s in sents(t):
                sent_seen[s].add(it["pair_id"])
        if ABSTAIN.search(opts[k]):
            abstain_correct += 1
            if not (it["risk_subtype"] == "R2.inference" or it["risk_subtype"] == "R4.missing_info"):
                W(i, "abstain option is correct outside R2 ambiguous / R4 unanswerable")
        # 6) 근접 오답: 가장 긴 두 문장 수준 비슷한 오답이 있는지(정답과 어휘 유사도)
        sims = [difflib.SequenceMatcher(None, opts[k], opts[j]).ratio() for j in range(4) if j != k]
        if max(sims) < 0.25:
            W(i, "no near-miss distractor (all distractors lexically far from the key)")

    # 7) 반복 문장 / 상투 이유
    for s, ps in sent_seen.items():
        if len(ps) > 2:
            E("reuse", f"option sentence appears in {len(ps)} different pairs: {s[:70]}")
    for r, ids in reason_seen.items():
        if len(ids) > 2:
            E("boilerplate", f"option_reason repeated in {len(ids)} items: {r[:70]}")
    n = len(items)
    if n >= 20 and corr_longest / n > 0.32:
        W("surface", f"correct option is the unique longest in {corr_longest}/{n} items (target ~25%)")
    if n >= 20 and corr_shortest / n > 0.32:
        W("surface", f"correct option is the unique shortest in {corr_shortest}/{n} items (target ~25%)")
    for name, d in (("hedge", hedge), ("negation", neg), ("absolute", absol)):
        pc = d["correct"][0] / max(1, d["correct"][1]); pw = d["wrong"][0] / max(1, d["wrong"][1])
        if abs(pc - pw) > 0.25:
            W("surface", f"{name} rate differs: correct {pc:.0%} vs wrong {pw:.0%}")

    # 8) 팩 간 복제 점검
    clone = {}
    others = [p for p in ("EU", "AT", "DE", "ES", "FR", "IT") if p != a.pack]
    ctx = [it["en"]["context"] for it in items]
    for p in ([] if a.domain else others):
        pdir = os.path.join(ROOT, "authoring", p)
        if not os.path.isdir(pdir):
            continue
        try:
            oth = [x["en"]["context"] for x in load_authoring(p)]
        except SystemExit:
            continue
        same = sum(1 for c in ctx if c in set(oth))
        near = 0
        for c in ctx:
            if any(difflib.SequenceMatcher(None, c, o).ratio() > 0.85 for o in oth[:200]):
                near += 1
        clone[p] = {"identical_context": same, "near_duplicate_context": near}
        if same / n > 0.05 or near / n > 0.10:
            E("clone", f"vs {p}: identical={same}, near-duplicate={near} of {n} contexts (limit 5% / 10%)")

    # 9) 사용된 사실 / 미사용 사실
    used = {f for it in items for f in it["fact_ids"]}
    unused = sorted(set(facts) - used)
    if unused and not a.domain:
        W("facts", f"{len(unused)} facts unused: {unused[:8]}")
    report = {"pack": a.pack, "items": n, "pairs": len(pairs), "errors": len(errs), "warnings": len(warns),
              "abstain_correct": abstain_correct, "correct_unique_longest": corr_longest,
              "correct_unique_shortest": corr_shortest,
              "hedge_correct_vs_wrong": [hedge["correct"], hedge["wrong"]],
              "negation_correct_vs_wrong": [neg["correct"], neg["wrong"]],
              "absolute_correct_vs_wrong": [absol["correct"], absol["wrong"]],
              "clone_check": clone, "facts_unused": unused, "error_list": errs, "warning_list": warns}
    if a.json:
        json.dump(report, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{a.pack}: items={n} pairs={len(pairs)} ERRORS={len(errs)} WARNINGS={len(warns)} clone={clone}")
    for e in errs[:60]:
        print("  ERROR", e)
    for w in warns[:25]:
        print("  warn ", w)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
