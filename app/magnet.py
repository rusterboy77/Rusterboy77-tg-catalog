#!/usr/bin/env python3
import sys, os, json, hashlib
import bencodepy

def build_magnet_from_file(path):
    with open(path, "rb") as f:
        data = f.read()
    decoded = bencodepy.decode(data)
    info = decoded.get(b"info") or decoded.get("info")
    if not info:
        raise ValueError("No se encontró 'info' en torrent")
    infohash = hashlib.sha1(bencodepy.encode(info)).hexdigest()

    # Magnet limpio: solo incluye el hash
    magnet = f"magnet:?xt=urn:btih:{infohash}"
    return infohash, magnet

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage"}))
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        sys.stderr.write(f"[ERROR] No existe {path}\n")
        sys.exit(2)
    try:
        infohash, magnet = build_magnet_from_file(path)
        print(json.dumps({
            "file": os.path.basename(path),
            "infohash": infohash,
            "magnet": magnet
        }))
    except Exception as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        sys.exit(3)

