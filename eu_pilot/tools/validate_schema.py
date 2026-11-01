#!/usr/bin/env python3
"""EU 파일럿 릴리스 스키마 검증기.

1) items / answer_keys: Drive 합의본(v0.9)을 옮긴 schema/*.json 으로 JSON Schema(2020-12) 검증.
2) relations / sources / facts / manifest: Drive에 합의된 스키마가 없어, 빌드 산출물 구조에서 뽑은
   '파생 스키마'(이 파일 안)로 검증한다. 합의본이 생기면 교체한다.
3) 파일 간 정합성: ID 유일성, 정답 키와 선택지 대응, 번역 쌍, 출처/사실 참조, 관할 규칙, 매니페스트 sha256.

사용:
  python validate_schema.py                 # 모든 팩
  python validate_schema.py IT DE           # 지정 팩
  python validate_schema.py --release-dir X # 다른 위치의 release 폴더
  python validate_schema.py --json out.json # 결과를 JSON으로 저장
종료 코드: 오류가 있으면 1, 없으면 0.
"""
import argparse, collections, hashlib, json, os, re, sys
from jsonschema import Draft202012Validator, FormatChecker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = ["EU", "AT", "DE", "ES", "FR", "IT"]
DOM_PREFIX = {"medical": "MED", "finance": "FIN", "legal": "LAW", "public_admin": "PUB", "education": "EDU"}
FILES = {  # 논리 이름 -> 파일명
    "items_en": "items_en_draft.jsonl", "items_ko": "items_ko_reverse_draft.jsonl",
    "keys_en": "answer_keys_en_draft.jsonl", "keys_ko": "answer_keys_ko_reverse_draft.jsonl",
    "relations": "relations_draft.jsonl", "sources": "sources_draft.jsonl", "facts": "facts_draft.jsonl",
    "manifest": "release_manifest_draft.json",
}
NUM = re.compile(r"(\d{6,})")

# ---- 파생 스키마(합의본 없음) ----
S_NULLSTR = {"type": ["string", "null"]}
DERIVED = {
    "relations": {
        "type": "object", "additionalProperties": False,
        "required": ["relation_id", "source_item_id", "source_item_version", "target_item_id", "target_item_version",
                     "derivation_type", "equivalent_option_pairs", "changed_fields", "reason", "recorded_by", "recorded_at"],
        "properties": {
            "relation_id": {"type": "string", "pattern": r"^REL-[A-Z]{2}-\d{5,}$"},
            "source_item_id": {"type": "string", "pattern": r"^KVA-\d{6,}$"}, "source_item_version": {"type": "integer", "minimum": 1},
            "target_item_id": {"type": "string", "pattern": r"^KVA-\d{6,}$"}, "target_item_version": {"type": "integer", "minimum": 1},
            "derivation_type": {"enum": ["translation", "contrast", "attribute_swap"]},
            "equivalent_option_pairs": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["source_option_id", "target_option_id"],
                "properties": {"source_option_id": {"type": "string"}, "target_option_id": {"type": "string"}}}},
            "changed_fields": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string", "minLength": 1}, "recorded_by": {"type": "string"},
            "recorded_at": {"type": "string", "format": "date-time"},
        }, "additionalProperties_note": "pair 관계는 추가 키를 가질 수 있어 확장 허용",
    },
    "sources": {
        "type": "object", "required": ["source_id", "source_type", "citation", "locator", "relevant_excerpt", "excerpt_language", "verified", "fact_ids"],
        "properties": {
            "source_id": {"type": "string", "pattern": r"^SRC-[A-Z]{2}-\d{3}$"},
            "source_type": {"enum": ["website", "law", "regulation", "directive", "official_document", "synthetic", "other"]},
            "citation": {"type": "string", "minLength": 1}, "locator": {"type": "string", "minLength": 1},
            "relevant_excerpt": {"type": "string", "minLength": 1}, "excerpt_language": {"type": "string"},
            "accessed_at": S_NULLSTR, "source_version": S_NULLSTR, "usage_terms": {"type": "string"},
            "verified": {"type": ["boolean", "object", "null"]}, "fact_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
    "facts": {
        "type": "object", "required": ["fact_id", "domain", "jurisdiction", "jurisdiction_basis", "title", "fact_en", "fact_ko",
                                       "legal_basis", "effective_date", "volatility", "source_refs", "verified", "reference_date"],
        "properties": {
            "fact_id": {"type": "string", "pattern": r"^[A-Z]{2}-(MED|FIN|LAW|PUB|EDU)-F\d{2}$"},
            "domain": {"enum": list(DOM_PREFIX)},
            "jurisdiction": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": r"^(GLOBAL|[A-Z]{2})$"}},
            "jurisdiction_basis": {"enum": ["national_law", "eu_law", "synthetic"]},
            "title": {"type": "string", "minLength": 1}, "fact_en": {"type": "string", "minLength": 1}, "fact_ko": {"type": "string", "minLength": 1},
            "legal_basis": {"type": "string", "minLength": 1}, "effective_date": {"type": "string"},
            "volatility": {"enum": ["stable", "recently_changed", "scheduled_change"]},
            "source_refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "verified": {"type": ["boolean", "object"]}, "used_by_items": {"type": "array", "items": {"type": "string"}},
            "reference_date": {"type": "string", "format": "date"},
        },
    },
    "manifest": {
        "type": "object", "required": ["release_id", "release_version", "status", "schema_version", "taxonomy_version", "canary",
                                       "items", "file_checksums", "counts", "released_at"],
        "properties": {
            "release_id": {"type": "string", "pattern": r"^KVR-[A-Z]{2}-PILOT-v\d+\.\d+$"}, "release_version": {"type": "integer", "minimum": 1},
            "status": {"type": "string"}, "schema_version": {"const": "0.9"}, "taxonomy_version": {"type": "string"},
            "canary": {"type": "string", "pattern": r"canary"},
            "items": {"type": "array", "items": {"type": "object", "required": ["item_id", "item_version", "rubric_id", "rubric_version", "language", "split", "item_weight"],
                "properties": {"item_id": {"type": "string"}, "item_version": {"type": "integer"}, "rubric_id": {"type": "string"},
                               "rubric_version": {"type": "integer"}, "language": {"enum": ["ko", "en"]}, "split": {"type": "string"}, "item_weight": {"type": "number"}}}},
            "file_checksums": {"type": "array", "items": {"type": "object", "required": ["path", "sha256"],
                "properties": {"path": {"type": "string"}, "sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"}}}},
            "counts": {"type": "object"}, "released_at": {"type": "string", "format": "date-time"},
        },
    },
}
DERIVED["relations"].pop("additionalProperties_note", None)
DERIVED["relations"].pop("additionalProperties", None)


def load_jsonl(path, errs, tag):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                out.append((n, json.loads(line)))
            except json.JSONDecodeError as e:
                errs.append((tag, f"{os.path.basename(path)}:{n}", f"JSON 파싱 실패: {e}"))
    return out


def schema_check(validator, recs, fname, errs, tag):
    for n, r in recs:
        for e in sorted(validator.iter_errors(r), key=lambda e: list(e.absolute_path)):
            loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
            errs.append((tag, f"{fname}:{n}", f"{loc}: {e.message[:160]}"))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_pack(pack, rel_root, vals):
    errs, warns = [], []
    tag = pack
    d = os.path.join(rel_root, pack)
    for name, fn in FILES.items():
        if not os.path.exists(os.path.join(d, fn)):
            errs.append((tag, fn, "파일 없음"))
    if errs:
        return errs, warns, {}
    data = {k: load_jsonl(os.path.join(d, FILES[k]), errs, tag) for k in FILES if k not in ("manifest",)}
    manifest = json.load(open(os.path.join(d, FILES["manifest"]), encoding="utf-8"))

    # 1) 스키마
    schema_check(vals["items"], data["items_en"], FILES["items_en"], errs, tag)
    schema_check(vals["items"], data["items_ko"], FILES["items_ko"], errs, tag)
    schema_check(vals["keys"], data["keys_en"], FILES["keys_en"], errs, tag)
    schema_check(vals["keys"], data["keys_ko"], FILES["keys_ko"], errs, tag)
    schema_check(vals["relations"], data["relations"], FILES["relations"], errs, tag)
    schema_check(vals["sources"], data["sources"], FILES["sources"], errs, tag)
    schema_check(vals["facts"], data["facts"], FILES["facts"], errs, tag)
    for e in vals["manifest"].iter_errors(manifest):
        errs.append((tag, FILES["manifest"], "/".join(str(p) for p in e.absolute_path) + ": " + e.message[:160]))

    # 2) 교차 정합성
    items = {}
    for lang in ("en", "ko"):
        seen = set()
        for n, it in data[f"items_{lang}"]:
            iid = it.get("item_id")
            where = f"{FILES['items_' + lang]}:{n}"
            if iid in seen:
                errs.append((tag, where, f"item_id 중복 {iid}"))
            seen.add(iid)
            items[iid] = (lang, it)
            md = it.get("metadata", {})
            if md.get("language") != lang:
                errs.append((tag, where, f"metadata.language={md.get('language')} 이 파일 언어({lang})와 다름"))
            m = NUM.search(iid or "")
            dc = md.get("display_code", "")
            parts = dc.split("-")
            if len(parts) == 4:
                if DOM_PREFIX.get(md.get("domain")) != parts[0]:
                    errs.append((tag, where, f"display_code 접두 {parts[0]} 가 domain {md.get('domain')} 와 다름"))
                if parts[1] != md.get("primary_risk"):
                    errs.append((tag, where, f"display_code 위험축 {parts[1]} != primary_risk {md.get('primary_risk')}"))
                if parts[3].lower() != lang:
                    errs.append((tag, where, f"display_code 언어 {parts[3]} 가 파일 언어와 다름"))
            if md.get("risk_subtype", "")[:2] != md.get("primary_risk"):
                errs.append((tag, where, f"risk_subtype {md.get('risk_subtype')} 가 primary_risk 와 다름"))
            opts = it.get("input", {}).get("options") or []
            if [o.get("label") for o in opts] != ["A", "B", "C", "D"]:
                errs.append((tag, where, "선택지 라벨이 A,B,C,D 순서가 아님"))
            if [o.get("display_order") for o in opts] != [1, 2, 3, 4]:
                errs.append((tag, where, "display_order 가 1..4 순서가 아님"))
            if len({o.get("option_id") for o in opts}) != len(opts):
                errs.append((tag, where, "option_id 중복"))
            if len({o.get("text") for o in opts}) != len(opts):
                errs.append((tag, where, "같은 문항 안에 동일한 선택지 문구가 있음"))
            # 관할 규칙
            jb = (md.get("extensions") or {}).get("jurisdiction_basis")
            jur = md.get("jurisdiction") or []
            if jb == "national_law" and jur != [pack]:
                errs.append((tag, where, f"national_law 인데 jurisdiction={jur} (기대 [{pack}])"))
            if jb in ("eu_law", "synthetic") and jur != ["GLOBAL"]:
                errs.append((tag, where, f"{jb} 인데 jurisdiction={jur} (기대 [GLOBAL])"))
            if md.get("locale_scope") == "common" and jur and jur != ["GLOBAL"]:
                warns.append((tag, where, "locale_scope=common 인데 jurisdiction 이 GLOBAL 이 아님"))
            if "CANARY" in json.dumps(it).upper():
                warns.append((tag, where, "문항 본문에 canary 문자열이 있음"))
    en_ids = {i for i, (l, _) in items.items() if l == "en"}
    ko_ids = {i for i, (l, _) in items.items() if l == "ko"}
    if len(en_ids) != len(ko_ids):
        errs.append((tag, "items", f"영어 {len(en_ids)}개, 한국어 {len(ko_ids)}개로 수가 다름"))

    sources = {s["source_id"]: s for _, s in data["sources"]}
    if len(sources) != len(data["sources"]):
        errs.append((tag, FILES["sources"], "source_id 중복"))
    facts = {f["fact_id"]: f for _, f in data["facts"]}
    if len(facts) != len(data["facts"]):
        errs.append((tag, FILES["facts"], "fact_id 중복"))
    for iid, (lang, it) in items.items():
        md = it["metadata"]
        for sr in md.get("source_refs", []):
            if sr not in sources:
                errs.append((tag, iid, f"source_refs 의 {sr} 가 sources 에 없음"))
        for fid in (md.get("extensions") or {}).get("fact_ids", []) or []:
            if fid not in facts:
                errs.append((tag, iid, f"extensions.fact_ids 의 {fid} 가 facts 에 없음"))
    for sid, s in sources.items():
        for fid in s.get("fact_ids", []):
            if fid not in facts:
                errs.append((tag, sid, f"fact_ids 의 {fid} 가 facts 에 없음"))
        v = s.get("verified")
        if s.get("source_type") not in ("synthetic",) and not v:
            warns.append((tag, sid, "비합성 출처인데 verified 가 비어 있음"))
    for fid, f in facts.items():
        for sr in f.get("source_refs", []):
            if sr not in sources:
                errs.append((tag, fid, f"source_refs 의 {sr} 가 sources 에 없음"))
        if not f.get("verified"):
            errs.append((tag, fid, "verified 가 아님(공식 출처 대조 미통과)"))
        if f["jurisdiction_basis"] == "national_law" and f["jurisdiction"] != [pack]:
            errs.append((tag, fid, f"national_law 사실의 jurisdiction={f['jurisdiction']}"))

    # 정답 키
    for lang in ("en", "ko"):
        keyfile = FILES[f"keys_{lang}"]
        seen = set()
        for n, k in data[f"keys_{lang}"]:
            where = f"{keyfile}:{n}"
            iid = k["item_ref"]["item_id"]
            if iid in seen:
                errs.append((tag, where, f"같은 item 에 키가 둘 이상 {iid}"))
            seen.add(iid)
            if iid not in items or items[iid][0] != lang:
                errs.append((tag, where, f"item_ref {iid} 가 {lang} 문항에 없음"))
                continue
            it = items[iid][1]
            oids = [o["option_id"] for o in it["input"]["options"]]
            if k.get("correct_option_id") not in oids:
                errs.append((tag, where, f"correct_option_id {k.get('correct_option_id')} 가 선택지에 없음"))
                continue
            sc = {s["option_id"]: s for s in k.get("option_scores", [])}
            if sorted(sc) != sorted(oids):
                errs.append((tag, where, "option_scores 의 option_id 가 선택지와 다름"))
                continue
            ones = [o for o, s in sc.items() if s["score"] == 1]
            if ones != [k["correct_option_id"]]:
                errs.append((tag, where, f"점수 1 인 선택지 {ones} 가 정답 {k['correct_option_id']} 와 다름"))
            if any(s["score"] not in (0, 1) for s in sc.values()):
                errs.append((tag, where, "exact_option 인데 0/1 이 아닌 점수가 있음"))
            for o, s in sc.items():
                et = s.get("error_type")
                if (et == "correct") != (o == k["correct_option_id"]):
                    errs.append((tag, where, f"{o}: error_type 'correct' 가 정답 선택지와 일치하지 않음"))
                if s.get("refusal_label") is None:
                    errs.append((tag, where, f"{o}: refusal_label 없음"))
            exp = k.get("expected_refusal")
            lab = sc[k["correct_option_id"]].get("refusal_label")
            if exp is True and lab != "refusal" or exp is False and lab != "non_refusal":
                errs.append((tag, where, f"expected_refusal={exp} 인데 정답 선택지 refusal_label={lab}"))
            if k.get("language") not in (None, lang):
                errs.append((tag, where, f"키 language={k.get('language')} 가 파일 언어와 다름"))
            if k["item_ref"]["item_version"] != it["item_version"]:
                errs.append((tag, where, "item_version 불일치"))
            for sr in k.get("source_refs", []):
                if sr not in sources:
                    errs.append((tag, where, f"source_refs 의 {sr} 가 sources 에 없음"))
        missing = {i for i, (l, _) in items.items() if l == lang} - seen
        for i in sorted(missing):
            errs.append((tag, keyfile, f"{i} 의 정답 키가 없음"))

    # 번역/쌍 관계
    trans = {}
    for n, r in data["relations"]:
        where = f"{FILES['relations']}:{n}"
        s, t = r["source_item_id"], r["target_item_id"]
        for x in (s, t):
            if x not in items:
                errs.append((tag, where, f"{x} 가 items 에 없음"))
        if r["derivation_type"] == "translation" and s in items and t in items:
            if items[s][0] != "en" or items[t][0] != "ko":
                errs.append((tag, where, "translation 은 영어 원문→한국어 역번역이어야 함"))
            trans[s] = t
            so = [o["option_id"] for o in items[s][1]["input"]["options"]]
            pairs = r["equivalent_option_pairs"]
            if sorted(p["source_option_id"] for p in pairs) != sorted(so):
                errs.append((tag, where, "equivalent_option_pairs 가 원문 선택지를 모두 덮지 않음"))
            ks = {k["item_ref"]["item_id"]: k for _, k in data["keys_en"]}
            kt = {k["item_ref"]["item_id"]: k for _, k in data["keys_ko"]}
            if s in ks and t in kt:
                mp = {p["source_option_id"]: p["target_option_id"] for p in pairs}
                if mp.get(ks[s]["correct_option_id"]) != kt[t]["correct_option_id"]:
                    errs.append((tag, where, "번역 쌍의 정답 선택지가 서로 대응하지 않음"))
            # display_code 번호 규칙(v0.9): 영어 항목은 한국어 원문 번호를 재사용
            dc_s = items[s][1]["metadata"]["display_code"].split("-")[2]
            dc_t = items[t][1]["metadata"]["display_code"].split("-")[2]
            if dc_s != dc_t:
                warns.append((tag, where, f"번역 쌍의 display_code 번호가 다름({dc_s} vs {dc_t})"))
    for iid in en_ids:
        if iid not in trans:
            errs.append((tag, "relations", f"영어 문항 {iid} 의 번역 관계가 없음"))
    if len(set(trans.values())) != len(trans):
        errs.append((tag, "relations", "한국어 문항이 둘 이상의 원문에 대응함"))

    # 정답 위치 분포
    kc = collections.Counter()
    for _, k in data["keys_en"]:
        it = items.get(k["item_ref"]["item_id"])
        if it:
            lab = next((o["label"] for o in it[1]["input"]["options"] if o["option_id"] == k["correct_option_id"]), None)
            kc[lab] += 1
    if kc and (max(kc.values()) - min(kc.values()) > max(2, len(en_ids) // 10)):
        warns.append((tag, "answer_keys_en", f"정답 문자 분포가 치우침 {dict(kc)}"))

    # 매니페스트
    for c in manifest.get("file_checksums", []):
        p = os.path.join(d, c["path"])
        if not os.path.exists(p):
            errs.append((tag, FILES["manifest"], f"체크섬 대상 파일 없음 {c['path']}"))
        elif sha256_file(p) != c["sha256"]:
            errs.append((tag, FILES["manifest"], f"{c['path']} 의 sha256 이 매니페스트와 다름(파일이 빌드 후 바뀜)"))
    listed = {c["path"] for c in manifest.get("file_checksums", [])}
    for k in ("items_en", "items_ko", "keys_en", "keys_ko", "relations", "sources", "facts"):
        if FILES[k] not in listed:
            warns.append((tag, FILES["manifest"], f"{FILES[k]} 가 file_checksums 에 없음"))
    mids = {(m["item_id"], m["language"]) for m in manifest.get("items", [])}
    fids = {(i, l) for i, (l, _) in items.items()}
    if mids != fids:
        errs.append((tag, FILES["manifest"], f"manifest.items 와 실제 문항이 다름(차이 {len(mids ^ fids)}건)"))
    cnt = manifest.get("counts", {})
    if cnt.get("items_per_language") not in (None, len(en_ids)):
        errs.append((tag, FILES["manifest"], f"counts.items_per_language={cnt.get('items_per_language')} 가 실제 {len(en_ids)}와 다름"))
    n_real_src = len([s for s in sources.values() if s.get("source_type") != "synthetic"])  # 합성 자리표시 출처는 세지 않는 규칙
    if cnt.get("facts") not in (None, len(facts)) or cnt.get("sources") not in (None, n_real_src, len(sources)):
        errs.append((tag, FILES["manifest"], f"counts 의 facts/sources 수가 실제와 다름(facts {cnt.get('facts')}/{len(facts)}, sources {cnt.get('sources')}/{n_real_src})"))
    if manifest.get("release_id", "").split("-")[1:2] != [pack]:
        errs.append((tag, FILES["manifest"], f"release_id {manifest.get('release_id')} 가 팩 {pack} 와 다름"))

    summary = {"items_per_language": len(en_ids), "facts": len(facts), "sources": len(sources), "relations": len(data["relations"]),
               "records_checked": sum(len(v) for v in data.values()) + 1}
    return errs, warns, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="*")
    ap.add_argument("--release-dir", default=os.path.join(ROOT, "release"))
    ap.add_argument("--schema-dir", default=os.path.join(ROOT, "schema"))
    ap.add_argument("--json")
    ap.add_argument("--max-print", type=int, default=40)
    a = ap.parse_args()
    packs = a.packs or PACKS
    fc = FormatChecker()
    def V(sch): return Draft202012Validator(sch, format_checker=fc)
    vals = {
        "items": V(json.load(open(os.path.join(a.schema_dir, "items.schema.v0.9.json"), encoding="utf-8"))),
        "keys": V(json.load(open(os.path.join(a.schema_dir, "answer_keys.schema.v0.9.json"), encoding="utf-8"))),
    }
    for k, s in DERIVED.items():
        Draft202012Validator.check_schema(s)
        vals[k] = V(s)
    report, total_err = {}, 0
    for p in packs:
        errs, warns, summ = validate_pack(p, a.release_dir, vals)
        total_err += len(errs)
        report[p] = {"errors": [list(e) for e in errs], "warnings": [list(w) for w in warns], "summary": summ}
        status = "PASS" if not errs else "FAIL"
        print(f"[{status}] {p}: 오류 {len(errs)}건, 경고 {len(warns)}건  {summ}")
        grouped = collections.OrderedDict()
        for e in errs:
            grouped.setdefault(re.sub(r"[A-Z]{2}-[A-Z]{3}-R\d-\d+|KVA-\d+|\d+", "#", e[2])[:110], []).append(e)
        shown = 0
        for msg, lst in grouped.items():
            if shown >= a.max_print:
                print(f"   ... 오류 유형 {len(grouped) - shown}개 더")
                break
            print(f"   ERROR x{len(lst)}  {lst[0][1]} - {lst[0][2]}")
            shown += 1
        for w in warns[:10]:
            print("   warn ", w[1], "-", w[2])
    if a.json:
        json.dump(report, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("결과:", "모두 통과" if not total_err else f"오류 합계 {total_err}건")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
