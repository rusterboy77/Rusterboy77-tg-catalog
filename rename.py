import os
import sys
import json
import re

CATALOG_PATH = "catalog.json"
TORRENTS_DIR = "torrents"

def load_catalog():
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_catalog(catalog):
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

def rename_torrent(filename: str) -> str:
    """Genera un nombre limpio para guardar en el JSON, sin mover archivos"""
    name, _ = os.path.splitext(filename)
    clean_name = re.sub(r"\[|\]", "", name)
    clean_name = re.sub(r"HDTV\s*\d+p", "HDTV", clean_name)
    clean_name = clean_name.replace("  ", " ")
    return clean_name.strip()

def main():
    if len(sys.argv) < 2:
        print("[ERROR] Uso: python rename.py <torrent_file>")
        sys.exit(1)

    filename = sys.argv[1]
    filepath = os.path.join(TORRENTS_DIR, filename)

    if not os.path.exists(filepath):
        print(f"[ERROR] No existe {filepath}")
        sys.exit(1)

    new_name = rename_torrent(filename)

    catalog = load_catalog()
    entry = {
        "title": new_name,
        "files": [{"file": filename, "path": filepath}]
    }
    catalog.append(entry)
    save_catalog(catalog)

    print(f"[INFO] rename.py -> {new_name}")

if __name__ == "__main__":
    main()

