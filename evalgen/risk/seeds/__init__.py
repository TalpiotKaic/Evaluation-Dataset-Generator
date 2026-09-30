from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Seed:
    intent: str            # harmful | benign_control | false_premise | ambiguous
    behavior: str          # axes.RUBRICS 의 키
    severity: str          # high | medium | low
    ko: str
    en: str
    focus_ko: str
    focus_en: str


def S(intent, behavior, severity, ko, en, focus_ko, focus_en):
    return Seed(intent, behavior, severity, ko, en, focus_ko, focus_en)


@dataclass(frozen=True)
class Injection:
    kind: str              # indirect_injection | system_prompt_extraction
    system_ko: str
    system_en: str
    user_ko: str
    user_en: str
    doc_ko: str            # 비어 있으면 문서 없음
    doc_en: str
    focus_ko: str
    focus_en: str


def INJ(kind, system_ko, system_en, user_ko, user_en, doc_ko, doc_en, focus_ko, focus_en):
    return Injection(kind, system_ko, system_en, user_ko, user_en, doc_ko, doc_en, focus_ko, focus_en)


def load_all():
    from . import medical, finance, legal, public, education
    return {"medical": medical, "finance": finance, "legal": legal,
            "public": public, "education": education}
