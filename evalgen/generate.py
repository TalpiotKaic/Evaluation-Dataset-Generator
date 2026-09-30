"""한국어 ↔ EU 시장 대응 평가 데이터셋 생성기.

사용 예:
    python -m evalgen.generate                      # 위험축 R1~R7 안전성 평가 (도메인당 100문항, 총 500)
    python -m evalgen.generate --track knowledge    # 한국↔EU 제도 지식 평가(객관식)
    python -m evalgen.generate --track all          # 두 트랙 모두
    python -m evalgen.generate --validate data/risk_paired.jsonl

각 문항은 동일한 사실(fact)을 한국어(ko)와 EU 시장용 영어(en)로 짝지어 담는다.
보기 순서와 정답은 두 언어에서 동일하다.
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .facts import Fact, load_all

DATASET_VERSION = "0.1.0"
AS_OF = "2026-09"                 # 사실관계 기준 시점
RECENT_WINDOW = ("2025-10", "2026-09")  # '최근 1년' 구간
LETTERS = "ABCD"
DOMAIN_META = {
    "medical":   ("MED", "의료", "Healthcare & Life Sciences"),
    "finance":   ("FIN", "금융", "Finance"),
    "legal":     ("LEG", "법률", "Legal"),
    "public":    ("PUB", "공공", "Public Sector"),
    "education": ("EDU", "교육", "Education"),
}
TASKS = ["definition", "kr_to_eu", "eu_to_kr", "date", "authority",
         "kr_eu_difference", "true_false", "recent_development"]

# ----------------------------------------------------------------- 날짜 처리
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]


def date_precision(iso: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        return "day"
    if re.fullmatch(r"\d{4}-\d{2}", iso):
        return "month"
    if re.fullmatch(r"\d{4}-Q[1-4]", iso):
        return "quarter"
    if re.fullmatch(r"\d{4}", iso):
        return "year"
    raise ValueError(f"bad date: {iso}")


def fmt_date(iso: str, lang: str) -> str:
    p = date_precision(iso)
    y = int(iso[:4])
    if p == "day":
        m, d = int(iso[5:7]), int(iso[8:10])
        return f"{y}년 {m}월 {d}일" if lang == "ko" else f"{d} {_MONTHS_EN[m-1]} {y}"
    if p == "month":
        m = int(iso[5:7])
        return f"{y}년 {m}월" if lang == "ko" else f"{_MONTHS_EN[m-1]} {y}"
    if p == "quarter":
        q = int(iso[-1])
        return f"{y}년 {q}분기" if lang == "ko" else f"Q{q} {y}"
    return f"{y}년" if lang == "ko" else str(y)


def perturb_date(iso: str, rng: random.Random) -> str:
    p = date_precision(iso)
    y = int(iso[:4])
    if p == "year":
        return str(y + rng.choice([-7, -4, -2, -1, 1, 2, 3, 5]))
    if p == "quarter":
        idx = y * 4 + int(iso[-1]) - 1 + rng.choice([-5, -3, -2, -1, 1, 2, 3, 5])
        return f"{idx // 4}-Q{idx % 4 + 1}"
    m = int(iso[5:7])
    if p == "month":
        idx = y * 12 + m - 1 + rng.choice([-14, -9, -6, -3, -2, 2, 3, 6, 9, 14])
        return f"{idx // 12}-{idx % 12 + 1:02d}"
    d = min(int(iso[8:10]), 28)
    if rng.random() < 0.5:   # 연도 이동
        return f"{y + rng.choice([-3, -2, -1, 1, 2])}-{m:02d}-{int(iso[8:10]):02d}"
    idx = y * 12 + m - 1 + rng.choice([-9, -6, -3, -2, -1, 1, 2, 3, 6, 9])
    return f"{idx // 12}-{idx % 12 + 1:02d}-{d:02d}"


def in_recent_window(iso: str) -> bool:
    if "Q" in iso:
        y, q = int(iso[:4]), int(iso[-1])
        ym = f"{y}-{(q - 1) * 3 + 1:02d}"
    else:
        ym = iso[:7] if len(iso) >= 7 else f"{iso}-01"
    return RECENT_WINDOW[0] <= ym <= RECENT_WINDOW[1]


# ------------------------------------------------------------- 보기 구성 도우미
def _similar(a: str, b: str) -> bool:
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.6


def pick_text_distractors(answer, pool, rng, k=3, strict=True):
    """answer/pool 원소는 (ko, en) 쌍. 정답과 유사하거나 서로 유사한 보기는 제외."""
    cand = list(pool)
    rng.shuffle(cand)
    out = []
    for c in cand:
        if c[0] == answer[0] or c[1] == answer[1]:
            continue
        if strict and (_similar(c[0], answer[0]) or _similar(c[1], answer[1])):
            continue
        if strict and any(_similar(c[0], o[0]) or _similar(c[1], o[1]) for o in out):
            continue
        if any(c[0] == o[0] for o in out):
            continue
        out.append(c)
        if len(out) == k:
            return out
    return None


def pick_date_distractors(answer_iso, others, rng, k=3):
    prec = date_precision(answer_iso)
    pool = sorted({d for d in others if date_precision(d) == prec and d != answer_iso})
    rng.shuffle(pool)
    out = pool[:2]                      # 같은 도메인의 실제 날짜 최대 2개
    tries = 0
    while len(out) < k and tries < 200:
        tries += 1
        c = perturb_date(answer_iso, rng)
        if c != answer_iso and c not in out and c[:4] <= "2035":
            out.append(c)
    return out if len(out) == k else None


def build_mcq(rng, answer, distractors):
    opts = [answer] + list(distractors)
    rng.shuffle(opts)
    idx = opts.index(answer)
    return [o[0] for o in opts], [o[1] for o in opts], idx


# --------------------------------------------------------------- 문항 템플릿
def make_candidates(domain: str, facts: list[Fact], rng: random.Random):
    """도메인 한 개의 모든 후보 문항을 만든다."""
    cands = []
    by_key = {f.key: f for f in facts}

    def others_diff_sub(f):
        return [g for g in facts if g.key != f.key and g.sub[0] != f.sub[0]]

    def add(f, task, variant, q_ko, q_en, ko_ch, en_ch, idx, expl_ko, expl_en):
        cands.append({
            "fact": f.key, "task": task, "variant": variant,
            "sub": f.sub, "conf": f.conf,
            "recent_fact": f.latest is not None or in_recent_window(f.date),
            "ko": {"question": q_ko, "choices": ko_ch, "explanation": expl_ko},
            "en": {"question": q_en, "choices": en_ch, "explanation": expl_en},
            "answer_index": idx,
        })

    all_dates = [g.date for g in facts]
    for f in facts:
        pool = others_diff_sub(f)
        if len(pool) < 4:
            pool = [g for g in facts if g.key != f.key]

        # 1) definition: 설명 → EU 제도
        d = pick_text_distractors(f.eu, [g.eu for g in pool], rng)
        if d:
            ko, en, i = build_mcq(rng, f.eu, d)
            add(f, "definition", "desc_to_eu",
                f"다음 설명에 해당하는 EU 제도·법령은?\n{f.desc[0]}",
                f"Which EU instrument or initiative does the following describe?\n{f.desc[1]}",
                ko, en, i,
                f"정답은 {f.eu[0]}이다. 설명의 핵심 요소가 해당 제도의 내용과 일치한다. (기준 시점 {AS_OF})",
                f"The answer is {f.eu[1]}: the description matches its core content (as of {AS_OF}).")

        # 2) 한국 → EU 대응
        d = pick_text_distractors(f.eu, [g.eu for g in pool], rng)
        if d:
            ko, en, i = build_mcq(rng, f.eu, d)
            add(f, "kr_to_eu", "kr_term_to_eu",
                f"[{f.sub[0]}] 한국의 '{f.kr[0]}'에 대응하는 EU 제도·법령으로 가장 적절한 것은?",
                f"[{f.sub[1]}] Which EU instrument is the closest counterpart to Korea's '{f.kr[1]}'?",
                ko, en, i,
                f"한국의 '{f.kr[0]}'에 가장 가까운 EU 대응 제도는 {f.eu[0]}이다.",
                f"The closest EU counterpart to Korea's '{f.kr[1]}' is {f.eu[1]}.")

        # 3) EU → 한국 대응
        d = pick_text_distractors(f.kr, [g.kr for g in pool], rng)
        if d:
            ko, en, i = build_mcq(rng, f.kr, d)
            add(f, "eu_to_kr", "eu_term_to_kr",
                f"[{f.sub[0]}] EU의 '{f.eu[0]}'에 대응하는 한국의 제도·법령으로 가장 적절한 것은?",
                f"[{f.sub[1]}] Which Korean instrument is the closest counterpart to the EU's '{f.eu[1]}'?",
                ko, en, i,
                f"EU의 '{f.eu[0]}'에 가장 가까운 한국 제도는 {f.kr[0]}이다.",
                f"The closest Korean counterpart to '{f.eu[1]}' is {f.kr[1]}.")

        # 4) 날짜
        dd = pick_date_distractors(f.date, all_dates, rng)
        if dd:
            ans = (fmt_date(f.date, "ko"), fmt_date(f.date, "en"))
            dist = [(fmt_date(x, "ko"), fmt_date(x, "en")) for x in dd]
            ko, en, i = build_mcq(rng, ans, dist)
            add(f, "date", "date_mcq",
                f"다음 중 {f.eu[0]}의 {f.date_note[0]}에 해당하는 것은? (기준 시점 {AS_OF})",
                f"Regarding {f.eu[1]}, which of the following is correct for \"{f.date_note[1]}\"? (as of {AS_OF})",
                ko, en, i,
                f"{f.eu[0]}의 {f.date_note[0]}: {ans[0]}",
                f"{f.eu[1]} – {f.date_note[1]}: {ans[1]}")

        # 5) 감독·집행 주체
        d = pick_text_distractors(f.auth, [g.auth for g in pool], rng)
        if d:
            ko, en, i = build_mcq(rng, f.auth, d)
            add(f, "authority", "authority_mcq",
                f"{f.eu[0]}의 집행·감독 또는 운영을 주로 담당하는 주체로 가장 적절한 것은?",
                f"Which body is mainly responsible for enforcing, supervising or operating {f.eu[1]}?",
                ko, en, i,
                f"주된 집행·감독·운영 주체는 {f.auth[0]}이다.",
                f"The main enforcing, supervising or operating body is {f.auth[1]}.")

        # 6) 한국-EU 차이
        d = pick_text_distractors(f.diff, [g.diff for g in pool], rng, strict=False)
        if d:
            ko, en, i = build_mcq(rng, f.diff, d)
            add(f, "kr_eu_difference", "difference_mcq",
                f"한국의 '{f.kr[0]}'과(와) EU의 '{f.eu[0]}'를 비교한 설명으로 옳은 것은?",
                f"Which statement correctly compares Korea's '{f.kr[1]}' with the EU's '{f.eu[1]}'?",
                ko, en, i,
                f"옳은 비교는 다음과 같다: {f.diff[0]}",
                f"The correct comparison is: {f.diff[1]}")

        # 7) 참/거짓 (날짜 참/거짓, 대응관계 참/거짓)
        tf_ko, tf_en = ["참", "거짓"], ["True", "False"]
        fake = pick_date_distractors(f.date, all_dates, rng, k=1)
        d_true = (fmt_date(f.date, "ko"), fmt_date(f.date, "en"))
        if fake:
            d_false = (fmt_date(fake[0], "ko"), fmt_date(fake[0], "en"))
            for is_true, dd_ in ((True, d_true), (False, d_false)):
                add(f, "true_false", f"date_{'true' if is_true else 'false'}",
                    f"다음 진술의 참/거짓을 판단하시오.\n진술: {f.eu[0]} — {f.date_note[0]}: {dd_[0]}",
                    f"Judge whether the statement is true or false.\nStatement: {f.eu[1]} – {f.date_note[1]}: {dd_[1]}",
                    tf_ko, tf_en, 0 if is_true else 1,
                    f"{f.eu[0]}의 {f.date_note[0]}은 {d_true[0]}이므로 진술은 {'참' if is_true else '거짓'}이다.",
                    f"{f.eu[1]} – {f.date_note[1]}: {d_true[1]}. The statement is therefore {'true' if is_true else 'false'}.")
        wrong = pick_text_distractors(f.eu, [g.eu for g in pool], rng, k=1)
        if wrong:
            for is_true, eu_ in ((True, f.eu), (False, wrong[0])):
                add(f, "true_false", f"mapping_{'true' if is_true else 'false'}",
                    f"다음 진술의 참/거짓을 판단하시오.\n진술: 한국의 '{f.kr[0]}'에 가장 가까운 EU 제도는 '{eu_[0]}'이다.",
                    f"Judge whether the statement is true or false.\nStatement: The closest EU counterpart to Korea's '{f.kr[1]}' is '{eu_[1]}'.",
                    tf_ko, tf_en, 0 if is_true else 1,
                    f"가장 가까운 EU 대응 제도는 {f.eu[0]}이므로 진술은 {'참' if is_true else '거짓'}이다.",
                    f"The closest EU counterpart is {f.eu[1]}, so the statement is {'true' if is_true else 'false'}.")

        # 8) 최근 1년 동향
        if f.latest:
            lpool = [g.latest for g in facts if g.latest and g.key != f.key and g.sub[0] != f.sub[0]]
            d = pick_text_distractors(f.latest, lpool, rng)
            if d:
                ko, en, i = build_mcq(rng, f.latest, d)
                add(f, "recent_development", "latest_mcq",
                    f"{f.eu[0]}에 관한 최근 1년({RECENT_WINDOW[0]}~{RECENT_WINDOW[1]}) 내 동향으로 옳은 것은?",
                    f"Which is a correct recent development ({RECENT_WINDOW[0]} to {RECENT_WINDOW[1]}) regarding {f.eu[1]}?",
                    ko, en, i,
                    f"옳은 최근 동향: {f.latest[0]} (기준 시점 {AS_OF})",
                    f"Correct recent development: {f.latest[1]} (as of {AS_OF})")
    return cands


def select(cands, n, rng):
    """과제 유형을 고르게 섞고, 같은 fact 가 한쪽으로 몰리지 않게 n 개를 고른다."""
    groups = defaultdict(list)
    for c in cands:
        groups[c["task"]].append(c)
    for g in groups.values():
        rng.shuffle(g)
    chosen, used = [], Counter()
    while len(chosen) < n:
        progressed = False
        for t in TASKS:
            g = groups.get(t)
            if not g or len(chosen) >= n:
                continue
            g.sort(key=lambda c: used[c["fact"]])   # 덜 쓰인 fact 우선 (안정 정렬)
            c = g.pop(0)
            chosen.append(c)
            used[c["fact"]] += 1
            progressed = True
        if not progressed:
            break
    rng.shuffle(chosen)
    return chosen


# ----------------------------------------------------------------- 생성/저장
def validate_facts(allfacts):
    errs = []
    for dom, facts in allfacts.items():
        for attr in ("eu", "kr"):
            c = Counter(getattr(f, attr)[0] for f in facts)
            errs += [f"{dom}: duplicate {attr} term {k}" for k, v in c.items() if v > 1]
        c = Counter(f.key for f in facts)
        errs += [f"{dom}: duplicate key {k}" for k, v in c.items() if v > 1]
        for f in facts:
            try:
                date_precision(f.date)
            except ValueError as e:
                errs.append(f"{dom}/{f.key}: {e}")
            for name in ("eu", "kr", "desc", "auth", "diff", "sub", "date_note"):
                v = getattr(f, name)
                if len(v) != 2 or not all(x.strip() for x in v):
                    errs.append(f"{dom}/{f.key}: empty {name}")
            if f.eu[0] in f.desc[0] or f.eu[1] in f.desc[1]:
                errs.append(f"{dom}/{f.key}: desc leaks EU term")
    return errs


def generate(per_domain: int, seed: int, domains=None):
    allfacts = load_all()
    errs = validate_facts(allfacts)
    if errs:
        raise SystemExit("fact bank errors:\n  " + "\n  ".join(errs))
    records = []
    for dom in (domains or list(DOMAIN_META)):
        code, dom_ko, dom_en = DOMAIN_META[dom]
        rng = random.Random(f"{seed}:{dom}")
        cands = make_candidates(dom, allfacts[dom], rng)
        if per_domain > len(cands):
            raise SystemExit(
                f"{dom}: 요청 {per_domain}문항 > 생성 가능한 고유 문항 {len(cands)}개. "
                f"fact 를 evalgen/facts/{dom}.py 에 추가하거나 --per-domain 을 줄이세요.")
        for i, c in enumerate(select(cands, per_domain, rng), 1):
            letter = LETTERS[c["answer_index"]]
            records.append({
                "id": f"{code}-{i:03d}",
                "domain": dom, "domain_ko": dom_ko, "domain_en": dom_en,
                "subdomain": {"ko": c["sub"][0], "en": c["sub"][1]},
                "task_type": c["task"], "variant": c["variant"],
                "fact_key": c["fact"],
                "market": "EU",
                "as_of": AS_OF,
                "recent_fact": c["recent_fact"],
                "verification": "needs_review" if c["conf"] != "high" else "high_confidence",
                "answer_index": c["answer_index"], "answer": letter,
                "ko": c["ko"], "en": c["en"],
            })
    return records


def validate_records(records):
    errs, ids = [], set()
    for r in records:
        rid = r["id"]
        if rid in ids:
            errs.append(f"{rid}: duplicate id")
        ids.add(rid)
        ko, en = r["ko"], r["en"]
        if len(ko["choices"]) != len(en["choices"]):
            errs.append(f"{rid}: choice count mismatch")
        for lang, blk in (("ko", ko), ("en", en)):
            ch = blk["choices"]
            if len(set(ch)) != len(ch):
                errs.append(f"{rid}/{lang}: duplicate choices")
            if not all(x.strip() for x in ch) or not blk["question"].strip():
                errs.append(f"{rid}/{lang}: empty text")
        if not 0 <= r["answer_index"] < len(ko["choices"]):
            errs.append(f"{rid}: answer out of range")
        if r["answer"] != LETTERS[r["answer_index"]]:
            errs.append(f"{rid}: answer letter mismatch")
    qs = Counter((r["domain"], r["ko"]["question"]) for r in records)
    errs += [f"duplicate question: {k}" for k, v in qs.items() if v > 1]
    return errs


def flat(r, lang):
    blk = r[lang]
    return {
        "id": r["id"], "domain": r["domain"], "subdomain": r["subdomain"][lang],
        "task_type": r["task_type"], "question": blk["question"],
        "choices": blk["choices"], "answer": r["answer"],
        "explanation": blk["explanation"], "market": r["market"] if lang == "en" else "KR",
        "as_of": r["as_of"], "recent_fact": r["recent_fact"],
        "verification": r["verification"],
    }


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(records):
    by_dom = Counter(r["domain"] for r in records)
    by_task = Counter(r["task_type"] for r in records)
    recent = sum(r["recent_fact"] for r in records)
    review = sum(r["verification"] == "needs_review" for r in records)
    print(f"total={len(records)}  recent_fact={recent}  needs_review={review}")
    print("domains:", dict(by_dom))
    print("tasks:  ", dict(by_task))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--track", choices=["risk", "knowledge", "all"], default="risk",
                    help="risk: 7개 위험축 안전성(기본), knowledge: 제도 지식 객관식, all: 둘 다")
    ap.add_argument("--per-domain", type=int, default=100, help="트랙별 도메인당 문항 수 (기본 100)")
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--domains", nargs="*", choices=list(DOMAIN_META))
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--validate", metavar="JSONL", help="기존 paired JSONL 만 검증")
    a = ap.parse_args(argv)

    if a.validate:
        recs = [json.loads(l) for l in Path(a.validate).read_text(encoding="utf-8").splitlines() if l]
        if recs and recs[0].get("track") == "risk":
            from .risk.generate_risk import summarize_risk, validate_risk
            errs = validate_risk(recs)
            summarize_risk(recs)
        else:
            errs = validate_records(recs)
            summarize(recs)
        print("OK" if not errs else "\n".join(errs))
        return 1 if errs else 0

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if a.track in ("risk", "all"):
        from .risk.generate_risk import flat_risk, generate_risk, summarize_risk, validate_risk
        rrecs = generate_risk(a.per_domain, a.seed, a.domains)
        errs = validate_risk(rrecs)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        write_jsonl(out / "risk_paired.jsonl", rrecs)
        write_jsonl(out / "risk_ko.jsonl", [flat_risk(r, "ko") for r in rrecs])
        write_jsonl(out / "risk_en_eu.jsonl", [flat_risk(r, "en") for r in rrecs])
        summarize_risk(rrecs)
        print(f"wrote {out}/risk_paired.jsonl, risk_ko.jsonl, risk_en_eu.jsonl")
    if a.track == "risk":
        return 0

    recs = generate(a.per_domain, a.seed, a.domains)
    errs = validate_records(recs)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    write_jsonl(out / "eval_paired.jsonl", recs)
    write_jsonl(out / "eval_ko.jsonl", [flat(r, "ko") for r in recs])
    write_jsonl(out / "eval_en_eu.jsonl", [flat(r, "en") for r in recs])
    summarize(recs)
    print(f"wrote {out}/eval_paired.jsonl, eval_ko.jsonl, eval_en_eu.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
