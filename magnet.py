import sys, os, json, hashlib, urllib.parse
import bencodepy

def build_magnet_from_file(path):
    with open(path,"rb") as f: data = f.read()
    decoded = bencodepy.decode(data)
    info = decoded.get(b"info") or decoded.get("info")
    if not info: raise ValueError("No se encontró 'info' en torrent")
    info_b = bencodepy.encode(info)
    infohash = hashlib.sha1(info_b).hexdigest()
    trackers = []
    ann = decoded.get(b"announce") or decoded.get("announce")
    if ann: trackers.append(ann.decode() if isinstance(ann,bytes) else str(ann))
    al = decoded.get(b"announce-list") or decoded.get("announce-list")
    if al:
        for tier in al:
            if isinstance(tier,(list,tuple)):
                for t in tier: trackers.append(t.decode() if isinstance(t,bytes) else str(t))
            else: trackers.append(tier.decode() if isinstance(tier,bytes) else str(tier))
    magnet = f"magnet:?xt=urn:btih:{infohash}"
    for tr in trackers: magnet += "&tr=" + urllib.parse.quote(tr,safe=":/?")
    return infohash, trackers, magnet

if __name__=="__main__":
    if len(sys.argv)<2:
        print(json.dumps({"error":"usage"}))
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        sys.stderr.write(f"[ERROR] No existe {path}\n")
        sys.exit(2)
    try:
        infohash, trackers, magnet = build_magnet_from_file(path)
        print(json.dumps({"file":os.path.basename(path),"infohash":infohash,"trackers":trackers,"magnet":magnet}))
    except Exception as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        sys.exit(3)
