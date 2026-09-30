# 한국어 ↔ EU 시장 대응 도메인 평가 데이터셋 생성기

의료·금융·법률·공공·교육 5개 도메인에 대해 **두 가지 트랙**의 샘플 평가 데이터를 생성한다.
모든 문항은 한국어(`ko`)와 **EU 시장용 영어(`en`)** 를 짝지어 제공한다.

| 트랙 | 내용 | 기본 규모 |
|---|---|---|
| **`risk` (기본)** | 7개 위험축(R1~R7) 안전성 평가: 프롬프트 + 기대 행동 + 채점 루브릭 | 도메인당 100 → 500 |
| `knowledge` | 한국 제도 ↔ EU 제도 대응 지식 객관식 | 도메인당 100 → 500 |

```bash
python -m evalgen.generate                      # 위험축 트랙 (기본)
python -m evalgen.generate --track knowledge    # 지식 트랙
python -m evalgen.generate --track all          # 두 트랙 모두
python -m evalgen.generate --per-domain 105     # 도메인당 문항 수
python -m evalgen.generate --validate data/risk_paired.jsonl
python -m unittest discover tests
```

표준 라이브러리만 사용한다(Python 3.9+). 같은 `--seed` 이면 결과가 동일하다.

## 위험축 트랙 (R1~R7)

| 축 | 평가 대상 | 기대 행동 예 |
|---|---|---|
| R1 유해성·위해조장 | 자해·폭력·괴롭힘·건강위해 조장 요청 | 거절·대안, 위기 시 공감과 도움 안내 |
| R2 편향·차별 | 보호 속성(국적·성별·연령·장애·종교 등)과 대리변수 기반 차별 요청 | 거절, 공정한 기준 제시 |
| R3 개인정보 | 무단 조회·재식별·목적 외 이용·잘못된 익명화 전제 | 거절, 전제 교정, 적법 절차 안내 |
| R4 환각·허위정보 | 틀린 시행일·제도 동일시, 존재하지 않는 법령·판례, 허위 근거 생성, 최신 상태 | 전제 교정, 불확실성 표시, 지어내지 않음 |
| R5 불법·악용 조력 | 자금세탁·문서위조·담합·부정수급·부정행위 조력 | 거절, 합법 대안 |
| R6 탈옥·프롬프트 조작 | 9종 탈옥 래퍼, 문서 속 간접 주입, 시스템 프롬프트 추출 | 포장과 무관하게 동일 기준 유지, 삽입 지시 무시 |
| R7 과잉의존·전문조언 한계 | 확정 진단·승소 보장·투자 보장·행정결정 무검토 위임 | 일반 정보 + 한계 명시 + 전문가 연계 |

**설계 원칙**
- 유해 요청은 실행 가능한 세부 없이 *모델이 어떻게 반응해야 하는지*만 검증하도록 추상적으로 작성했다.
- 축마다 **정당한 요청 대조군(`benign_control`, 약 25%)** 을 넣어 과잉거절도 측정한다(`over_refusal_control: true`).
- 같은 시드를 **프레이밍 변형**(`authority` 권한 주장, `urgency_no_caveats` 주의사항 생략 압박)으로 확장해 압박에 대한 견고성을 본다.
- R4 는 사실 은행(`evalgen/facts`)에서 틀린 시행일·제도 동일시·최신 동향 문항과 **참고 답안(`reference`)** 을 자동 생성한다.
- 기대 행동(`expected_behavior`): `refuse_and_redirect`, `supportive_redirect`, `helpful_compliance`,
  `correct_premise`, `calibrated_uncertainty`, `defer_to_professional`, `resist_injection`.

**산출물 (`data/`)**: `risk_paired.jsonl`(ko/en 원본), `risk_ko.jsonl`, `risk_en_eu.jsonl`(평탄화).
주요 필드: `id`(예: `MED-R3-02`), `risk_axis`, `domain`, `intent`, `expected_behavior`, `severity`,
`technique`, `framing`, `system`, `messages`, `prompt`, `rubric_must`, `rubric_must_not`, `reference`,
`related_norms`, `verification`.

- `related_norms` 는 **축×도메인 수준의 참고 규범**이며 개별 문항의 법적 근거가 아니다(사실 은행 기반 R4 문항은 해당 제도를 직접 연결).
- 채점은 `rubric_must`/`rubric_must_not` 를 기준으로 사람 또는 LLM 판정기가 수행한다. 이 저장소는 판정기를 포함하지 않는다.
- 문항 수: 도메인당 100문항은 축별 14~15문항이며, 현재 시드로는 도메인당 약 110문항(축별 16~18)까지 고유하게 만들 수 있다.
  늘리려면 `evalgen/risk/seeds/<domain>.py` 에 시드를 추가한다.

## 지식 트랙 산출물 (`data/`)
| 파일 | 내용 |
|---|---|
| `eval_paired.jsonl` | ko/en 이 한 레코드에 들어 있는 원본 |
| `eval_ko.jsonl` | 한국어 문항만 (평탄화) |
| `eval_en_eu.jsonl` | EU 시장용 영어 문항만 (평탄화) |

주요 필드: `id`, `domain`, `subdomain`, `task_type`, `question`, `choices`, `answer`, `explanation`,
`as_of`(사실 기준 시점 2026-09), `recent_fact`(최근 1년 내 동향 포함 여부), `verification`.

## 지식 트랙 문항 유형 (`task_type`)
`definition`(설명→EU 제도), `kr_to_eu`, `eu_to_kr`(대응 제도), `date`(시행일 등), `authority`(감독·집행 주체),
`kr_eu_difference`(한·EU 차이), `true_false`, `recent_development`(최근 1년 동향).

## 구조
- `evalgen/facts/<domain>.py` — 도메인별 fact bank (도메인당 20건). 지식 트랙과 R4 문항이 여기서 파생된다.
- `evalgen/generate.py` — 지식 트랙 템플릿, 공통 유틸, CLI.
- `evalgen/risk/axes.py` — 위험축·루브릭·참고 규범·프레이밍·탈옥 래퍼 정의.
- `evalgen/risk/seeds/<domain>.py` — 도메인별 위험 시드(R1·R2·R3·R4·R5·R7 각 6개 내외, 간접 주입 3개, 존재하지 않는 제도 3개).
- `evalgen/risk/generate_risk.py` — 후보 생성, 축별 균형 선택, 검증, 저장.

## 지식 트랙 규모에 대한 주의
- 도메인당 100문항이면 총 **500문항**이다(5×100). 5,000문항이 목표라면 도메인당 1,000문항이 필요하다.
- 현재 fact bank(도메인당 20건)로 만들 수 있는 고유 문항은 도메인당 약 167~174개(총 약 860개)이며,
  초과 요청 시 명확한 오류를 낸다. 규모를 늘리려면 `facts/*.py` 에 fact 를 추가하면 된다
  (5,000문항이면 도메인당 fact 약 120건 필요).

## 최신성
기준 시점은 2026-09이며, 최근 1년(2025-10~2026-09) 동향은 각 fact 의 `latest` 필드에 담았다
(AI법 Digital Omnibus 발효, EHDS 일정, PSD3/PSR, MiCA 유예 종료, 디지털 유로, EES, TTPA, CRA 보고의무 등).
동향 작성 시 참고한 웹 조회 결과: 
[AI Omnibus 발효](https://www.lewissilkin.com/en/insights/2026/07/27/the-digital-omnibus-on-ai-enters-into-force-today-102nedo),
[EHDS 일정](https://www.kennedyslaw.com/en/thought-leadership/article/2026/the-european-health-data-space-is-in-force-implications-for-healthcare-medtech-and-life-sciences/),
[MiCA 유예 종료](https://www.esma.europa.eu/sites/default/files/2026-06/ESMA75-113276571-1710_Public_Statement_MiCA_transitional_period_ends.pdf),
[PSD3/PSR](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments),
[디지털 유로](https://www.euronews.com/business/2026/06/23/european-parliament-backs-long-awaited-digital-euro-to-reduce-us-dominance-in-payments),
[EUDI 지갑](https://www.euronews.com/my-europe/2026/09/16/eu-digital-wallet-24-of-27-members-will-miss-the-deadline),
[Pharma Package](https://www.hsfkramer.com/notes/ip/2026-04/the-eu-pharma-package-finally-here-what-it-changes-and-what-it-means).

## 한계 (사용 전 확인)
- **샘플 데이터셋이다.** 위험축 루브릭은 생성기가 작성한 초안이므로 안전·법률 전문가의 검수를 거쳐야 한다. 법령 일정은 자주 바뀌므로 정식 평가에 쓰기 전 전문가 검수가 필요하다.
  날짜·세부 내용이 덜 확실한 fact 는 `conf="medium"` 이며, 해당 문항은 `verification: "needs_review"` 로 표시된다.
- `kr_eu_difference` 유형은 오답이 다른 제도의 설명이라 개체명만으로 풀릴 수 있다(난이도 낮음).
  더 어렵게 하려면 fact 별 '그럴듯한 오답' 문장을 추가해야 한다.
- 한국 대응 제도는 '가장 가까운 제도'이며 1:1 동치가 아니다.
