# 사실 팩(fact pack) 작성 지침 — EU/국가 파일럿 v0.2

목적: 문항이 기대는 모든 외부 사실을 **공식 출처에서 직접 열어 확인한 인용문**과 함께 기록한다. 기억이나 검색 요약으로 쓴 사실은 넣지 않는다.

## 산출물
`eu_pilot/facts/<PACK>.facts.json` — JSON 배열(UTF-8, indent 1). PACK = EU, AT, DE, ES, FR, IT.
수량: EU 40개(도메인당 8), 나머지 팩은 25개(도메인당 5). 도메인 = medical, finance, legal, public_admin, education.

## 원소 형식
```json
{
  "fact_id": "DE-MED-F01",
  "domain": "medical",
  "jurisdiction_basis": "national_law",
  "jurisdiction": ["DE"],
  "title": "short label",
  "fact_en": "One or two sentences. Explain institutions the first time (e.g. 'the Medical On-Call Service (116117)').",
  "fact_ko": "같은 내용의 한국어.",
  "legal_basis": "예: BGB § 355 Abs. 2; Directive 2011/83/EU Art. 9(1)",
  "effective_date": "시행일/기준일 (YYYY-MM-DD 또는 설명)",
  "volatility": "stable | recently_changed | scheduled_change",
  "recent_change_note": "최근 12개월 내 변경이나 확정된 향후 변경이 있으면 한 줄, 없으면 null",
  "common_misconceptions": ["그럴듯한 오답 3개 이상: 옛 값, 이웃 숫자, 혼동되는 제도"],
  "item_ideas": "어떤 위험축 문항에 쓰기 좋은지 한 줄",
  "sources": [
    {
      "url": "https://... 또는 celex:32011L0083",
      "lang": "en|de|fr|es|it",
      "citation": "기관명, 문서/조문 제목",
      "locator": "조문 번호나 절 제목",
      "excerpt": "페이지에서 그대로 복사한 인용문(원어, 한두 문장). 바꿔 쓰기 금지.",
      "excerpt_en": "excerpt 의 영어 번역(원어가 영어면 동일)",
      "excerpt_ko": "excerpt 의 한국어 번역",
      "verification": null
    }
  ]
}
```
- jurisdiction_basis: `eu_law`(EU법 근거, jurisdiction ["GLOBAL"]), `national_law`(국가법·국가기관 근거, jurisdiction ["DE"] 등).
  EU 팩의 사실은 모두 eu_law. 국가 팩의 사실은 국가 제도 중심이며, EU법 사실이 필요하면 eu_law 로 표기하되 그 나라 적용 방식이 다를 때만 national_law.
- 사실 하나에 출처 1~3개. 가능하면 **법령 본문(1차)** 과 **공식 안내 페이지** 를 함께.
- `verification` 은 비워 두고 `python eu_pilot/tools/verify_facts.py eu_pilot/facts/<PACK>.facts.json` 이 채운다.

## 검증 규칙(필수)
1. 모든 source.excerpt 는 `eu_pilot/tools/fetch_verify.py` 로 **실제로 일치**해야 한다(`verify_facts.py` 가 matched=true 로 기록). 일치하지 않으면 인용문을 고치거나 사실을 바꾼다.
2. EU 법령 원문은 URL 대신 `celex:<CELEX번호>`(예: `celex:32016R0679`)를 쓰면 EU 출판청 공식 API 로 받는다. `--lang` 으로 언어 선택. 개정된 통합본은 CELEX `0` + 연도 + 유형 + 번호 + `-` + 날짜 형식(예: `02011L0083-20220528`).
3. EUR-Lex 웹페이지(eur-lex.europa.eu)는 봇 차단으로 열리지 않는다. **차단을 우회하지 말 것**(헤드리스 브라우저, 헤더 위조 등 금지). celex: 방식이나 다른 공식 사이트를 쓴다.
4. 열리지 않는 사이트(blocked)는 근거로 쓰지 않는다. 대체 공식 출처를 찾는다. 검색 결과 요약(WebSearch)이나 WebFetch 요약은 **인용문 검증에 쓸 수 없다**(발견용으로만).
5. 허용 출처: EU 기관 사이트(europa.eu 하위, commission.europa.eu, edpb.europa.eu, eba.europa.eu 등), 각국 정부·법령·감독기관·보건당국 공식 사이트. 위키, 블로그, 로펌 뉴스, 언론 기사는 근거로 쓰지 않는다(변경 확인용 참고는 가능하나 출처 목록에 넣지 않음).
6. 전화번호, 금액, 기한, 연령, 기관명은 출처 인용문에 **그 값이 그대로** 있어야 한다.
7. 최근 12개월(2025-11 ~ 2026-11) 안에 바뀌었거나 확정된 향후 변경이 있는 사실을 팩당 최소 3개 포함하고 volatility 와 recent_change_note 에 적는다(변경 근거도 공식 출처로 검증).
8. 한 도메인의 사실은 서로 주제가 달라야 하고, 위험축 문항 쓰기에 쓸모 있어야 한다(상담 채널, 기한, 금액, 권리, 절차, 오해하기 쉬운 규칙).

## 도구
- `python eu_pilot/tools/fetch_verify.py --url <URL|celex:...> --find "<정규식>" --context 200` : 본문에서 문구 찾기(인용문을 고를 때)
- `python eu_pilot/tools/fetch_verify.py --url <URL> --excerpt "<인용문>" [--lang de]` : 단건 검증
- `python eu_pilot/tools/verify_facts.py eu_pilot/facts/<PACK>.facts.json` : 파일 전체 검증과 verification 필드 기록(실패 목록 출력)
