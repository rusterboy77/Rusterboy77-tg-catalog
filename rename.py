#!/usr/bin/env python3
import re
import json
import os

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

def extract_metadata_from_filename(filename):
    base_name = os.path.splitext(filename)[0]
    clean_name = remove_tokens(base_name)
    year, cleaner_name = extract_year_and_clean(clean_name)
    quality = "Unknown"
    if "4k" in base_name.lower() or "2160" in base_name.lower():
        quality = "4K"
    elif "1080" in base_name.lower():
        quality = "1080p"
    elif "720" in base_name.lower():
        quality = "720p"
    is_series = False
    season = None
    episode = None
    series_patterns = [
        r"[Ss](\d{1,2})[Ee](\d{1,2})",
        r"temporada\s*(\d+).*capitulo\s*(\d+)",
        r"season\s*(\d+).*episode\s*(\d+)",
        r"cap\.?\s*(\d+)"
    ]
    for pattern in series_patterns:
        match = re.search(pattern, base_name, re.IGNORECASE)
        if match:
            is_series = True
            if len(match.groups()) >= 1:
                season = int(match.group(1))
            if len(match.groups()) >= 2:
                episode = int(match.group(2))
            break
    if not is_series and re.search(r"cap\.?\s*\d+", base_name, re.IGNORECASE):
        is_series = True
        season = 1
    result = {
        "title": cleaner_name,
        "year": year,
        "quality": quality,
        "type": "series" if is_series else "movie"
    }
    if is_series:
        result["season"] = season
        result["episode"] = episode
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        filename = sys.argv[1]
        metadata = extract_metadata_from_filename(filename)
        print(json.dumps(metadata, ensure_ascii=False))
