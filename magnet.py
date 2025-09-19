import os
import sys
import hashlib
import bencodepy
import json
import base64
import requests

REPO = "rusterboy77/Rusterboy77-tg-catalog"
CATALOG_FILE = "catalog.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if len(sys.argv) < 2:
    print("Uso: python magnet.py <torrent_file>")
    sys.exit(1)

fname = sys.argv[1]
torrent_path = os.path.join("torrents", fname)

if not os.path.exists(torrent_path):
    print(f"ERROR: no existe {torrent_path}", file=sys.stderr)
    sys.exit(1)

# Leer torrent
with open(torrent_path, "rb") as f:
    torrent_data = bencodepy.decode(f.read())

info_hash = hashlib.sha1(bencodepy.encode(torrent_data[b"info"])).hexdigest()
magnet = f"magnet:?xt=urn:btih:{info_hash}"

# Leer catalog.json actual
url = f"https://api.github.com/repos/{REPO}/contents/{CATALOG_FILE}"
headers = {"Authorization": f"token {GITHUB_TOKEN}"}
r = requests.get(url, headers=headers)

if r.status_code == 200:
    sha = r.json()["sha"]
    content = base64.b64decode(r.json()["content"]).decode("utf-8")
    try:
        catalog = json.loads(content)
    except:
        catalog = []
else:
    sha = None
    catalog = []

# Añadir nueva entrada
entry = {
    "title": fname.replace(".torrent", ""),
    "source": f"https://raw.githubusercontent.com/{REPO}/main/{torrent_path}",
    "magnet": magnet,
}
catalog.append(entry)

# Subir catalog.json actualizado
new_content = json.dumps(catalog, indent=2, ensure_ascii=False)
message = f"update catalog.json with {fname}"
data = {
    "message": message,
    "content": base64.b64encode(new_content.encode()).decode(),
    "branch": "main",
}
if sha:
    data["sha"] = sha

r = requests.put(url, headers=headers, json=data)
if r.status_code not in (200, 201):
    print(f"Error actualizando catalog.json: {r.text}", file=sys.stderr)
    sys.exit(1)

print(f"OK magnet añadido: {magnet}")
