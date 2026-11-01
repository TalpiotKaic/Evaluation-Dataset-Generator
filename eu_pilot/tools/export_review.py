#!/usr/bin/env python3
"""검토자용 압축 보기: 팩별 영어/한국어 문항을 도메인별 Markdown 으로 내보낸다. (기계 판독용 원본은 release/<PACK>/*.jsonl)"""
import json, os, sys, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pack = sys.argv[1]
rel = os.path.join(ROOT, "release", pack); out = os.path.join(ROOT, "release", pack, "review")
os.makedirs(out, exist_ok=True)
def rd(n): return [json.loads(l) for l in open(os.path.join(rel, n), encoding="utf-8")]
items = {l: rd(f"items_{l}_draft.jsonl" if l == "en" else "items_ko_reverse_draft.jsonl") for l in ("en", "ko")}
keys = {l: {k["item_ref"]["item_id"]: k for k in rd(f"answer_keys_{l}_draft.jsonl" if l == "en" else "answer_keys_ko_reverse_draft.jsonl")} for l in ("en", "ko")}
srcs = {s["source_id"]: s for s in rd("sources_draft.jsonl")}
rels = rd("relations_draft.jsonl")
tr = {}
for r in rels:
    if r.get("relation_type") == "translation":
        tr[r["from_item_id"] if "from_item_id" in r else r["source_item_id"]] = r.get("to_item_id") or r.get("target_item_id")
def ext(it): return it["metadata"]["extensions"]
by_dom = collections.defaultdict(list)
for it in items["en"]: by_dom[it["metadata"]["domain"] if "domain" in it["metadata"] else ext(it).get("domain", "?")].append(it)
ko_by_local = {ext(i)["local_id"]: i for i in items["ko"]}
STD = {'What is the most appropriate response from the AI assistant?','Which reply from the AI assistant is the most appropriate?','AI 도우미의 응답으로 가장 적절한 것은 무엇입니까?'}
def block(it, lang, k):
    e = ext(it); lines = [f"#### {e['local_id']} · {e.get('pair_id','')[-4:]} {e.get('pair_role','')[:1]}",
        f"{it['input']['context']}"] + ([] if it['input']['question'] in STD else [f"**{it['input']['question']}**"])
    
    ck = k["correct_option_id"]
    for o in it["input"]["options"]:
        mark = " ✅" if o["option_id"] == ck else ""
        sc = next(s for s in k["option_scores"] if s["option_id"] == o["option_id"])
        lines.append(f"- {o['label']}. {o['text']}{mark}" + "")
    return "\n".join(lines)
files = []
for dom, its in sorted(by_dom.items()):
    its.sort(key=lambda i: ext(i)["local_id"])
    for lang in ("en", "ko"):
        buf = [f"# {pack} · {dom} · {lang.upper()} (draft, needs_review)\n"]
        for it in its:
            src = it if lang == "en" else ko_by_local[ext(it)["local_id"]]
            buf.append(block(src, lang, keys[lang][src["item_id"]])); buf.append("")
        fn = f"{pack}_{dom}_{lang}.md"; open(os.path.join(out, fn), "w", encoding="utf-8").write("\n".join(buf)); files.append(fn)
print(pack, [(f, os.path.getsize(os.path.join(out, f))) for f in files])
