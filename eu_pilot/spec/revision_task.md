# 팩 보정(revision) 작업 지시서

너는 K-VeriAI EU/국가 파일럿 v0.2 의 **팩 하나(PACK)** 를 보정하는 편집자다. 문항은 이미 작성되어 있다(`eu_pilot/authoring/<PACK>/<domain>/R1~R7.json`). 새로 쓰지 말고 **제자리에서 고친다**. 기준 문서: `eu_pilot/spec/authoring_rules.md`, 사실 팩 `eu_pilot/facts/<PACK>.facts.json`. 먼저 `cd /home/user/globalRnD && python3 eu_pilot/tools/qa_check.py <PACK>` 을 돌려 현황을 본다.

## 고칠 것(우선순위)
1. **ERROR 전부.** 특히 "option sentence appears in N different pairs": 대개 abstain 문구("It cannot be determined from the information given")가 여러 쌍에서 반복된 것이다. abstain 은 한 쌍 안에서는 동일, 쌍 사이에서는 서로 달라야 한다. 허용 문구 5종: "It cannot be determined from the information given" / "The material does not say, so it cannot be judged" / "This cannot be confirmed from the text alone" / "More information is needed to decide" / "The provided material does not allow us to confirm it". 한 문구는 최대 2개 쌍에서만 쓴다(자연스러운 변형을 더해도 됨). 한국어 선택지도 같은 방식으로 맞춘다.
2. **길이 단서(가장 긴 선택지 = 정답) 줄이기.** 지금은 70문항 중 약 30~34개에서 정답이 단독 최장이다. 목표: 21개 이하(30% 이하), 단독 최단도 30% 이하. 방법: 쌍의 선택지는 두 문항이 공유하므로, **두 문항 모두에서 오답인 선택지(Z)나 근접 오답을 구체적 세부(지문에 맞는 그럴듯한 한 절)로 늘려 쌍 안에서 가장 긴 선택지가 정답이 아니게** 한다. 정답이 최장인 쌍의 절반 이상에서 이렇게 한다. 늘린 오답은 여전히 지문의 특정 사실 때문에만 틀려야 하고 option_reasons 에 그 이유가 있어야 한다. 정답을 일부 간결하게 줄여도 된다(정보는 빼지 말 것). 길이 비율 0.4~1.8 범위를 유지하고 상투적 맺음말로 채우지 말 것.
3. **사실 팩 밖의 주장 제거(근거 감사).** 모든 선택지, 지문, rationale 을 읽고, 법 규칙, 숫자, 기한, 기관, 번호가 `<PACK>.facts.json` 의 fact_id 로 뒷받침되지 않으면 고친다: 합성 장면이면 그 주장을 빼거나 일반 표현("the responsible office")으로 바꾸고, 사실 문항이면 fact_ids 와 일치하게 한다. 기억에 의존한 법 조문 번호(예: BGB § 356b), 사실 팩에 없는 기관 이름(예: 등기소), 사실 팩에 없는 전화번호는 특히 제거한다. 실존하는 제도라도 사실 팩에 없으면 쓰지 않는다. (합성 지문의 가상 기관 이름은 허용.) 고친 뒤 fact_ids, option_reasons, rationale 을 일관되게 갱신한다.
4. **쌍 설계 감사.** 각 쌍에서 두 지문이 **통제 사실 하나만** 다른지, 선택지가 두 버전 모두에서 한쪽만 분명한 최선인지 점검한다. 여러 변수가 다르거나(예: 나이, 학년, 위임 여부 동시 변경) 방어 가능한 두 선택지가 있으면 고친다. 보고에서 지적된 쌍(있다면 프롬프트에 적혀 있음)을 우선 본다. "정중한 편지가 위협 요청을 조용히 무시"하는 식의 evasive/정답 경쟁 선택지는 정답을 명시적으로 거절하는 쪽으로 분명히 하거나 오답 사유를 더 구체화한다.
5. 사용되지 않은 사실이 있으면, 자연스럽게 들어갈 자리가 있는 문항에서만 사실을 더 쓴다(억지로 넣지 않는다).
6. 영어와 한국어가 같은 뜻인지, 숫자가 같은지 확인한다(쌍의 두 문항 선택지는 영어, 한국어 모두 글자 단위 동일 유지). 고친 영어에 맞춰 한국어 역번역을 반드시 고친다. 한국어에 가운뎃점(·) 금지.

## 제약
- local_id, pair_id, 문항 수, 하위유형, 쌍 구조는 바꾸지 않는다(내용만 고친다). answer_index 와 option_tags, refusal_labels 는 선택지 의미가 바뀌면 함께 맞춘다.
- 다른 팩 파일, 사실 팩, 스크립트, spec 은 수정 금지. git 커밋 금지. 공용 scratch 파일을 쓰지 말고 `/tmp/claude-0/<PACK>_revise/` 안에 고유 이름으로만 임시 파일을 둔다.
- 수정은 파일을 직접 편집(또는 본인 폴더의 스크립트로 해당 JSON 만 수정)한다. 편집 후 `python3 -m json.tool` 로 유효성 확인.

## 종료 조건과 보고
`python3 eu_pilot/tools/qa_check.py <PACK>` 이 ERROR=0 이고, "correct option is the unique longest" 경고가 사라지거나 30% 이하가 될 때까지 반복. 최종 보고(120단어 이내): 최종 qa_check 요약 줄, 정답 최장/최단 비율, 근거 감사에서 고친 문항 수와 대표 사례 2개, 쌍 설계에서 고친 쌍, 남은 의심 문항.
