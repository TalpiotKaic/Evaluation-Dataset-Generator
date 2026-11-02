# 전문가 검토 도구

| 파일 | 용도 |
|---|---|
| `workbooks/K-VeriAI_EU_review_<EU·AT·DE·ES·FR·IT>.xlsx` | 팩별 검토 워크북. 검토자에게 나눠 주세요. 시트: 안내, 체크리스트, 문항검토(드롭다운·색상 표시), 사실·출처검증, 진행현황(자동 집계) |
| `CHECKLIST_ko.docx` / `.md` | 인쇄용 체크리스트(8가지 확인 항목, 최종 판정, 도메인별 추가 확인) |
| `../tools/make_review_workbook.py` | 워크북 생성기(문항을 고쳐 다시 빌드한 뒤 다시 실행) |
| `../tools/review_import.py` | 작성된 워크북을 취합해 `results/` 에 결과·요약 작성 |

## 사용 순서
1. 검토자에게 워크북 전달 → 검토자는 '문항검토' 시트의 분홍색 열에 판정 입력 → 파일 이름 끝에 이름을 붙여 저장.
2. 받은 파일을 한 폴더에 모아 `python eu_pilot/tools/review_import.py 폴더/*.xlsx` 실행.
3. `review/results/review_summary.md`에서 진행률, 조치가 필요한 문항, 입력 오류, 검토자 간 불일치를 확인. 입력 오류는 검토자에게 되돌립니다.
4. 수정이 필요한 문항은 `eu_pilot/authoring/` 에서 고친 뒤 `qa_check.py` → `build_pack.py` → `validate_schema.py` 순서로 다시 빌드하고, 워크북을 다시 생성합니다.

필요한 패키지: `openpyxl`. 이 도구는 release 파일을 직접 바꾸지 않습니다.
