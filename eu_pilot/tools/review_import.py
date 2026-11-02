#!/usr/bin/env python3
"""작성된 전문가 검토 워크북을 읽어 결과를 취합한다.

사용:
  python review_import.py 파일1.xlsx 파일2.xlsx ... [--out DIR]
  python review_import.py review/returned/*.xlsx

출력(기본 review/results/):
  review_results.jsonl   문항×검토자 한 줄
  review_results.csv     엑셀에서 열기 쉬운 같은 내용
  review_summary.md      진행률, 판정 분포, 수정이 필요한 문항 목록, 입력 오류, 검토자 간 불일치
  fact_review.csv        사실·출처 검증 입력 취합
입력 점검: 판정이 비었거나 값이 목록 밖, 항목에 '수정 필요/부적합'이 있는데 이유가 없음,
'보류/폐기'인데 코멘트가 없음, '승인'인데 항목에 문제 표시가 있음, 검토자 이름이 없음.
이 도구는 release 파일을 바꾸지 않는다. 결과를 보고 담당자가 authoring 을 고쳐 다시 빌드한다.
종료 코드: 입력 오류가 있으면 1.
"""
import argparse, collections, csv, datetime, glob, json, os, re, sys
from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRIT = ["①사실 정확성", "②정답 유일성", "③오답 적절성", "④쌍 설계", "⑤위험·안전 판단", "⑥한국어 번역", "⑦관할·현지화", "⑧표면 단서"]
CRIT_OK = {"적합", "수정 필요", "부적합", "해당 없음"}
FINAL_OK = {"승인", "수정 후 승인", "보류", "폐기"}
HEAD_ROW = 2


def clean(v):
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def reviewer_from_name(path):
    m = re.match(r"K-VeriAI_EU_review_([A-Z]{2})(?:_(.+))?\.xlsx$", os.path.basename(path))
    return (m.group(1), m.group(2) or "") if m else ("", "")


def read_sheet(ws, header_row):
    heads = [clean(c.value) for c in ws[header_row]]
    idx = {h: i for i, h in enumerate(heads) if h}
    for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
        yield {h: clean(r[i]) if i < len(r) else "" for h, i in idx.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=os.path.join(ROOT, "review", "results"))
    a = ap.parse_args()
    files = []
    for f in a.files:
        files += sorted(glob.glob(f)) or [f]
    results, errors, warns, facts_out = [], [], [], []
    all_ids = set()
    for path in files:
        pack, rname = reviewer_from_name(path)
        try:
            wb = load_workbook(path, data_only=True)
        except Exception as e:
            errors.append((os.path.basename(path), "-", f"파일을 열 수 없음: {e}")); continue
        if "문항검토" not in wb.sheetnames:
            errors.append((os.path.basename(path), "-", "'문항검토' 시트가 없음(양식이 바뀌었는지 확인)")); continue
        for i, row in enumerate(read_sheet(wb["문항검토"], HEAD_ROW), HEAD_ROW + 1):
            lid = row.get("문항번호", "")
            if not lid:
                continue
            all_ids.add((pack or lid.split("-")[0], lid))
            where = (os.path.basename(path), f"{lid} (행 {i})")
            crit = {c: row.get(c, "") for c in CRIT}
            final = row.get("최종 판정", ""); reviewer = row.get("검토자", "") or rname
            touched = final or any(crit.values()) or row.get("코멘트") or row.get("수정 제안(문구·정답)")
            if not touched:
                continue
            for c, v in crit.items():
                if v and v not in CRIT_OK:
                    errors.append((*where, f"{c}: '{v}' 는 허용값이 아님"))
            if final and final not in FINAL_OK:
                errors.append((*where, f"최종 판정 '{final}' 는 허용값이 아님"))
            if not final:
                errors.append((*where, "항목은 입력했는데 최종 판정이 비어 있음"))
            if not reviewer:
                errors.append((*where, "검토자 이름이 없음(열에 쓰거나 파일 이름 끝에 붙이세요)"))
            probs = [c for c, v in crit.items() if v in ("수정 필요", "부적합")]
            empty_c = [c for c, v in crit.items() if not v]
            if final and empty_c and final in ("승인", "수정 후 승인"):
                warns.append((*where, f"항목 {len(empty_c)}개가 비어 있음({', '.join(empty_c[:3])}{'…' if len(empty_c) > 3 else ''})"))
            if probs and not (row.get("수정 제안(문구·정답)") or row.get("코멘트")):
                errors.append((*where, f"'수정 필요/부적합' 항목({', '.join(probs)})이 있는데 제안이나 코멘트가 없음"))
            if final in ("보류", "폐기") and not row.get("코멘트"):
                errors.append((*where, f"'{final}' 인데 코멘트가 없음"))
            if final == "승인" and probs:
                warns.append((*where, f"'승인'인데 {', '.join(probs)} 에 문제 표시가 있음"))
            if final in ("수정 후 승인",) and not (row.get("수정 제안(문구·정답)") or row.get("코멘트")):
                errors.append((*where, "'수정 후 승인'인데 수정 제안이 없음"))
            results.append({"pack": pack or lid.split("-")[0], "local_id": lid, "reviewer": reviewer, "status": final or "입력 불완전", "final": final,
                            "criteria": crit, "suggestion": row.get("수정 제안(문구·정답)", ""), "comment": row.get("코멘트", ""), "date": row.get("검토일", ""),
                            "item_id": row.get("영어 item_id", ""), "domain": row.get("도메인", ""), "risk": row.get("위험축", ""),
                            "pair_id": row.get("pair_id", "")})
        if "사실·출처검증" in wb.sheetnames:
            for row in read_sheet(wb["사실·출처검증"], 1):
                if row.get("사실ID") and (row.get("원문 일치") or row.get("최신 여부") or row.get("수정 제안")):
                    facts_out.append({"pack": pack, "fact_id": row["사실ID"], "match": row.get("원문 일치", ""), "current": row.get("최신 여부", ""),
                                      "suggestion": row.get("수정 제안", ""), "reviewer": row.get("검토자", "") or rname, "date": row.get("검토일", "")})
                    if row.get("원문 일치") in ("불일치", "확인 불가") or row.get("최신 여부") in ("변경됨", "확인 불가"):
                        if not row.get("수정 제안"):
                            warns.append((os.path.basename(path), row["사실ID"], "사실 검증이 불일치/변경됨/확인 불가인데 수정 제안이 없음"))
    # 문항 하나를 둘 이상이 본 경우 판정 비교
    by_item = collections.defaultdict(list)
    for r in results:
        if r["final"]:
            by_item[(r["pack"], r["local_id"])].append(r)
    conflicts = []
    for k, lst in by_item.items():
        if len({x["final"] for x in lst}) > 1:
            conflicts.append((k, [(x["reviewer"], x["final"]) for x in lst]))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "review_results.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "review_results.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["팩", "문항번호", "검토자", "최종 판정"] + CRIT + ["수정 제안", "코멘트", "검토일"])
        for r in results:
            w.writerow([r["pack"], r["local_id"], r["reviewer"], r["status"]] + [r["criteria"][c] for c in CRIT] + [r["suggestion"], r["comment"], r["date"]])
    with open(os.path.join(a.out, "fact_review.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["팩", "사실ID", "원문 일치", "최신 여부", "수정 제안", "검토자", "검토일"])
        for r in facts_out:
            w.writerow([r["pack"], r["fact_id"], r["match"], r["current"], r["suggestion"], r["reviewer"], r["date"]])
    # 요약
    done = [r for r in results if r["final"]]
    decided = {(r["pack"], r["local_id"]) for r in done}
    dist = collections.Counter(r["final"] for r in done)
    L = ["# 전문가 검토 취합 요약", "", f"- 읽은 파일 {len(files)}개, 서로 다른 문항 {len(all_ids)}개 중 판정이 하나라도 있는 문항 {len(decided)}개(진행률 {100 * len(decided) // max(1, len(all_ids))}%), 판정 입력 {len(done)}건",
         f"- 최종 판정 분포: " + (", ".join(f"{k} {v}" for k, v in dist.most_common()) or "없음"), ""]
    per_pack = collections.defaultdict(collections.Counter)
    for r in done:
        per_pack[r["pack"]][r["final"]] += 1
    for pk, lid in all_ids - decided:
        per_pack[pk]["미검토"] += 1
    L += ["## 팩별", "| 팩 | " + " | ".join(["승인", "수정 후 승인", "보류", "폐기", "미검토"]) + " |", "|---|---|---|---|---|---|"]
    for p, c in sorted(per_pack.items()):
        L.append(f"| {p} | " + " | ".join(str(c.get(k, 0)) for k in ["승인", "수정 후 승인", "보류", "폐기", "미검토"]) + " |")
    crit_bad = collections.Counter()
    for r in done:
        for c, v in r["criteria"].items():
            if v in ("수정 필요", "부적합"):
                crit_bad[c] += 1
    L += ["", "## 확인 항목별 문제 건수(수정 필요 + 부적합)"] + [f"- {c}: {crit_bad.get(c, 0)}" for c in CRIT]
    todo = [r for r in done if r["final"] in ("수정 후 승인", "보류", "폐기")]
    L += ["", f"## 조치가 필요한 문항 ({len(todo)}개)"]
    for r in sorted(todo, key=lambda x: (x["final"], x["pack"], x["local_id"])):
        bad = [c for c, v in r["criteria"].items() if v in ("수정 필요", "부적합")]
        L.append(f"- **{r['local_id']}** [{r['final']}] {', '.join(bad)} — 제안: {r['suggestion'] or '-'} / 코멘트: {r['comment'] or '-'} ({r['reviewer']})")
    if conflicts:
        L += ["", f"## 검토자 간 판정이 다른 문항 ({len(conflicts)}개)"] + [f"- {k[1]}: " + ", ".join(f"{n}={v}" for n, v in lst) for k, lst in conflicts]
    if errors:
        L += ["", f"## 입력 오류 ({len(errors)}건) — 검토자에게 되돌려 고치게 하세요"] + [f"- {e[0]} / {e[1]}: {e[2]}" for e in errors]
    if warns:
        L += ["", f"## 확인 권장 ({len(warns)}건)"] + [f"- {e[0]} / {e[1]}: {e[2]}" for e in warns[:60]]
    open(os.path.join(a.out, "review_summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"문항 {len(all_ids)}, 판정 입력 {len(done)}, 입력 오류 {len(errors)}, 확인 권장 {len(warns)}, 검토자 간 불일치 {len(conflicts)}")
    print("결과:", a.out)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
