import os, json, base64, requests, hashlib
from torrent_parser import parse_torrent_file

GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CATALOG_PATH = "catalog.json"
TORRENTS_DIR = "torrents"

def github_list_files(path: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code == 200:
        return r.json()
    return []

def github_get_file(path: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"])
        return content, r.json().get("sha")
    return None, None

def github_put_file(path: str, content: str, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    body = {"message": f"update {path}", "content": base64.b64encode(content.encode()).decode()}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=headers, json=body, timeout=20)
    return r.status_code in (200, 201)

def infohash_from_torrent(data: bytes) -> str:
    import bencodepy
    torrent = bencodepy.decode(data)
    info = bencodepy.encode(torrent[b"info"])
    return hashlib.sha1(info).hexdigest()

def main():
    # cargar catalog.json
    catalog_data, sha = github_get_file(CATALOG_PATH)
    catalog = json.loads(catalog_data.decode()) if catalog_data else []

    files = github_list_files(TORRENTS_DIR)
    print(f"[INFO] Procesando {len(files)} torrents desde GitHub...")

    for f in files:
        if not f["name"].lower().endswith(".torrent"):
            continue
        url = f["download_url"]
        data = requests.get(url).content
        try:
            parsed = parse_torrent_file(data)
            infohash = infohash_from_torrent(data)
            trackers = parsed.get("announce-list") or [parsed.get("announce")]
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            if trackers:
                for t in trackers:
                    if isinstance(t, list):
                        for u in t:
                            magnet += f"&tr={u}"
                    else:
                        magnet += f"&tr={t}"

            item = {
                "title": parsed.get("info", {}).get("name", f["name"]),
                "source": magnet,
                "type": "magnet",
            }
            catalog = [i for i in catalog if i["source"] != magnet]
            catalog.append(item)
            print(f"[ADD] {item['title']} ✅")

        except Exception as e:
            print(f"[ERROR] {f['name']} no procesado:", e)

    github_put_file(CATALOG_PATH, json.dumps(catalog, ensure_ascii=False, indent=2), sha)
    print("[INFO] magnet.py terminado ✅")

if __name__ == "__main__":
    main()
