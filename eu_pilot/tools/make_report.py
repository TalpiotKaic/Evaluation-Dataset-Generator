#!/usr/bin/env python3
"""팩별 README/검수 요약(Markdown)과 전체 개요를 만든다. Drive 업로드용. 출력: release/_reports/"""
import json, os, subprocess, hashlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = ["EU", "AT", "DE", "ES", "FR", "IT"]
out = os.path.join(ROOT, "release", "_reports"); os.makedirs(out, exist_ok=True)
def qa(p):
    r = subprocess.run(["python3", os.path.join(ROOT, "tools", "qa_check.py"), p, "--json", f"/tmp/claude-0/qa_{p}.json"], capture_output=True, text=True)
    try: return json.load(open(f"/tmp/claude-0/qa_{p}.json"))
    except Exception: return {}
def blind(p):
    f = f"/tmp/claude-0/{p}_blind.json"
    return json.load(open(f)) if os.path.exists(f) else None
rows = []
for p in PACKS:
    s = json.load(open(os.path.join(ROOT, "release", p, "stats.json"))); b = blind(p); q = qa(p)
    facts = json.load(open(os.path.join(ROOT, "facts", f"{p}.facts.json")))
    fl = facts["facts"] if isinstance(facts, dict) else facts
    lines = [f"# {p} 팩 v0.2 (초안, needs_review)", "",
        f"- release_id: {s['release_id']} / 상태: {s['status']}",
        f"- 문항: 언어당 {s['conceptual_items_per_language']}개(쌍 {s['pairs_per_language']}), 레코드 {s['total_item_records']}개 (영어 원문 + 한국어 역번역)",
        f"- 도메인별(영어): {s['counts_by_domain_en']}", f"- 위험축별: {s['counts_by_risk_en']}",
        f"- 정답 문자 분포: {s['correct_letter']}", f"- 요청 유형: {s['request_class']} / 관할 근거: {s['jurisdiction_basis']}",
        f"- 사실 팩: {s['fact_count']}개(출처 대조 통과 {s['facts_verified']}개), 문항에서 사용 {len(s['facts_used']) if isinstance(s['facts_used'], list) else s['facts_used']}개, 미사용 {s['facts_unused']}",
        f"- 출처 {s['source_count']}건, 최근 변경·예정 사실 {s['facts_recently_changed_or_scheduled']}개", "",
        "## 자동 점검(qa_check)"]
    if q:
        lines.append(f"- 오류 {q.get('errors', q.get('ERRORS','?'))}건, 경고 {q.get('warnings', q.get('WARNINGS','?'))}건 (경고 대부분은 '근접 오답 없음' 또는 EN/KO 숫자 표기 차이)")
    lines += ["", "## 블라인드 검수(AI 2종, 같은 계열 모델)"]
    if b:
        lines += [f"- 선택지만 보고 푼 정확도: {b['options_only_accuracy']} (무작위 25%), 쌍 모두 맞힘 {b['options_only_pair_both_right']}",
                  f"- 문맥 포함 전체 풀이의 키 일치: {b['full_solve_agreement']}, 쌍 모두 일치 {b['full_pair_both_right']}",
                  f"- 불일치 {len(b['full_disagreements'])}건 {b['full_disagreements']}, 모호/의심 표시 {len(b['ambiguity_flags'])}건"]
    else: lines.append("- (결과 없음)")
    lines += ["", "## 한계", "- 사람 전문가 검토 전의 초안입니다. 블라인드 검수는 사람이 아닌 AI이며 작성과 같은 계열이라 독립 검증이 아닙니다.",
              "- EUR-Lex 본문은 공식 Cellar API로, 국가 사이트는 접속 가능한 공식 페이지의 문구 일치로 확인했습니다. 접속이 막힌 사이트는 우회하지 않았습니다.",
              "- 스키마 검증기는 데이터 규격이 안정된 뒤 진행하기로 해 아직 만들지 않았습니다.",
              "- 기계 판독용 원본(jsonl, release_manifest의 sha256 포함)은 GitHub 저장소 `eu_pilot/release/" + p + "/` 에 있습니다. Drive 파일은 검토용 보기입니다."]
    open(os.path.join(out, f"{p}_README.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    # compact facts/sources view
    fb = [f"# {p} 사실 팩과 출처 (검증 결과 포함)\n"]
    for x in fl:
        fb.append(f"## {x['fact_id']} · {x['title']}\n- EN: {x['fact_en']}\n- KO: {x['fact_ko']}\n- 근거: {x.get('legal_basis')} / 기준일: {x.get('effective_date')} / 변동성: {x.get('volatility')}")
        for sr in x.get("sources", []):
            v = sr.get("verification") or {}
            fb.append(f"- 출처: {sr.get('title','')} {sr.get('url')} (검증: {v.get('status', v)})")
        fb.append("")
    open(os.path.join(out, f"{p}_facts_sources.md"), "w", encoding="utf-8").write("\n".join(fb))
    mp = os.path.join(ROOT, "release", p, "release_manifest_draft.json")
    rows.append((p, s, b, hashlib.sha256(open(mp, 'rb').read()).hexdigest()[:16]))
print({f: os.path.getsize(os.path.join(out, f)) for f in sorted(os.listdir(out))})
