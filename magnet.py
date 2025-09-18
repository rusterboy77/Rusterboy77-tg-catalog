import os
import sys
import json
import hashlib
import bencodepy

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

def torrent_to_magnet(torrent_path: str) -> str:
    with open(torrent_path, "rb") as f:
        torrent_data = f.read()
    torrent_dict = bencodepy.decode(torrent_data)

    info = torrent_dict[b"info"]
    info_bencoded = bencodepy.encode(info)
    info_hash = hashlib.sha1(info_bencoded).hexdigest()

    trackers = []
    if b"announce-list" in torrent_dict:
        trackers = [t[0].decode("utf-8") for t in torrent_dict[b"announce-list"]]
    elif b"announce" in torrent_dict:
        trackers = [torrent_dict[b"announce"].decode("utf-8")]

    magnet = f"magnet:?xt=urn:btih:{info_hash}"
    for tr in trackers:
        magnet += f"&tr={tr}"

    return magnet

def main():
    if len(sys.argv) < 2:
        print("[ERROR] Uso: python magnet.py <torrent_file>")
        sys.exit(1)

    filename = sys.argv[1]
    torrent_path = os.path.join(TORRENTS_DIR, filename)

    if not os.path.exists(torrent_path):
        print(f"[ERROR] {filename} no encontrado en {TORRENTS_DIR}")
        sys.exit(1)

    magnet = torrent_to_magnet(torrent_path)

    catalog = load_catalog()
    for entry in catalog:
        for f in entry.get("files", []):
            if f["file"] == filename:
                f["magnet"] = magnet
                break

    save_catalog(catalog)
    print(f"[INFO] magnet.py -> {filename} añadido magnet")

if __name__ == "__main__":
    main()

