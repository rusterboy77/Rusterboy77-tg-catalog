import os, re, json, base64, requests, subprocess
from typing import List, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------- Config ----------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CATALOG_PATH = os.environ.get("CATALOG_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")
TORRENTS_DIR = "torrents"

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)
app = FastAPI(title="TG -> Catalog API")

# ---------------- GitHub helpers ----------------
def get_raw_github_file(path: str) -> dict | list:
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[DEBUG] Error leyendo {path}:", e)
    return {}

def github_put_file(path: str, content: dict | list) -> bool:
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None
    r_get = requests.get(api_url, headers=headers, timeout=15)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    content_b64 = base64.b64encode(
        json.dumps(content, ensure_ascii=False, indent=2).encode()
    ).decode()

    body = {"message": f"Update {path}", "content": content_b64}
    if sha:
        body["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=body, timeout=20)
    if r_put.status_code in (200, 201):
        print(f"[DEBUG] {path} actualizado en GitHub ✅")
        return True
    print(f"[DEBUG] Error subiendo {path}:", r_put.text)
    return False

def save_torrent_to_github(filename: str, binary_content: bytes) -> str:
    os.makedirs(TORRENTS_DIR, exist_ok=True)
    path = f"{TORRENTS_DIR}/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(binary_content).decode("utf-8")
    body = {"message": f"Add torrent {filename}", "content": content_b64}
    r = requests.put(api_url, headers=headers, json=body, timeout=30)
    if r.status_code in (200, 201):
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
        print(f"[DEBUG] Torrent subido: {raw_url}")
        return filename  # devolvemos el nombre, lo usaremos en rename/magnet
    print(f"[DEBUG] Error subiendo torrent {filename}: {r.text}")
    return ""

def allowed_chat(message: Dict) -> bool:
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

    found_files = []
    text = msg.get("text") or msg.get("caption") or ""

    # detectar magnets
    for m in MAGNET_RE.findall(str(text)):
        print(f"[DEBUG] Magnet encontrado: {m}")
        found_files.append(m)

    # detectar archivos .torrent
    doc = msg.get("document")
    if doc and doc.get("file_name", "").lower().endswith(".torrent"):
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
                        saved = save_torrent_to_github(filename, r.content)
                        if saved:
                            found_files.append(saved)

    # si no hay nada, salimos
    if not found_files:
        return JSONResponse({"ok": True, "info": "no torrents found"})

    # ejecutamos rename.py y magnet.py solo sobre los nuevos torrents
    for fname in found_files:
        if fname.endswith(".torrent"):
            print(f"[DEBUG] Ejecutando rename.py para {fname}")
            subprocess.run(["python", "rename.py", fname], check=True)

            print(f"[DEBUG] Ejecutando magnet.py para {fname}")
            subprocess.run(["python", "magnet.py", fname], check=True)

    return JSONResponse({"ok": True, "added": len(found_files)})

# ---------------- catalog endpoint ----------------
@app.get("/api/catalog")
async def catalog():
    items = get_raw_github_file(CATALOG_PATH)
    return JSONResponse(items)
