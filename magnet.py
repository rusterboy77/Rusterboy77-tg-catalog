import sys, json, bencodepy, hashlib

TORRENTS_DIR = "torrents"

def torrent_to_magnet(path: str) -> str:
    with open(path, "rb") as f:
        data = bencodepy.decode(f.read())
    info = data[b"info"]
    info_bencoded = bencodepy.encode(info)
    info_hash = hashlib.sha1(info_bencoded).hexdigest()
    return f"magnet:?xt=urn:btih:{info_hash}"

def main():
    if len(sys.argv) < 2:
        print("[ERROR] Falta nombre de archivo")
        return
    filename = sys.argv[1]
    with open("last_item.json", "r", encoding="utf-8") as f:
        item = json.load(f)

    magnet = torrent_to_magnet(f"{TORRENTS_DIR}/{filename}")
    item["source"] = magnet
    item["type"] = "magnet"

    with open("last_item.json", "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

    print(f"[INFO] magnet.py -> {magnet[:50]}...")

if __name__ == "__main__":
    main()

