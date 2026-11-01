#!/usr/bin/env python3
"""사실 팩 JSON 의 모든 source.excerpt 를 검증하고 verification 필드를 채운다.
사용: python verify_facts.py <facts.json> [--quiet]
종료코드: 0 = 전부 일치, 1 = 불일치/차단 있음
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fetch_verify import verify  # noqa: E402


def main():
    path = sys.argv[1]
    quiet = "--quiet" in sys.argv
    facts = json.load(open(path, encoding="utf-8"))
    bad = []
    n_src = 0
    for f in facts:
        for s in f.get("sources", []):
            n_src += 1
            v = verify(s["url"], s["excerpt"], s.get("lang", "en"))
            s["verification"] = {
                "method": "fetch_verify.py (normalised substring match)",
                "matched": bool(v["matched"]),
                "http_status": v["status"],
                "blocked": bool(v["blocked"]),
                "fetched_at": v["fetched_at"],
                "text_sha256": v["text_sha256"],
            }
            if not v["matched"]:
                bad.append((f["fact_id"], s["url"], v.get("error") or ("blocked" if v["blocked"] else v.get("hint", "no match"))))
        f["verified"] = bool(f.get("sources")) and all(s["verification"]["matched"] for s in f["sources"])
    json.dump(facts, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for f in facts if f["verified"])
    print(f"{os.path.basename(path)}: facts={len(facts)} verified={ok} sources={n_src} failures={len(bad)}")
    if not quiet:
        for b in bad:
            print("  FAIL", b[0], b[1], "|", str(b[2])[:160])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
