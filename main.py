#!/usr/bin/env python3
# main.py
# Procesa torrents y genera catalog.json, integrado con rename.py y magnet.py

import os, shutil, json, subprocess
from pathlib import Path

FILES_DIR = "files"
OUTPUT_DIR = "organized_torrents"
COPY_INSTEAD_OF_MOVE = True
DRY_RUN = False

# Import rename.py como módulo o ejecutar
from rename import safe_norm, remove_tokens, extract_year_and_clean, detect_cap_number, canonical_movie_key, canonical_series_key

# Crear carpetas base
os.makedirs(os.path.join(OUTPUT_DIR, "movies"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "series"), exist_ok=True)

movie_map = {}
series_map = {}
catalog = []

files = sorted(os.listdir(FILES_DIR))
print(f"[INFO] Encontrados {len(files)} ficheros en '{FILES_DIR}' (procesando solo .torrent).")

for fname in files:
    if not fname.lower().endswith(".torrent"):
        continue

    src = os.path.join(FILES_DIR, fname)
    base = os.path.splitext(fname)[0]
    base_norm = safe_norm(base)

    # detectar capítulo
    cap_num = detect_cap_number(base_norm)
    is_series = (cap_num is not None and cap_num >= 100)

    if is_series:
        season = cap_num // 100
        mcap = base_norm.lower().find("cap")
        title_part = base_norm[:mcap] if mcap != -1 else base_norm
        title_clean = remove_tokens(title_part)
        _, title_clean = extract_year_and_clean(title_clean)
        title_clean = safe_norm(title_clean) or safe_norm(remove_tokens(base_norm))
        title_clean = title_clean.strip(" -_.[](){}")

        key = canonical_series_key(title_clean, season)
        if key in series_map:
            dest_dir = series_map[key]
        else:
            dest_dir = os.path.join(OUTPUT_DIR, "series", title_clean, f"Season {season}")
            os.makedirs(dest_dir, exist_ok=True)
            series_map[key] = dest_dir

        dest_path = os.path.join(dest_dir, fname)
        if DRY_RUN:
            print(f"[DRY] Serie -> {title_clean} / Season {season}  : {fname}  -> {dest_path}")
        else:
            if COPY_INSTEAD_OF_MOVE:
                shutil.copy2(src, dest_path)
            else:
                shutil.move(src, dest_path)

        catalog.append({
            "title": fname,
            "source": os.path.relpath(dest_path, OUTPUT_DIR).replace("\\", "/"),
            "type": "torrent",
            "category": "series",
            "serie": title_clean,
            "season": season
        })

    else:
        # Película
        cleaned = remove_tokens(base_norm)
        year, cleaned_no_year = extract_year_and_clean(cleaned)
        movie_title = safe_norm(cleaned_no_year) or safe_norm(remove_tokens(base_norm))
        movie_title = movie_title.strip(" -_.[](){}")
        folder_display = f"{movie_title} ({year})" if year else movie_title

        key = canonical_movie_key(movie_title, year)
        if key in movie_map:
            dest_dir = movie_map[key]
        else:
            dest_dir = os.path.join(OUTPUT_DIR, "movies", folder_display)
            os.makedirs(dest_dir, exist_ok=True)
            movie_map[key] = dest_dir

        dest_path = os.path.join(dest_dir, fname)
        if DRY_RUN:
            print(f"[DRY] Movie -> {movie_title} ({year}) : {fname} -> {dest_path}")
        else:
            if COPY_INSTEAD_OF_MOVE:
                shutil.copy2(src, dest_path)
            else:
                shutil.move(src, dest_path)

        catalog.append({
            "title": fname,
            "source": os.path.relpath(dest_path, OUTPUT_DIR).replace("\\", "/"),
            "type": "torrent",
            "category": "movie",
            "movie": movie_title,
            "year": year or ""
        })

    # --- Llamada a magnet.py para actualizar infohash y trackers ---
    if not DRY_RUN:
        try:
            result = subprocess.run(
                ["python3", "magnet.py", dest_path],
                capture_output=True, text=True, check=True
            )
            magnet_data = json.loads(result.stdout)
            catalog[-1].update({
                "infohash": magnet_data.get("infohash"),
                "trackers": magnet_data.get("trackers"),
                "magnet": magnet_data.get("magnet")
            })
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] magnet.py falló: {e}")
        except json.JSONDecodeError:
            print(f"[ERROR] Salida de magnet.py no es JSON:\n{result.stdout}")

# Guardar catalog.json
if not DRY_RUN:
    with open(os.path.join(OUTPUT_DIR, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

print("[DONE] Proceso finalizado.")
print(f"[INFO] Carpetas movies: {len(movie_map)}, series (title+season): {len(series_map)}")
print(f"[INFO] Items en catalog: {len(catalog)} (no escrito si DRY_RUN=True)")

