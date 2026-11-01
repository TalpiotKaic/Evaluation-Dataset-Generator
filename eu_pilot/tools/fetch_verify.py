#!/usr/bin/env python3
"""공식 출처 페이지를 가져와 인용문(excerpt)이 실제로 그 페이지에 있는지 검증한다.

원칙
- 가져올 수 없는 페이지(봇 차단 202/403/429/503 등)는 우회하지 않고 'blocked' 로 보고한다.
- EU 법령 원문은 EU 출판청이 프로그래밍용으로 제공하는 Cellar API 로 받는다
  (URL 대신 'celex:32011L0083' 형식으로 지정, --lang 으로 언어 선택).
- 검증은 정규화(NFKC, 공백·따옴표·대시 통일, 대소문자 무시) 후 '부분 문자열 일치'로 한다.

사용 예
  python fetch_verify.py --url celex:32011L0083 --find "14 days to withdraw" --context 200
  python fetch_verify.py --url https://europa.eu/... --excerpt "문장 그대로"
  python fetch_verify.py --url https://... --dump 1500
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from html.parser import HTMLParser

CACHE = os.environ.get("EU_PILOT_CACHE", os.path.join(tempfile.gettempdir(), "eu_pilot_fetch_cache"))
UA = "Mozilla/5.0 (X11; Linux x86_64) K-VeriAI-fact-check/0.2"
LANG3 = {"en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita", "ko": "kor"}
BLOCK_STATUS = {202, 401, 403, 429, 503}
_SKIP = {"script", "style", "noscript", "svg", "head", "template"}
_BLOCKTAGS = {"p", "div", "li", "br", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "table", "ul", "ol", "dd", "dt", "blockquote"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCKTAGS:
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        elif tag in _BLOCKTAGS:
            self.out.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    p.feed(raw)
    return html.unescape("".join(p.out))


_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"',
           "„": '"', "«": '"', "»": '"', "–": "-", "—": "-", "−": "-",
           "‐": "-", "‑": "-", " ": " ", " ": " ", "­": ""}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(_QUOTES.get(c, c) for c in s)
    s = re.sub(r"[​-‏⁠﻿]", "", s)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s


def _cache_path(key: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")


def fetch_text(url: str, lang: str = "en", timeout: int = 60) -> dict:
    """returns {url, fetch_url, status, content_type, text, blocked, error}"""
    key = f"{url}|{lang}"
    cp = _cache_path(key)
    if os.path.exists(cp):
        return json.load(open(cp, encoding="utf-8"))
    headers = []
    fetch_url = url
    if url.startswith("celex:"):
        fetch_url = "http://publications.europa.eu/resource/celex/" + url.split(":", 1)[1]
        headers = ["-H", "Accept: application/xhtml+xml", "-H", f"Accept-Language: {LANG3.get(lang, 'eng')}"]
    res = {"url": url, "fetch_url": fetch_url, "lang": lang, "status": None, "content_type": None,
           "text": "", "blocked": False, "error": None}
    tmp = tempfile.mktemp(suffix=".bin")
    try:
        cmd = ["curl", "-sSL", "-m", str(timeout), "-A", UA, "-o", tmp, "-w", "%{http_code}|%{content_type}"] + headers + [fetch_url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            res["error"] = (r.stderr or "curl failed").strip()[:200]
        else:
            code, _, ctype = r.stdout.partition("|")
            res["status"], res["content_type"] = int(code), ctype
            body = open(tmp, "rb").read()
            if int(code) in BLOCK_STATUS or (int(code) == 200 and len(body) == 0):
                res["blocked"] = True
            elif int(code) >= 400:
                res["error"] = f"HTTP {code}"
            elif "pdf" in ctype.lower():
                pdf = tmp + ".pdf"
                open(pdf, "wb").write(body)
                t = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True)
                res["text"] = t.stdout if t.returncode == 0 else ""
                if not res["text"]:
                    res["error"] = "pdf text extraction failed (pdftotext missing?)"
                os.path.exists(pdf) and os.remove(pdf)
            else:
                enc = "utf-8"
                m = re.search(rb"charset=([A-Za-z0-9_-]+)", body[:2000]) or re.search(rb"charset=([A-Za-z0-9_-]+)", ctype.encode())
                if m:
                    enc = m.group(1).decode()
                try:
                    raw = body.decode(enc, errors="replace")
                except LookupError:
                    raw = body.decode("utf-8", errors="replace")
                res["text"] = html_to_text(raw)
    finally:
        os.path.exists(tmp) and os.remove(tmp)
    if res["status"] == 200 and res["text"]:
        json.dump(res, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def verify(url: str, excerpt: str, lang: str = "en") -> dict:
    r = fetch_text(url, lang)
    out = {"url": url, "status": r["status"], "blocked": r["blocked"], "error": r["error"],
           "matched": False, "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
           "text_sha256": None, "text_len": len(r["text"])}
    if not r["text"]:
        return out
    nt = normalize(r["text"])
    out["text_sha256"] = hashlib.sha256(nt.encode()).hexdigest()
    out["matched"] = normalize(excerpt) in nt
    if not out["matched"]:
        # 가장 비슷한 구간을 알려 줘 오타·번역 혼입을 찾기 쉽게 한다
        import difflib
        ne = normalize(excerpt)
        head = ne[:40]
        i = nt.find(head)
        out["hint"] = nt[max(0, i - 20): i + len(ne) + 60] if i >= 0 else "first 40 chars of excerpt not found in page"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--excerpt")
    ap.add_argument("--find", help="정규식으로 본문 검색 후 문맥 출력")
    ap.add_argument("--context", type=int, default=160)
    ap.add_argument("--dump", type=int, help="본문 앞 N자 출력")
    a = ap.parse_args()
    if a.excerpt:
        print(json.dumps(verify(a.url, a.excerpt, a.lang), ensure_ascii=False, indent=1))
        return
    r = fetch_text(a.url, a.lang)
    print(f"status={r['status']} blocked={r['blocked']} error={r['error']} chars={len(r['text'])}")
    if a.dump:
        print(re.sub(r"\s+", " ", r["text"])[: a.dump])
    if a.find:
        t = re.sub(r"\s+", " ", r["text"])
        for m in list(re.finditer(a.find, t, re.I))[:8]:
            s, e = max(0, m.start() - a.context), m.end() + a.context
            print("...", t[s:e], "...\n")


if __name__ == "__main__":
    main()
