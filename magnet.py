import os, json
from torrent_parser import parse_torrent_file  # pip install torrent-parser

CATALOG_JSON = "catalog.json"
TORRENTS_DIR = "torrents"

def main():
    try:
        with open(CATALOG_JSON, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    except Exception:
        catalog = []

    for item in catalog:
        try:
            url = item.get("source")
            if not url:
                continue

            filename = os.path.basename(url)
            local_path = os.path.join(TORRENTS_DIR, filename)
            if not os.path.exists(local_path):
                continue

            # parse torrent
            meta = parse_torrent_file(local_path)
            if meta:
                info_hash = meta.get("info_hash")
                if info_hash:
                    magnet = f"magnet:?xt=urn:btih:{info_hash}"

                    # añadimos trackers si existen
                    trackers = meta.get("announce-list", [])
                    if trackers:
                        for tr in trackers:
                            if isinstance(tr, list):
                                for t in tr:
                                    magnet += f"&tr={t}"
                            else:
                                magnet += f"&tr={tr}"

                    item["magnet"] = magnet

        except Exception as e:
            print(f"[ERROR] {filename} no procesado:", e)

    # guardar catalog.json actualizado
    with open(CATALOG_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print("[INFO] magnet.py terminado ✅")

if __name__ == "__main__":
    main()

