import os
import re
import shutil

# Carpeta donde se guardan torrents recién recibidos
INCOMING_DIR = "torrents"
# Carpeta organizada temporal
ORGANIZED_DIR = "organized_torrents"

SERIES_REGEX = re.compile(r"Cap(?:\.|\s*\()?(\d{3})", re.IGNORECASE)
YEAR_REGEX = re.compile(r"\((\d{4})\)")

def organize_torrent(filename):
    # Quita extensiones
    name = os.path.splitext(filename)[0]

    # Detecta año
    year_match = YEAR_REGEX.search(name)
    year = year_match.group(1) if year_match else ""

    # Detecta si es serie o película
    series_match = SERIES_REGEX.search(name)
    if series_match:
        season_num = int(series_match.group(1)[0])
        target_dir = os.path.join(ORGANIZED_DIR, "series", name.split("Cap")[0].strip(), f"Season {season_num}")
    else:
        # Película
        clean_name = re.sub(r"\[\d{3,4}p.*?\]", "", name).strip()
        target_dir = os.path.join(ORGANIZED_DIR, "movies", clean_name)
        if year:
            target_dir += f" ({year})"

    os.makedirs(target_dir, exist_ok=True)
    shutil.move(os.path.join(INCOMING_DIR, filename), os.path.join(target_dir, filename))
    print(f"[A] Movido {filename} → {target_dir}")

def main():
    for f in os.listdir(INCOMING_DIR):
        if f.lower().endswith(".torrent"):
            organize_torrent(f)

if __name__ == "__main__":
    main()
