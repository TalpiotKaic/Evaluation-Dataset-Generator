#!/usr/bin/env python3
"""블라인드 검수 결과(불일치, 모호 표시)를 수정 담당자가 볼 수 있게 local_id 로 정리한다.
사용: python blind_findings.py <PACK> <options_answers.json> <full_answers.json> <out.json>
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pack, oa_p, fa_p, out = sys.argv[1:5]
idmap = json.load(open(f"/tmp/claude-0/blind_private/{pack}.idmap.json"))
rel = os.path.join(ROOT, "release", pack)
items = {}
for l in open(os.path.join(rel, "items_en_draft.jsonl"), encoding="utf-8"):
    r = json.loads(l); items[r["item_id"]] = r
keys = {}
for l in open(os.path.join(rel, "answer_keys_en_draft.jsonl"), encoding="utf-8"):
    k = json.loads(l); keys[k["item_ref"]["item_id"]] = "ABCD"[int(k["correct_option_id"][1:]) - 1]
oa = json.load(open(oa_p)); fa = json.load(open(fa_p))
res = []
for b, iid in idmap.items():
    f = fa.get(b, {}); ans = f["answer"] if isinstance(f, dict) else f
    amb = bool(isinstance(f, dict) and f.get("ambiguous")); note = f.get("note", "") if isinstance(f, dict) else ""
    wrong = ans.strip().upper()[:1] != keys[iid]
    if wrong or amb:
        ext = items[iid]["metadata"]["extensions"]
        res.append({"local_id": ext["local_id"], "pair_id": ext["pair_id"], "item_id": iid, "key": keys[iid],
                    "full_solver_answer": ans, "disagrees_with_key": wrong, "flagged_ambiguous_or_doubtful": amb,
                    "solver_note": note, "options_only_guess": oa.get(b)})
res.sort(key=lambda r: r["local_id"])
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(res), "findings ->", out)
for r in res: print(" ", r["local_id"], "key", r["key"], "solver", r["full_solver_answer"], "DISAGREE" if r["disagrees_with_key"] else "", "|", r["solver_note"][:70])
