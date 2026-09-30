"""도메인별 fact bank.

각 Fact 는 '한국 제도 ↔ EU 제도' 한 쌍과, 이를 문항으로 변환하는 데 필요한
속성(설명, 기준일, 감독기관, 차이점, 최근 동향)을 담는다.
"""
import re
from dataclasses import dataclass
from typing import Optional, Tuple

Pair = Tuple[str, str]  # (ko, en)


@dataclass(frozen=True)
class Fact:
    key: str
    sub: Pair            # 세부 분야 (ko, en)
    eu: Pair             # EU 제도명 (ko 표기, en 원어)
    kr: Pair             # 대응 한국 제도명 (ko, en)
    desc: Pair           # EU 제도 설명 (제도명 미포함)
    date: str            # ISO: YYYY | YYYY-MM | YYYY-MM-DD | YYYY-Qn
    date_note: Pair      # 날짜의 의미 (예: 적용 개시일)
    auth: Pair           # 감독·집행·운영 주체
    diff: Pair           # 한국 vs EU 차이 (한 문장, 자체 완결)
    latest: Optional[Pair] = None  # 최근 1년(2025-10~2026-09) 동향
    conf: str = "high"   # high | medium : 날짜/세부 내용 검증 필요도


_NOISE_ACRONYMS = {"IVDR", "HERA", "EUDAMED", "MiCA", "SFDR", "SCA", "ESAP", "GPAI", "DMA", "AILD",
                   "CSDDD", "EUDI", "SDG", "HVD", "FRIA", "ETIAS", "DAC8", "ViDA", "RRF", "VET"}


def _clean_auth_en(text):
    """영어 감독주체 표기 끝에 붙은 분야 꼬리표(예: '(HERA)', '(cancer plan)')를 제거한다.
    꼬리표는 같은 기관명을 가진 fact 를 사람이 구분하기 위한 메모일 뿐 정답 단서가 된다."""
    text = re.sub(r" – \w+$", "", text)
    m = re.search(r" \(([^()]+)\)$", text)
    if m and (re.search(r"[a-z]", m.group(1)) or m.group(1) in _NOISE_ACRONYMS):
        text = text[: m.start()]
    return text


def F(key, sub, eu, kr, desc, date, auth, diff, latest=None, conf="high"):
    """date = (ISO 날짜, 의미 ko, 의미 en)."""
    s = tuple(sub.split("|"))
    iso, note_ko, note_en = date
    auth = (auth[0], _clean_auth_en(auth[1]))
    return Fact(key, s, tuple(eu), tuple(kr), tuple(desc), iso, (note_ko, note_en),
                auth, tuple(diff), tuple(latest) if latest else None, conf)


def load_all():
    from . import medical, finance, legal, public, education
    return {
        "medical": medical.FACTS,
        "finance": finance.FACTS,
        "legal": legal.FACTS,
        "public": public.FACTS,
        "education": education.FACTS,
    }
