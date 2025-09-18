import os
import json
import base64
from torrent_parser import parse_torrent_file, torrent_infohash
import re
import requests

ORGANIZED_DIR = "organized_torrents"
CATALOG_JSON = "catalog.json"

def get_existing_catalog():
    if os.path.exists(CATALOG_JSON):
        with open(CATALOG_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_catalog(catalog):
    with open(CATALOG_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"[B] Catalog.json actualizado con {len(catalog)} items")

def process_torrent_file(filepath):
    try:
        infohash = torrent_infohash(filepath)
        parsed = parse_torrent_file(filepath)
        trackers = parsed.get("announce-list", []) or [parsed.get("announce")]
        magnet = f"magnet:?xt=urn:btih:{infohash}&tr=" + "&tr=".join(trackers)
        return magnet
    except Exception as e:
        print(f"[B][ERROR] No se pudo leer torrent {filepath}: {e}")
        return None

def main():
    catalog = get_existing_catalog()
    catalog_map = {item["source"]: item for item in catalog}

    for root, _, files in os.walk(ORGANIZED_DIR):
        for f in files:
            if f.lower().endswith(".torrent"):
                fullpath = os.path.join(root, f)
                magnet = process_torrent_file(fullpath)
                if magnet:
                    title = f
                    catalog_map[magnet] = {"title": title, "source": magnet, "type": "magnet"}

    save_catalog(list(catalog_map.values()))

if __name__ == "__main__":
    main()
