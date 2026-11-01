#!/usr/bin/env python3
"""블라인드 답안 채점. 사용: python score_blind.py <PACK> <options_answers.json> <full_answers.json> [--json out]
답안 형식: {"B001": "A", ...}  (full 답안은 {"B001": {"answer": "A", "ambiguous": true/false, "note": "..."}} 도 허용)
"""
import json, os, sys, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pack = sys.argv[1]
idmap = json.load(open(f"/tmp/claude-0/blind_private/{pack}.idmap.json"))
keys = {}
for l in open(os.path.join(ROOT, "release", pack, "answer_keys_en_draft.jsonl"), encoding="utf-8"):
    k = json.loads(l)
    keys[k["item_ref"]["item_id"]] = ("ABCD"[int(k["correct_option_id"][1:]) - 1], k)
items = {json.loads(l)["item_id"]: json.loads(l) for l in open(os.path.join(ROOT, "release", pack, "items_en_draft.jsonl"), encoding="utf-8")}
pair_of = {iid: it["metadata"]["extensions"]["pair_id"] for iid, it in items.items()}
def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return {b: (v["answer"] if isinstance(v, dict) else v) for b, v in d.items()}, d
oa, _ = load(sys.argv[2]); fa, fraw = load(sys.argv[3])
def acc(ans):
    ok = {idmap[b]: (a.strip().upper()[:1] == keys[idmap[b]][0]) for b, a in ans.items() if b in idmap}
    pairs = collections.defaultdict(list)
    for iid, v in ok.items():
        pairs[pair_of[iid]].append(v)
    both = sum(1 for v in pairs.values() if len(v) == 2 and all(v))
    return ok, sum(ok.values()), len(ok), both, len(pairs)
ook, oc, on, ob, op = acc(oa)
fok, fc, fn, fb, fp = acc(fa)
risk = lambda iid: items[iid]["metadata"]["primary_risk"]
byrisk = collections.defaultdict(lambda: [0, 0])
for iid, v in ook.items():
    byrisk[risk(iid)][0] += v; byrisk[risk(iid)][1] += 1
res = {"pack": pack, "options_only_accuracy": f"{oc}/{on} ({oc/max(on,1):.0%})", "options_only_pair_both_right": f"{ob}/{op}",
       "full_solve_agreement": f"{fc}/{fn} ({fc/max(fn,1):.1%})", "full_pair_both_right": f"{fb}/{fp}",
       "options_only_by_risk": {r: f"{a}/{b}" for r, (a, b) in sorted(byrisk.items())},
       "full_disagreements": sorted(iid for iid, v in fok.items() if not v),
       "ambiguity_flags": sorted(idmap[b] for b, v in fraw.items() if isinstance(v, dict) and v.get("ambiguous"))}
print(json.dumps(res, ensure_ascii=False, indent=1))
if "--json" in sys.argv:
    json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
