import os, json, shutil
from pathlib import Path
from rename import remove_tokens, detect_cap_number, safe_norm, extract_year_and_clean, canonical_movie_key, canonical_series_key

# Carpeta base dinámica en Render
BASE_DIR = Path(__file__).parent.resolve()
TORRENTS_DIR = BASE_DIR / "torrents"
OUTPUT_DIR = BASE_DIR / "organized_torrents"

TORRENTS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

movie_map = {}
series_map = {}
catalog = []

for torrent_file in sorted(TORRENTS_DIR.iterdir()):
    if not torrent_file.name.lower().endswith(".torrent"):
        continue

    base_name = torrent_file.stem
    base_norm = safe_norm(base_name)

    cap_num = detect_cap_number(base_norm)
    is_series = (cap_num is not None and cap_num >= 100)

    if is_series:
        season = cap_num // 100
        title_part = base_norm.split("cap")[0]
        title_clean = safe_norm(remove_tokens(title_part))
        if not title_clean:
            title_clean = safe_norm(remove_tokens(base_norm))
        key = canonical_series_key(title_clean, season)

        dest_dir = series_map.get(key, OUTPUT_DIR / "series" / title_clean / f"Season {season}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        series_map[key] = dest_dir

        dest_path = dest_dir / torrent_file.name
        shutil.copy2(torrent_file, dest_path)

        catalog.append({
            "title": torrent_file.name,
            "source": str(dest_path.relative_to(OUTPUT_DIR)).replace("\\", "/"),
            "type": "torrent",
            "category": "series",
            "serie": title_clean,
            "season": season
        })
    else:
        year, cleaned_no_year = extract_year_and_clean(remove_tokens(base_norm))
        movie_title = safe_norm(cleaned_no_year)
        if not movie_title:
            movie_title = safe_norm(remove_tokens(base_norm))
        folder_display = f"{movie_title} ({year})" if year else movie_title
        key = canonical_movie_key(movie_title, year)

        dest_dir = movie_map.get(key, OUTPUT_DIR / "movies" / folder_display)
        dest_dir.mkdir(parents=True, exist_ok=True)
        movie_map[key] = dest_dir

        dest_path = dest_dir / torrent_file.name
        shutil.copy2(torrent_file, dest_path)

        catalog.append({
            "title": torrent_file.name,
            "source": str(dest_path.relative_to(OUTPUT_DIR)).replace("\\", "/"),
            "type": "torrent",
            "category": "movie",
            "movie": movie_title,
            "year": year or ""
        })

# Guardar catalog.json
with open(OUTPUT_DIR / "catalog.json", "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)


