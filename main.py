import os, re, json, base64, requests, subprocess
from typing import Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# -------- CONFIG --------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GITHUB_PATH = "catalog.json"
TORRENTS_DIR = "torrents"

os.makedirs(TORRENTS_DIR, exist_ok=True)

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)
app = FastAPI(title="TG -> Catalog API")

# -------- UTILS --------
def get_catalog() -> list:
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def put_catalog(data: list):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None
    r_get = requests.get(api_url, headers=headers, timeout=10)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    content_b64 = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode()
    ).decode()
    body = {"message": "update catalog", "content": content_b64}
    if sha:
        body["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=body, timeout=20)
    print(f"[DEBUG] PUT catalog.json -> {r_put.status_code}")
    return r_put.status_code in (200, 201)

def save_torrent_to_github(filename: str, content: bytes) -> str:
    path = f"{TORRENTS_DIR}/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(content).decode("utf-8")
    body = {"message": f"add torrent {filename}", "content": content_b64}

    r = requests.put(api_url, headers=headers, json=body, timeout=20)
    if r.status_code in (200, 201):
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
        return raw_url
    return ""

# -------- WEBHOOK --------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    msg = payload.get("message") or payload.get("channel_post")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message"})

    added_items = []

    # magnet links en texto
    text = msg.get("text") or msg.get("caption") or ""
    for m in MAGNET_RE.findall(text):
        item = {"title": text.splitlines()[0][:120], "source": m, "type": "magnet"}
        added_items.append(item)

    # documentos .torrent
    doc = msg.get("document")
    if doc and doc.get("file_name", "").lower().endswith(".torrent"):
        file_id = doc["file_id"]
        getf = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}",
            timeout=20,
        )
        if getf.status_code == 200:
            file_path = getf.json()["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            r = requests.get(file_url, timeout=20)
            if r.status_code == 200:
                filename = doc["file_name"]
                raw_url = save_torrent_to_github(filename, r.content)
                if raw_url:
                    # --- Ejecutar rename.py y magnet.py ---
                    with open(f"{TORRENTS_DIR}/{filename}", "wb") as f:
                        f.write(r.content)

                    try:
                        subprocess.run(["python", "rename.py", filename], check=True)
                        subprocess.run(["python", "magnet.py", filename], check=True)
                    except Exception as e:
                        print("[ERROR] Ejecutando scripts:", e)

                    # leer salida temporal del magnet.py
                    if os.path.exists("last_item.json"):
                        with open("last_item.json", "r", encoding="utf-8") as f:
                            item = json.load(f)
                        added_items.append(item)

    # --- fusionar con catalog.json ---
    if added_items:
        catalog = get_catalog()
        existing = {it["source"]: it for it in catalog}
        for it in added_items:
            existing[it["source"]] = it
        put_catalog(list(existing.values()))

    return JSONResponse({"ok": True, "added": len(added_items)})

@app.get("/api/catalog")
async def catalog():
    return JSONResponse(get_catalog())
