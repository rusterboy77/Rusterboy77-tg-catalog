#!/usr/bin/env python3
import re, sys, json

TOKENS_REMOVE = [
    "wolfmax4k.com", "wolfmax4k.net",
    "720esp", "1080esp", "2160esp", "720Esp", "1080Esp", "2160Esp", "4kesp", "blurayesp",
    "720p", "1080p", "2160p", "4k",
    "hdtv", "webrip", "web-dl", "webdl", "bluray", "br", "remux",
    "x264", "x265", "hevc", "aac", "dts", "ac3",
    "esp", "eng", "subesp", "lat", "latam", "multi",
    "spanish", "castellano", "rip", "blurayrip", "bdrip", "dvdrip", "hdrip"
]

escaped = [re.escape(t) for t in TOKENS_REMOVE]
TOKENS_RE = re.compile(r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)
COMBINED_RE = re.compile(r"\b(?:720p|1080p|2160p|4k)(?:esp|lat|eng|subesp)?\b", re.IGNORECASE)
BRACKETS_RE = re.compile(r"\[.*?\]|\{.*?\}")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
CAP_WORD_RE = re.compile(r"cap(?=[\s\._\-\(\d])", re.IGNORECASE)
DIGITS_RE = re.compile(r"(\d{2,4})")
MULTI_SPACES_RE = re.compile(r"\s{2,}")
TRAILING_RE = re.compile(r"^[\s\-\._\[]+|[\s\-\._\]]+$")
SEASON_EPISODE_RE = re.compile(r"(?i)\b(?:S(\d{1,2})E(\d{1,3})|(\d{1,2})x(\d{1,3}))\b")

RESOLUTION_RE = re.compile(r"(2160p|1080p|720p|4k)", re.IGNORECASE)
SOURCE_RE = re.compile(r"(bluray|hdtv|webrip|web-dl|webdl|remux)", re.IGNORECASE)

def detect_quality(fname: str) -> str:
    m = RESOLUTION_RE.search(fname)
    if m:
        return m.group(1).lower()
    m2 = SOURCE_RE.search(fname)
    if m2:
        return m2.group(1).lower()
    return "desconocida"

def safe_norm(s: str) -> str:
    return MULTI_SPACES_RE.sub(" ", s.replace("_", " ")).strip()

def remove_tokens(s: str) -> str:
    s = BRACKETS_RE.sub(" ", s)
    s = COMBINED_RE.sub(" ", s)  # primero combinaciones
    s = TOKENS_RE.sub(" ", s)    # luego tokens individuales
    s = re.sub(r"\(\s*\d{1,3}\s*\)", " ", s)
    s = re.sub(r"[\[\]\{\}]", " ", s)
    return TRAILING_RE.sub("", MULTI_SPACES_RE.sub(" ", s).strip())


def extract_year_and_clean(s: str):
    yrs = YEAR_RE.findall(s)
    if not yrs:
        return None, s
    year = yrs[-1]
    return year, MULTI_SPACES_RE.sub(" ", re.sub(rf"\(?\b{re.escape(year)}\b\)?", " ", s)).strip()

def detect_cap_number(s: str):
    m = CAP_WORD_RE.search(s.lower())
    if not m:
        return None
    tail = s[m.end():]
    md = DIGITS_RE.search(tail)
    return int(md.group(1)) if md else None

def normalize_title(title: str) -> str:
    title = re.sub(r"\([^)]*\)", "", title).strip()
    return safe_norm(title)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No se pasó nombre de archivo"}))
        return

    fname = sys.argv[1]
    base = safe_norm(fname.rsplit(".", 1)[0])
    base = re.sub(r"wolfmax4k\.com|wolfmax4k\.net", " ", base, flags=re.IGNORECASE)
    base = MULTI_SPACES_RE.sub(" ", base).strip()

    # Intentar detectar formato S01E01 primero
    se_match = SEASON_EPISODE_RE.search(base)
    
    cap_num = None
    if not se_match:
        cap_num = detect_cap_number(base)

    is_series_se = (se_match is not None)
    is_series_cap = (cap_num is not None and cap_num >= 100)

    result = {"title": fname}

    if is_series_se:
        if se_match.group(1):
            season = int(se_match.group(1))
            episode = int(se_match.group(2))
        else:
            season = int(se_match.group(3))
            episode = int(se_match.group(4))
        # El título es todo lo que hay antes del SxxExx
        span = se_match.span()
        title_part = base[:span[0]]
        # Si no hay título antes (ej: "1x04 Beetlejuice"), buscar después
        if not title_part.strip():
            title_part = base[span[1]:]
        title_clean = normalize_title(remove_tokens(title_part))
        _, title_clean = extract_year_and_clean(title_clean)
        result.update({"type": "series", "series": title_clean, "season": season, "episode": episode})
    elif is_series_cap:
        season = cap_num // 100
        episode = cap_num % 100
        title_part = base[:base.lower().find("cap")] if "cap" in base.lower() else base
        title_clean = normalize_title(remove_tokens(title_part))
        _, title_clean = extract_year_and_clean(title_clean)
        result.update({
            "type": "series",
            "series": title_clean,
            "season": season,
            "episode": episode,
        })
    else:
        cleaned = remove_tokens(base)
        year, cleaned_no_year = extract_year_and_clean(cleaned)
        movie_title = normalize_title(safe_norm(cleaned_no_year))
        result.update({
            "type": "movie",
            "movie": movie_title,
            "year": year or ""
        })

    result["quality"] = detect_quality(fname)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
