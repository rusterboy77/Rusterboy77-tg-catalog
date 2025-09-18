import os, json, subprocess
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests, base64

GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

app = FastAPI(title="TG -> Catalog API")

def get_raw_github_file():
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("Error leyendo catalog.json:", e)
    return []

def github_put_file(catalog_list):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None
    r_get = requests.get(api_url, headers=headers, timeout=15)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    content_b64 = base64.b64encode(json.dumps(catalog_list, ensure_ascii=False, indent=2).encode()).decode()
    body = {"message": "Update catalog", "content": content_b64}
    if sha:
        body["sha"] = sha
    r_put = requests.put(api_url, headers=headers, json=body, timeout=20)
    return r_put.status_code in (200,201)

def allowed_chat(message):
    if not ALLOWED_CHAT_IDS:
        return True
    allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = message.get("chat", {}) or message.get("channel_post", {}).get("chat", {}) or {}
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed

def process_torrent_batch(torrent_paths):
    processed = []
    for t in torrent_paths:
        try:
            subprocess.run(["python", "rename.py", t], check=True)
            subprocess.run(["python", "magnet.py", t], check=True)
            processed.append(t)
        except subprocess.CalledProcessError as e:
            print(f"Error procesando {t}: {e}")
    return processed

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    msg = payload.get("channel_post") or payload.get("message")
    if not msg or not allowed_chat(payload):
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    # ---------------- Guardar torrents nuevos ----------------
    os.makedirs("torrents", exist_ok=True)
    new_torrents = []
    docs = []
    if msg.get("document") and msg["document"]["file_name"].lower().endswith(".torrent"):
        docs.append(msg["document"])
    elif msg.get("media_group_id") and "media_group" in msg:  # Para lotes (ej. galería)
        docs.extend(msg.get("media_group", []))

    for doc in docs:
        file_id = doc.get("file_id")
        filename = doc.get("file_name")
        if BOT_TOKEN and file_id:
            getf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=20)
            if getf.status_code == 200:
                file_path = getf.json().get("result", {}).get("file_path")
                if file_path:
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                    r = requests.get(file_url, timeout=30)
                    if r.status_code == 200:
                        path_local = os.path.join("torrents", filename)
                        with open(path_local, "wb") as f:
                            f.write(r.content)
                        new_torrents.append(path_local)

    if not new_torrents:
        return JSONResponse({"ok": True, "info": "no torrents found"})

    # ---------------- Ejecutar rename.py + magnet.py en lote ----------------
    processed = process_torrent_batch(new_torrents)

    # ---------------- Merge incremental al catalog.json ----------------
    catalog = get_raw_github_file() or []
    existing_sources = {item["source"] for item in catalog}

    for t in processed:
        json_path = t + ".json"
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                info = json.load(f)
                if info["source"] not in existing_sources:
                    catalog.append(info)

    if catalog:
        github_put_file(catalog)
        print(f"Catalog actualizado con {len(processed)} torrents nuevos")

    return JSONResponse({"ok": True, "added": len(processed)})
