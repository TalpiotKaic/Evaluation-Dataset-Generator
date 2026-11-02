#!/usr/bin/env python3
"""사람 전문가 검토용 엑셀 워크북 생성기.

팩별로 release/<PACK>/ 의 영어·한국어 문항, 정답, 사실, 출처를 읽어
review/workbooks/K-VeriAI_EU_review_<PACK>.xlsx 를 만든다.
시트: 안내 / 체크리스트 / 문항검토 / 사실·출처검증 / 진행현황 / (숨김)목록

사용:
  python make_review_workbook.py            # 6개 팩 모두
  python make_review_workbook.py IT DE      # 지정 팩
  python make_review_workbook.py --out DIR
작성된 워크북은 review_import.py 로 읽어 결과를 모은다.
"""
import argparse, collections, json, os, sys
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = ["EU", "AT", "DE", "ES", "FR", "IT"]
DOM_KO = {"medical": "의료", "finance": "금융", "legal": "법률", "public_admin": "공공", "education": "교육"}
RISK_KO = {"R1": "유해성·위해조장", "R2": "편향·차별", "R3": "개인정보", "R4": "환각·허위정보", "R5": "불법·악용 조력", "R6": "탈옥·프롬프트 조작", "R7": "과잉의존·전문조언 한계"}
CLASS_KO = {"benign": "정상 요청", "risky": "위험 요청", "attack": "공격 요청"}

# 판정 값(가져오기 도구와 공유)
CRIT_VALUES = ["적합", "수정 필요", "부적합", "해당 없음"]
FINAL_VALUES = ["승인", "수정 후 승인", "보류", "폐기"]
CRITERIA = [  # (키, 열 제목, 확인할 것)
    ("c_fact", "①사실 정확성", "상황·정답·선택지에 쓰인 사실(수치, 기간, 기관, 법 내용)이 맞고 기준일(2026-11-01)에 유효한가. 사실 팩에 없는 내용이 들어 있지 않은가."),
    ("c_key", "②정답 유일성", "정답이 하나뿐인가. 다른 선택지도 방어 가능하거나 정답과 같은 말이면 '수정 필요'. 정답이 상황 정보만으로 정해지는가."),
    ("c_distr", "③오답 적절성", "각 오답이 의도한 오류 유형(거절 과다, 허위 사실, 위험 순응, 얼버무림 등)을 대표하는가. 너무 터무니없거나(명백) 실제로 맞는 말이면 안 된다."),
    ("c_pair", "④쌍 설계", "짝 문항과 선택지는 같고 상황의 사실만 달라 정답이 바뀌는가. 상황 외에 다른 차이가 정답을 좌우하지 않는가."),
    ("c_risk", "⑤위험·안전 판단", "이 문항의 '가장 적절한 응답'이 안전·윤리상 옳은가. 유해한 조력을 정답으로 삼거나, 정당한 요청을 거절하는 응답을 정답으로 삼지 않았는가."),
    ("c_trans", "⑥한국어 번역", "한국어가 영어와 뜻이 같고 자연스러운가. 숫자·기관명·조건이 빠지거나 바뀌지 않았는가. 정답이 한국어에서도 같은 선택지인가."),
    ("c_local", "⑦관할·현지화", "해당 국가(또는 EU) 맥락이 맞는가. 다른 나라 제도가 섞이지 않았는가. 용어가 현지에서 통하는가."),
    ("c_cue", "⑧표면 단서", "정답이 가장 길거나, 문체·어조·특정 표현만으로 추측되지 않는가. 정답 위치(A~D) 외에 단서가 없는가."),
]
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = {"info": PatternFill("solid", fgColor="D9E2F3"), "en": PatternFill("solid", fgColor="E2EFDA"),
            "ko": PatternFill("solid", fgColor="FFF2CC"), "ref": PatternFill("solid", fgColor="EDEDED"),
            "rev": PatternFill("solid", fgColor="FCE4D6")}
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def rd(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_pack(pack):
    d = os.path.join(ROOT, "release", pack)
    en = rd(f"{d}/items_en_draft.jsonl"); ko = rd(f"{d}/items_ko_reverse_draft.jsonl")
    ken = {k["item_ref"]["item_id"]: k for k in rd(f"{d}/answer_keys_en_draft.jsonl")}
    srcs = {s["source_id"]: s for s in rd(f"{d}/sources_draft.jsonl")}
    facts = {f["fact_id"]: f for f in rd(f"{d}/facts_draft.jsonl")}
    rel = rd(f"{d}/relations_draft.jsonl")
    tr = {r["source_item_id"]: r["target_item_id"] for r in rel if r["derivation_type"] == "translation"}
    ko_by_id = {i["item_id"]: i for i in ko}
    hints = {}
    hp = os.path.join(ROOT, "..", "dist", "blind_review", f"{pack}_findings.json")
    if not os.path.exists(hp):
        hp = f"/tmp/claude-0/{pack}_findings.json"
    if os.path.exists(hp):
        for x in json.load(open(hp, encoding="utf-8")):
            tag = ("키와 다르게 풂 " if x["disagrees_with_key"] else "") + ("모호·의심 표시 " if x["flagged_ambiguous_or_doubtful"] else "")
            hints[x["local_id"]] = (tag.strip() + (": " + x["solver_note"] if x.get("solver_note") else "")).strip()
    return en, ko_by_id, ken, srcs, facts, tr, hints


def style_header(ws, row, fills, widths=None):
    for c in ws[row]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD_FILL; c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = BORDER
    ws.row_dimensions[row].height = 34


def build(pack, outdir):
    en, ko_by_id, ken, srcs, facts, tr, hints = load_pack(pack)
    wb = Workbook()
    # ---------- 목록(숨김) ----------
    ls = wb.create_sheet("목록")
    for j, vals in enumerate([CRIT_VALUES, FINAL_VALUES], 1):
        for i, v in enumerate(vals, 1):
            ls.cell(i, j, v)
    ls.sheet_state = "hidden"

    # ---------- 안내 ----------
    ws = wb.active; ws.title = "안내"
    lines = [
        (f"K-VeriAI EU 파일럿 v0.2 — {pack} 팩 전문가 검토 워크북", "title"),
        ("", None),
        ("이 파일은 AI가 만든 초안을 사람 전문가가 확인하기 위한 것입니다. 모든 문항은 아직 '검토 필요(needs_review)' 상태입니다.", None),
        ("", None),
        ("■ 검토 순서", "h"),
        ("1. '체크리스트' 시트에서 8가지 확인 항목의 뜻을 읽습니다.", None),
        ("2. '문항검토' 시트에서 문항을 한 줄씩 읽고, 분홍색 열(검토자 입력)에 판정을 고릅니다. 칸을 누르면 드롭다운이 나옵니다.", None),
        ("   · 항목별: 적합 / 수정 필요 / 부적합 / 해당 없음   · 최종 판정: 승인 / 수정 후 승인 / 보류 / 폐기", None),
        ("   · '수정 필요'나 '부적합'을 고르면 '수정 제안'이나 '코멘트'에 이유와 고칠 문구를 적어 주세요.", None),
        ("   · 쌍 문항(같은 pair_id)은 서로 비교해서 ④쌍 설계를 판단합니다. 같은 pair_id 로 정렬하거나 필터하면 편합니다.", None),
        ("3. 사실 근거는 '사실·출처검증' 시트에서 출처 링크를 열어 원문과 대조하고 판정을 입력합니다. 문항검토 시트의 사실ID로 찾을 수 있습니다.", None),
        ("4. '진행현황' 시트는 입력하면 자동으로 집계됩니다.", None),
        ("5. 끝나면 파일 이름 끝에 검토자 이름을 붙여 저장해 돌려 주세요(예: ..._IT_홍길동.xlsx). 취합 프로그램(review_import.py)이 읽습니다.", None),
        ("", None),
        ("■ 지켜 주세요", "h"),
        ("· 헤더 행(1~2행), 열 이름, 회색·초록·노랑 열(문항 내용)은 고치지 마세요. 취합 프로그램이 열 이름으로 읽습니다.", None),
        ("· 정답을 바꾸고 싶으면 문항 내용을 직접 고치지 말고 '수정 제안'에 '정답을 C로' 처럼 적어 주세요. 원본은 담당자가 고쳐서 다시 빌드합니다.", None),
        ("· 한 문항을 두 사람이 보는 경우 서로의 판정을 보지 말고 독립적으로 입력해 주세요.", None),
        ("· 'AI 블라인드 검수 표시' 열은 AI가 풀어 본 결과의 참고용입니다. 그 표시와 상관없이 직접 판단해 주세요.", None),
        ("", None),
        ("■ 용어", "h"),
        ("· 쌍(pair): 선택지는 같고 상황의 사실만 바뀌어 정답이 달라지는 두 문항. 역할(pair_role) 열 참고.", None),
        ("· 위험 요청 / 정상 요청 / 공격 요청: 해로운 일을 시키는 요청 / 정당한 요청 / 프롬프트 조작이 섞인 요청.", None),
        ("· 정답 사유: 정답 선택지가 왜 맞는지에 대한 작성자의 설명입니다. 틀렸다고 보면 코멘트에 적어 주세요.", None),
    ]
    for i, (t, k) in enumerate(lines, 1):
        c = ws.cell(i, 1, t); c.alignment = Alignment(wrap_text=True, vertical="top")
        if k == "title": c.font = Font(bold=True, size=15, color="1F3864")
        elif k == "h": c.font = Font(bold=True, size=12, color="1F3864")
    ws.column_dimensions["A"].width = 130

    # ---------- 체크리스트 ----------
    cs = wb.create_sheet("체크리스트")
    cs.append(["번호", "확인 항목", "무엇을 확인하나", "판정 기준", "자주 보이는 문제"])
    style_header(cs, 1, None)
    common = {
        "c_fact": "수치·기간이 사실 팩과 다름 / 사실 팩에 없는 법조문·기관 이름 / 개정 전 규정",
        "c_key": "정답과 같은 말을 하는 오답 / 정답이 '상황에 없는 정보'에 의존",
        "c_distr": "오답이 한눈에 틀려 보임 / 오답이 사실은 맞는 말 / 거절 문구만 다르고 같은 오답이 둘",
        "c_pair": "짝 문항에서 상황 외 다른 부분도 달라짐 / 짝에서도 같은 정답이 됨",
        "c_risk": "위험 요청에 도움을 주는 선택지가 정답 / 정당한 요청을 거절하는 선택지가 정답 / 자해·위기 대응 문구가 부실",
        "c_trans": "숫자·고유명사 누락 / 어색한 직역 / 영어에 없는 말이 추가됨",
        "c_local": "다른 나라 기관·제도 혼입 / 현지에서 쓰지 않는 용어",
        "c_cue": "정답이 가장 길고 구체적 / 정답에만 완곡·공손한 어조가 붙음 / 오답에 '절대', '항상' 같은 극단 표현",
    }
    for n, (k, t, d) in enumerate(CRITERIA, 1):
        cs.append([n, t, d, "적합: 문제 없음 · 수정 필요: 고치면 쓸 수 있음 · 부적합: 고쳐도 어려움 · 해당 없음: 이 문항에는 적용되지 않음", common[k]])
    cs.append([9, "최종 판정", "위 항목을 종합한 문항 단위 결정", "승인: 그대로 사용 · 수정 후 승인: 제안대로 고치면 사용 · 보류: 추가 확인 필요(코멘트 필수) · 폐기: 문항 삭제 권고(코멘트 필수)", ""])
    for col, w in zip("ABCDE", (7, 20, 70, 60, 60)):
        cs.column_dimensions[col].width = w
    for r in cs.iter_rows(min_row=2):
        for c in r:
            c.alignment = WRAP; c.border = BORDER
        cs.row_dimensions[r[0].row].height = 62
    cs.freeze_panes = "A2"

    # ---------- 문항검토 ----------
    rv = wb.create_sheet("문항검토")
    cols = [  # (제목, 그룹, 너비)
        ("문항번호", "info", 14), ("영어 item_id", "info", 12), ("한국어 item_id", "info", 12), ("도메인", "info", 8), ("위험축", "info", 16), ("세부유형", "info", 18),
        ("pair_id", "info", 14), ("pair_role", "info", 12), ("요청유형", "info", 9), ("관할", "info", 8),
        ("[EN] 상황", "en", 52), ("[EN] 질문", "en", 26), ("[EN] A", "en", 40), ("[EN] B", "en", 40), ("[EN] C", "en", 40), ("[EN] D", "en", 40), ("정답", "en", 6), ("[EN] 정답 사유(작성자)", "en", 40),
        ("[KO] 상황", "ko", 52), ("[KO] A", "ko", 40), ("[KO] B", "ko", 40), ("[KO] C", "ko", 40), ("[KO] D", "ko", 40),
        ("사실ID", "ref", 16), ("사실 요약(EN)", "ref", 44), ("출처(URL)", "ref", 40), ("AI 블라인드 검수 표시", "ref", 30),
    ] + [(t, "rev", 12) for _, t, _ in CRITERIA] + [("최종 판정", "rev", 13), ("수정 제안(문구·정답)", "rev", 40), ("코멘트", "rev", 40), ("검토자", "rev", 10), ("검토일", "rev", 11)]
    # 1행: 그룹 라벨, 2행: 열 제목 (취합 도구는 2행을 헤더로 읽음)
    groups = [("info", "문항 정보"), ("en", "영어 원문"), ("ko", "한국어 역번역"), ("ref", "근거·참고"), ("rev", "검토자 입력")]
    col = 1
    for g, label in groups:
        n = sum(1 for _, gg, _ in cols if gg == g)
        rv.cell(1, col, label); rv.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + n - 1)
        for cc in range(col, col + n):
            rv.cell(1, cc).fill = SUB_FILL[g]; rv.cell(1, cc).font = Font(bold=True); rv.cell(1, cc).alignment = Alignment(horizontal="center")
        col += n
    for j, (t, g, w) in enumerate(cols, 1):
        rv.cell(2, j, t); rv.column_dimensions[get_column_letter(j)].width = w
    style_header(rv, 2, None)
    idx = {t: j for j, (t, _, _) in enumerate(cols, 1)}
    rows = sorted(en, key=lambda i: i["metadata"]["extensions"]["local_id"])
    r = 3
    for it in rows:
        md = it["metadata"]; ex = md["extensions"]; k = ken[it["item_id"]]
        ko = ko_by_id[tr[it["item_id"]]]
        o = {x["option_id"]: x for x in it["input"]["options"]}
        label = next(x["label"] for x in it["input"]["options"] if x["option_id"] == k["correct_option_id"])
        reason = next(s["reason"] for s in k["option_scores"] if s["option_id"] == k["correct_option_id"])
        fids = ex.get("fact_ids") or []
        fsum = "\n".join(f"[{f}] {facts[f]['fact_en']}" for f in fids if f in facts)
        urls = []
        for sr in md["source_refs"]:
            s = srcs.get(sr)
            if s and s.get("source_type") != "synthetic":
                urls.append(f"{sr}: {s['locator']}")
        vals = {
            "문항번호": ex["local_id"], "영어 item_id": it["item_id"], "한국어 item_id": ko["item_id"], "도메인": DOM_KO[md["domain"]],
            "위험축": f"{md['primary_risk']} {RISK_KO[md['primary_risk']]}", "세부유형": md["risk_subtype"], "pair_id": ex["pair_id"],
            "pair_role": ex["pair_role"], "요청유형": CLASS_KO[md["request_class"]], "관할": "·".join(md["jurisdiction"]),
            "[EN] 상황": it["input"]["context"], "[EN] 질문": it["input"]["question"],
            "[EN] A": it["input"]["options"][0]["text"], "[EN] B": it["input"]["options"][1]["text"], "[EN] C": it["input"]["options"][2]["text"], "[EN] D": it["input"]["options"][3]["text"],
            "정답": label, "[EN] 정답 사유(작성자)": reason,
            "[KO] 상황": ko["input"]["context"], "[KO] A": ko["input"]["options"][0]["text"], "[KO] B": ko["input"]["options"][1]["text"],
            "[KO] C": ko["input"]["options"][2]["text"], "[KO] D": ko["input"]["options"][3]["text"],
            "사실ID": ", ".join(fids), "사실 요약(EN)": fsum or "(사실 팩 미사용: 합성 상황)", "출처(URL)": "\n".join(urls) or "(없음: 합성 상황)",
            "AI 블라인드 검수 표시": hints.get(ex["local_id"], ""),
        }
        for t, v in vals.items():
            c = rv.cell(r, idx[t], v); c.alignment = WRAP; c.border = BORDER
        # 정답 칸 강조, 정답 선택지 연한 초록
        rv.cell(r, idx["정답"]).font = Font(bold=True, color="C00000"); rv.cell(r, idx["정답"]).alignment = Alignment(horizontal="center", vertical="top")
        gfill = PatternFill("solid", fgColor="C6E0B4")
        rv.cell(r, idx[f"[EN] {label}"]).fill = gfill; rv.cell(r, idx[f"[KO] {label}"]).fill = gfill
        for t in [t for _, t, _ in CRITERIA] + ["최종 판정", "수정 제안(문구·정답)", "코멘트", "검토자", "검토일"]:
            c = rv.cell(r, idx[t]); c.border = BORDER; c.alignment = WRAP
        rv.row_dimensions[r].height = 230
        r += 1
    last = r - 1
    dv1 = DataValidation(type="list", formula1="=목록!$A$1:$A$4", allow_blank=True, showErrorMessage=True, errorTitle="입력값", error="목록에서 고르세요.")
    dv2 = DataValidation(type="list", formula1="=목록!$B$1:$B$4", allow_blank=True, showErrorMessage=True, errorTitle="입력값", error="목록에서 고르세요.")
    dv3 = DataValidation(type="date", operator="greaterThan", formula1="43831", allow_blank=True, showErrorMessage=True, error="날짜(예: 2026-11-05)로 입력하세요.")
    rv.add_data_validation(dv1); rv.add_data_validation(dv2); rv.add_data_validation(dv3)
    c0, c1 = idx[CRITERIA[0][1]], idx[CRITERIA[-1][1]]
    dv1.add(f"{get_column_letter(c0)}3:{get_column_letter(c1)}{last}")
    fcol = get_column_letter(idx["최종 판정"]); dv2.add(f"{fcol}3:{fcol}{last}")
    dcol = get_column_letter(idx["검토일"]); dv3.add(f"{dcol}3:{dcol}{last}");
    for cc in range(idx["검토일"], idx["검토일"] + 1):
        for rr in range(3, last + 1):
            rv.cell(rr, cc).number_format = "yyyy-mm-dd"
    rng = f"{get_column_letter(c0)}3:{get_column_letter(c1)}{last}"
    rv.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"수정 필요"'], fill=PatternFill("solid", bgColor="FFE699")))
    rv.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"부적합"'], fill=PatternFill("solid", bgColor="F4B084")))
    rv.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"적합"'], fill=PatternFill("solid", bgColor="C6E0B4")))
    frng = f"{fcol}3:{fcol}{last}"
    for v, colr in (("승인", "A9D08E"), ("수정 후 승인", "FFE699"), ("보류", "BDD7EE"), ("폐기", "F4B084")):
        rv.conditional_formatting.add(frng, CellIsRule(operator="equal", formula=[f'"{v}"'], fill=PatternFill("solid", bgColor=colr)))
    rv.freeze_panes = rv.cell(3, idx["[EN] 상황"])
    rv.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{last}"
    rv.sheet_view.zoomScale = 90

    # ---------- 사실·출처검증 ----------
    fs = wb.create_sheet("사실·출처검증")
    fcols = [("사실ID", 14), ("도메인", 8), ("관할", 8), ("제목", 26), ("사실(EN)", 56), ("사실(KO)", 50), ("근거(법·기관)", 30), ("변동성", 14), ("출처 링크", 46), ("AI 대조 결과", 18), ("쓰인 문항", 24),
             ("원문 일치", 12), ("최신 여부", 12), ("수정 제안", 40), ("검토자", 10), ("검토일", 11)]
    fs.append([t for t, _ in fcols])
    style_header(fs, 1, None)
    for j, (t, w) in enumerate(fcols, 1):
        fs.column_dimensions[get_column_letter(j)].width = w
    used_by = collections.defaultdict(list)
    for it in rows:
        for f in it["metadata"]["extensions"].get("fact_ids") or []:
            used_by[f].append(it["metadata"]["extensions"]["local_id"])
    for fid, f in sorted(facts.items()):
        links = []
        ver = []
        for sr in f.get("source_refs", []):
            s = srcs.get(sr)
            if s:
                links.append(f"{sr}: {s['locator']}")
                v = s.get("verified")
                ver.append("통과" if v else "미확인")
        vals = [fid, DOM_KO.get(f["domain"], f["domain"]), "·".join(f["jurisdiction"]), f["title"], f["fact_en"], f["fact_ko"], f["legal_basis"], f["volatility"],
                "\n".join(links), "AI 대조 " + "/".join(sorted(set(ver))), ", ".join(used_by.get(fid, [])) or "(미사용)", None, None, None, None, None]
        fs.append(vals)
    fl = fs.max_row
    for row in fs.iter_rows(min_row=2, max_row=fl):
        for c in row:
            c.alignment = WRAP; c.border = BORDER
        fs.row_dimensions[row[0].row].height = 120
        for c in row[11:]:
            c.fill = SUB_FILL["rev"]
        row[15].number_format = "yyyy-mm-dd"
    dvm = DataValidation(type="list", formula1='"일치,불일치,확인 불가"', allow_blank=True); dvn = DataValidation(type="list", formula1='"최신,변경됨,확인 불가"', allow_blank=True)
    fs.add_data_validation(dvm); fs.add_data_validation(dvn)
    dvm.add(f"L2:L{fl}"); dvn.add(f"M2:M{fl}")
    fs.conditional_formatting.add(f"L2:M{fl}", CellIsRule(operator="equal", formula=['"불일치"'], fill=PatternFill("solid", bgColor="F4B084")))
    fs.conditional_formatting.add(f"L2:M{fl}", CellIsRule(operator="equal", formula=['"변경됨"'], fill=PatternFill("solid", bgColor="F4B084")))
    fs.conditional_formatting.add(f"L2:M{fl}", CellIsRule(operator="equal", formula=['"확인 불가"'], fill=PatternFill("solid", bgColor="FFE699")))
    fs.freeze_panes = "E2"; fs.auto_filter.ref = f"A1:{get_column_letter(len(fcols))}{fl}"

    # ---------- 진행현황 ----------
    pg = wb.create_sheet("진행현황")
    S = "'문항검토'!"
    fcl = get_column_letter(idx["최종 판정"]); dom = get_column_letter(idx["도메인"]); rk = get_column_letter(idx["위험축"])
    rngf = f"{S}${fcl}$3:${fcl}${last}"
    pg["A1"] = "진행현황 (자동 집계)"; pg["A1"].font = Font(bold=True, size=14, color="1F3864")
    pg["A3"] = "전체 문항"; pg["B3"] = f"=COUNTA({S}$A$3:$A${last})"
    pg["A4"] = "검토 완료(최종 판정 입력)"; pg["B4"] = f"=COUNTA({rngf})"
    pg["A5"] = "진행률"; pg["B5"] = "=IF(B3=0,0,B4/B3)"; pg["B5"].number_format = "0%"
    hdr = ["", "승인", "수정 후 승인", "보류", "폐기", "미검토", "합계"]
    pg.append([]); pg["A7"] = "도메인별"
    for j, h in enumerate(hdr, 1):
        pg.cell(8, j, h)
    rr = 9
    for dname in DOM_KO.values():
        pg.cell(rr, 1, dname)
        for j, v in enumerate(FINAL_VALUES, 2):
            pg.cell(rr, j, f'=COUNTIFS({S}${dom}$3:${dom}${last},$A{rr},{rngf},"{v}")')
        pg.cell(rr, 7, f'=COUNTIF({S}${dom}$3:${dom}${last},$A{rr})'); pg.cell(rr, 6, f"=G{rr}-SUM(B{rr}:E{rr})")
        rr += 1
    pg.cell(rr, 1, "합계")
    for j in range(2, 8):
        L = get_column_letter(j); pg.cell(rr, j, f"=SUM({L}9:{L}{rr - 1})")
    rr += 2; pg.cell(rr, 1, "위험축별")
    for j, h in enumerate(hdr, 1):
        pg.cell(rr + 1, j, h)
    rr += 2; r0 = rr
    for rkey, rname in RISK_KO.items():
        pg.cell(rr, 1, f"{rkey} {rname}")
        for j, v in enumerate(FINAL_VALUES, 2):
            pg.cell(rr, j, f'=COUNTIFS({S}${rk}$3:${rk}${last},$A{rr},{rngf},"{v}")')
        pg.cell(rr, 7, f'=COUNTIF({S}${rk}$3:${rk}${last},$A{rr})'); pg.cell(rr, 6, f"=G{rr}-SUM(B{rr}:E{rr})")
        rr += 1
    rr += 1; pg.cell(rr, 1, "확인 항목별 문제 건수"); pg.cell(rr + 1, 1, "항목"); pg.cell(rr + 1, 2, "수정 필요"); pg.cell(rr + 1, 3, "부적합")
    rr += 2
    for _, t, _ in CRITERIA:
        L = get_column_letter(idx[t]); pg.cell(rr, 1, t)
        pg.cell(rr, 2, f'=COUNTIF({S}${L}$3:${L}${last},"수정 필요")'); pg.cell(rr, 3, f'=COUNTIF({S}${L}$3:${L}${last},"부적합")'); rr += 1
    for row in pg.iter_rows(min_row=8, max_row=rr):
        for c in row:
            if c.value not in (None, ""):
                c.border = BORDER
    for rowi in (8, 9 + len(DOM_KO) + 3):
        for c in pg[rowi]:
            if c.value:
                c.font = Font(bold=True); c.fill = SUB_FILL["info"]
    pg.column_dimensions["A"].width = 30
    for L in "BCDEFG":
        pg.column_dimensions[L].width = 13
    pg["A5"].font = Font(bold=True); pg["B5"].font = Font(bold=True)

    wb._sheets = [wb["안내"], wb["체크리스트"], wb["문항검토"], wb["사실·출처검증"], wb["진행현황"], wb["목록"]]
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"K-VeriAI_EU_review_{pack}.xlsx")
    wb.save(path)
    return path, len(rows), len(facts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("packs", nargs="*")
    ap.add_argument("--out", default=os.path.join(ROOT, "review", "workbooks"))
    a = ap.parse_args()
    for p in a.packs or PACKS:
        path, n, nf = build(p, a.out)
        print(f"{p}: 문항 {n}, 사실 {nf} -> {path} ({os.path.getsize(path)//1024} KB)")


if __name__ == "__main__":
    main()
