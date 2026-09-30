# 한국어 ↔ EU 시장 대응 도메인 평가 데이터셋 생성기

의료·금융·법률·공공·교육 5개 도메인에 대해, 한국 제도와 **EU 시장에서 쓰이는 대응 제도·용어**를
짝지어 묻는 샘플 평가 문항(객관식·참/거짓)을 생성한다. 모든 문항은 동일한 사실을
**한국어(`ko`)** 와 **EU 시장용 영어(`en`)** 로 함께 제공하며, 보기 순서와 정답은 두 언어에서 같다.

```bash
python -m evalgen.generate                    # 도메인당 100문항 → 총 500문항 (기본)
python -m evalgen.generate --per-domain 150   # 도메인당 150문항
python -m evalgen.generate --validate data/eval_paired.jsonl
python -m unittest discover tests
```

표준 라이브러리만 사용한다(Python 3.9+). 같은 `--seed` 이면 결과가 동일하다.

## 산출물 (`data/`)
| 파일 | 내용 |
|---|---|
| `eval_paired.jsonl` | ko/en 이 한 레코드에 들어 있는 원본 |
| `eval_ko.jsonl` | 한국어 문항만 (평탄화) |
| `eval_en_eu.jsonl` | EU 시장용 영어 문항만 (평탄화) |

주요 필드: `id`, `domain`, `subdomain`, `task_type`, `question`, `choices`, `answer`, `explanation`,
`as_of`(사실 기준 시점 2026-09), `recent_fact`(최근 1년 내 동향 포함 여부), `verification`.

## 문항 유형 (`task_type`)
`definition`(설명→EU 제도), `kr_to_eu`, `eu_to_kr`(대응 제도), `date`(시행일 등), `authority`(감독·집행 주체),
`kr_eu_difference`(한·EU 차이), `true_false`, `recent_development`(최근 1년 동향).

## 구조
- `evalgen/facts/<domain>.py` — 도메인별 fact bank (도메인당 20건). 문항은 모두 여기서 파생된다.
- `evalgen/generate.py` — 문항 템플릿, 오답 보기 선택(유사 보기 제외), 균형 선택, 검증, 저장.

## 규모에 대한 주의
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
- **샘플 데이터셋이다.** 법령 일정은 자주 바뀌므로 정식 평가에 쓰기 전 전문가 검수가 필요하다.
  날짜·세부 내용이 덜 확실한 fact 는 `conf="medium"` 이며, 해당 문항은 `verification: "needs_review"` 로 표시된다.
- `kr_eu_difference` 유형은 오답이 다른 제도의 설명이라 개체명만으로 풀릴 수 있다(난이도 낮음).
  더 어렵게 하려면 fact 별 '그럴듯한 오답' 문장을 추가해야 한다.
- 한국 대응 제도는 '가장 가까운 제도'이며 1:1 동치가 아니다.
