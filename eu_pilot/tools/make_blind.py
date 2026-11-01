#!/usr/bin/env python3
"""블라인드 검수용 입력 생성: 정답, 오답 유형, 쌍 역할, 근거 등 메타데이터를 모두 제거한다.
사용: python make_blind.py <PACK>
출력: /tmp/claude-0/blind/<PACK>/options_only.json, full.json  (id 는 불투명 번호)
"""
import json, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pack = sys.argv[1]
rel = os.path.join(ROOT, "release", pack)
items = [json.loads(l) for l in open(os.path.join(rel, "items_en_draft.jsonl"), encoding="utf-8")]
rng = random.Random(f"blind-{pack}")
order = list(range(len(items)))
rng.shuffle(order)
out_dir = f"/tmp/claude-0/blind/{pack}"
os.makedirs(out_dir, exist_ok=True)
full, opts, idmap = [], [], {}
for n, i in enumerate(order, 1):
    it = items[i]
    bid = f"B{n:03d}"
    idmap[bid] = it["item_id"]
    o = [x["text"] for x in it["input"]["options"]]
    full.append({"id": bid, "context": it["input"]["context"], "question": it["input"]["question"],
                 "options": dict(zip("ABCD", o))})
    opts.append({"id": bid, "options": dict(zip("ABCD", o))})
json.dump(full, open(os.path.join(out_dir, "full.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(opts, open(os.path.join(out_dir, "options_only.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.makedirs("/tmp/claude-0/blind_private", exist_ok=True)
json.dump(idmap, open(f"/tmp/claude-0/blind_private/{pack}.idmap.json", "w"))   # 검수자에게 알리지 않는다
print(out_dir, len(items))
