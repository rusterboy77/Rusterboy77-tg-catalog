#!/usr/bin/env python3
# rename.py
# Adaptado para Render, mantiene la lógica local original

import re

# Tokens que queremos eliminar
TOKENS_REMOVE = [
    "wolfmax4k.com", "wolfmax4k.net",
    "720esp", "1080esp", "2160esp", "4kesp", "blurayesp",
    "720p", "1080p", "2160p", "720pEsp", "1080pEsp", "2160pEsp", "4k",
    "hdtv", "webrip", "web-dl", "webdl", "bluray", "br", "remux",
    "x264", "x265", "hevc", "aac", "dts", "ac3",
    "esp", "eng", "subesp", "lat", "latam", "multi"
]

escaped = [re.escape(t) for t in TOKENS_REMOVE]
TOKENS_PATTERN = r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)"
TOKENS_RE = re.compile(TOKENS_PATTERN, re.IGNORECASE)

BRACKETS_RE = re.compile(r"\[.*?\]|\{.*?\}")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
CAP_WORD_RE = re.compile(r"cap(?=[\s\._\-\(\d])", re.IGNORECASE)
DIGITS_2_4_RE = re.compile(r"(\d{2,4})")
MULTI_SPACES_RE = re.compile(r"\s{2,}")
TRAILING_PUNCT_RE = re.compile(r"^[\s\-\._\[]+|[\s\-\._\]]+$")

def safe_norm(s: str) -> str:
    s = s.replace("_", " ")
    s = MULTI_SPACES_RE.sub(" ", s).strip()
    return s

def remove_tokens(s: str) -> str:
    s = BRACKETS_RE.sub(" ", s)
    s = TOKENS_RE.sub(" ", s)
    s = re.sub(r"\(\s*\d{1,3}\s*\)", " ", s)
    s = re.sub(r"[\[\]\{\}]", " ", s)
    s = MULTI_SPACES_RE.sub(" ", s).strip()
    s = TRAILING_PUNCT_RE.sub("", s).strip()
    return s

def extract_year_and_clean(s: str):
    yrs = YEAR_RE.findall(s)
    if not yrs:
        return None, s
    year = yrs[-1]
    s2 = re.sub(rf"\(?\b{re.escape(year)}\b\)?", " ", s)
    s2 = MULTI_SPACES_RE.sub(" ", s2).strip()
    return year, s2

def detect_cap_number(s: str):
    low = s.lower()
    m = CAP_WORD_RE.search(low)
    if not m:
        return None
    tail = low[m.end():]
    md = DIGITS_2_4_RE.search(tail)
    if md:
        return int(md.group(1))
    md2 = DIGITS_2_4_RE.findall(low)
    if md2:
        return int(md2[-1])
    return None

def canonical_movie_key(title: str, year):
    t = re.sub(r"[^\w]", " ", (title or "").lower()).strip()
    return (t + "||" + (str(year) if year else "")).strip()

def canonical_series_key(title: str, season: int):
    t = re.sub(r"[^\w]", " ", (title or "").lower()).strip()
    return f"{t}||S{season}"
