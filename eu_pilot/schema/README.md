# 스키마와 검증기

- `items.schema.v0.9.json`, `answer_keys.schema.v0.9.json`: Drive의 합의 폴더(v0.9.3 / schema)에 있던 스키마를 그대로 옮겼습니다(JSON Schema 2020-12).
- relations, sources, facts, release_manifest는 Drive에 합의된 스키마가 없어서, 빌드 산출물 구조에서 뽑은 **파생 스키마**를 `tools/validate_schema.py` 안에 두었습니다. 합의본이 생기면 교체하세요.

## 실행
    python eu_pilot/tools/validate_schema.py              # 6개 팩 모두
    python eu_pilot/tools/validate_schema.py IT DE        # 지정 팩
    python eu_pilot/tools/validate_schema.py --json out.json
오류가 있으면 종료 코드 1입니다. 필요 패키지: `jsonschema` (4.x).

## 점검 내용
1. 스키마: 필수 키, 열거값, 정규식, 선택지 4개, R6의 target_risk, 날짜 형식 등.
2. 파일 간 정합성: ID 유일성, display_code와 domain·위험축·언어 일치, 선택지 라벨 A~D·display_order, 정답 키와 선택지 대응(점수 1은 정답 하나), error_type 'correct'와 정답 일치, expected_refusal과 정답의 refusal_label 일치, 영어↔한국어 번역 관계와 정답 대응, source_refs·fact_ids 참조 해소, 관할 규칙(national_law→해당 국가, eu_law·synthetic→GLOBAL), 사실의 verified, 매니페스트 sha256·counts·items 일치.

## 테스트
    python -m unittest discover -s eu_pilot/tests -v
복사본에 오류를 일부러 넣어 검증기가 잡는지 확인하는 부정 테스트 10개입니다.
