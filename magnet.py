#!/usr/bin/env python3
# magnet.py
import sys
import os
import json
import hashlib
import urllib.parse

try:
    import bencodepy
except Exception as e:
    sys.stderr.write("[ERROR] Necesitas instalar 'bencodepy' (añádelo a requirements.txt). Detalle: %s\n" % e)
    sys.exit(2)


def find_torrent_path(arg):
    """
    Acepta:
      - ruta completa (torrents/xxx.torrent)
      - nombre de fichero (xxx.torrent)
      - rutas con duplicación 'torrents/torrents/xxx'
    Devuelve ruta válida o None.
    """
    if not arg:
        return None

    # 1) si existe tal cual, usamos eso
    if os.path.exists(arg):
        return os.path.normpath(arg)

    # 2) normalizar y comprobar
    norm = os.path.normpath(arg)
    if os.path.exists(norm):
        return norm

    # 3) si nos pasan algo que contiene 'torrents' repetido, normalizamos basename
    bn = os.path.basename(arg)
    candidate = os.path.join("torrents", bn)
    if os.path.exists(candidate):
        return os.path.normpath(candidate)

    # 4) por si acaso: arg puede tener prefijo './torrents/..' etc
    candidate2 = os.path.join(os.getcwd(), arg)
    if os.path.exists(candidate2):
        return os.path.normpath(candidate2)

    # nada encontrado
    return None


def build_magnet_from_file(path):
    with open(path, "rb") as f:
        data = f.read()
    decoded = bencodepy.decode(data)
    # keys suelen ser bytes
    info = decoded.get(b"info") or decoded.get("info")
    if info is None:
        raise ValueError("No se encontró la clave 'info' en el torrent")

    # re-encode the info dict exactly as bencoded to compute info-hash
    info_b = bencodepy.encode(info)
    infohash = hashlib.sha1(info_b).hexdigest()

    # trackers: 'announce' y 'announce-list'
    trackers = []
    ann = decoded.get(b"announce") or decoded.get("announce")
    if ann:
        trackers.append(ann.decode() if isinstance(ann, bytes) else str(ann))

    al = decoded.get(b"announce-list") or decoded.get("announce-list")
    if al:
        # announce-list suele ser lista de listas
        for tier in al:
            if isinstance(tier, (list, tuple)):
                for t in tier:
                    trackers.append(t.decode() if isinstance(t, bytes) else str(t))
            else:
                trackers.append(tier.decode() if isinstance(tier, bytes) else str(tier))

    # construir magnet
    magnet = f"magnet:?xt=urn:btih:{infohash}"
    for tr in trackers:
        # percent-encode trackers
        magnet += "&tr=" + urllib.parse.quote(tr, safe=":/?")
    return infohash, trackers, magnet


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage", "msg": "pass torrent path or filename"}, ensure_ascii=False))
        sys.exit(1)

    arg = sys.argv[1]
    path = find_torrent_path(arg)
    if not path:
        sys.stderr.write(f"[ERROR] No existe {arg} ni torrents/{os.path.basename(arg)}\n")
        sys.exit(3)

    try:
        infohash, trackers, magnet = build_magnet_from_file(path)
    except Exception as e:
        sys.stderr.write(f"[ERROR] No se pudo procesar {path}: {e}\n")
        sys.exit(4)

    out = {
        "file": os.path.basename(path),
        "path": os.path.normpath(path),
        "infohash": infohash,
        "trackers": trackers,
        "magnet": magnet
    }
    # imprimimos JSON para que main lo pueda capturar si lo desea
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
