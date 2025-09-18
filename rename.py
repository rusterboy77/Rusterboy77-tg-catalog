import os, re, json, requests

GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CATALOG_JSON = "catalog.json"

TORRENTS_DIR = "torrents"

def download_torrent(url, local_path):
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        with open(local_path, "wb") as f:
            f.write(r.content)
        return True
    return False

def main():
    if not os.path.exists(TORRENTS_DIR):
        os.makedirs(TORRENTS_DIR)
    # cargar catalog.json
    catalog = []
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
                download_torrent(url, local_path)

            # Renombrado simple: quitar calidades del nombre de carpeta
            name = filename
            name = re.sub(r"\[.*?p.*?\]", "", name)
            name = re.sub(r"\.torrent$", "", name)
            item["title"] = name.strip()

        except Exception as e:
            print(f"[ERROR] {filename} no procesado:", e)

    with open(CATALOG_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print("[INFO] rename.py terminado ✅")

if __name__ == "__main__":
    main()
