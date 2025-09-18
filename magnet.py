import sys, bencodepy, hashlib, urllib.parse

TRACKERS = [
    "udp://tracker.openbittorrent.com:80/announce",
    "udp://tracker.opentrackr.org:1337/announce"
]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    fname = sys.argv[1]
    with open(f"torrents/{fname}", "rb") as f:
        meta = bencodepy.decode(f.read())

    info = bencodepy.encode(meta[b'info'])
    info_hash = hashlib.sha1(info).hexdigest()

    tr = "&".join("tr=" + urllib.parse.quote(t) for t in TRACKERS)
    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(fname)}&{tr}"
    print(magnet)

