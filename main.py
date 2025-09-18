import os, json, base64, subprocess, requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

app = FastAPI(title="TG -> Catalog API")

# ---------------- utilidades ----------------
def get_raw_github_file():
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("[DEBUG] Error leyendo catalog.json:", e)
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
    if r_put.status_code in (200,201):
        print("[DEBUG] catalog.json actualizado correctamente")
        return True
    print("[DEBUG] Error subiendo catalog.json:", r_put.text)
    return False

def save_torrent_to_github(filename, binary_content):
    path = f"torrents/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(binary_content).decode("utf-8")
    body = {"message": f"Add torrent {filename}", "content": content_b64}
    r = requests.put(api_url, headers=headers, json=body, timeout=30)
    if r.status_code in (200,201):
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
        print(f"[DEBUG] Torrent subido: {raw_url}")
        return raw_url
    print(f"[DEBUG] Error subiendo torrent {filename}: {r.text}")
    return ""

def allowed_chat(message):
    if not ALLOWED_CHAT_IDS:
        return True
    allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = message.get("chat", {}) or message.get("channel_post", {}).get("chat", {}) or {}
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed

# ---------------- webhook ----------------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message payload"})
    if not allowed_chat(payload):
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    # ---------------- subir torrents a GitHub ----------------
    found_items = []
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        if BOT_TOKEN and file_id:
            getf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=20)
            if getf.status_code == 200:
                file_path = getf.json().get("result", {}).get("file_path")
                if file_path:
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                    r = requests.get(file_url, timeout=30)
                    if r.status_code == 200:
                        filename = doc.get("file_name")
                        raw_url = save_torrent_to_github(filename, r.content)
                        if raw_url:
                            found_items.append({"title": filename, "source": raw_url, "type": "torrent"})

    if not found_items:
        return JSONResponse({"ok": True, "added": 0})

    # ---------------- merge con catalog.json existente ----------------
    existing = get_raw_github_file() or []
    existing_map = {it.get("source"): it for it in existing}
    for it in found_items:
        existing_map[it.get("source")] = it
    merged = list(existing_map.values())

    # ---------------- ejecutar scripts rename y magnet ----------------
    try:
        print("[DEBUG] Ejecutando rename.py...")
        subprocess.run(["python", "rename.py"], check=True)
        print("[DEBUG] Ejecutando magnet.py...")
        subprocess.run(["python", "magnet.py"], check=True)
        print("[DEBUG] Scripts A y B ejecutados correctamente")
    except Exception as e:
        print("[ERROR] Fallo ejecutando scripts:", e)

    github_put_file(merged)
    return JSONResponse({"ok": True, "added": len(found_items)})

# ---------------- catalog endpoint ----------------
@app.get("/api/catalog")
async def catalog():
    items = get_raw_github_file()
    return JSONResponse(items)
