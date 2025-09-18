import os, re, requests, base64, json

GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TORRENTS_DIR = "torrents"

# --- helpers github ---
def github_list_files(path: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code == 200:
        return r.json()
    print("[ERROR] No se pudo listar carpeta:", r.text)
    return []

def sanitize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\.\-\[\]\(\) ]+", "_", name)

def main():
    files = github_list_files(TORRENTS_DIR)
    if not files:
        print("[WARN] No se encontraron torrents en GitHub.")
        return

    print(f"[INFO] Procesando {len(files)} torrents desde GitHub...")

    for f in files:
        if not f["name"].lower().endswith(".torrent"):
            continue
        new_name = sanitize_name(f["name"])
        if new_name != f["name"]:
            print(f"[RENAME] {f['name']} → {new_name}")
            # en GitHub API no hay "rename", hay que copiar y borrar
            url_get = f["download_url"]
            data = requests.get(url_get).content
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{TORRENTS_DIR}/{new_name}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            body = {
                "message": f"rename {f['name']} → {new_name}",
                "content": base64.b64encode(data).decode(),
            }
            requests.put(api_url, headers=headers, json=body, timeout=20)

            # borrar viejo
            del_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{TORRENTS_DIR}/{f['name']}"
            requests.delete(del_url, headers=headers, json={"message": "remove old", "sha": f["sha"]})

    print("[INFO] rename.py terminado ✅")

if __name__ == "__main__":
    main()
