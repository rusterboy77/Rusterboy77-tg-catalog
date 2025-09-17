# main.py
import os
import re
import json
import base64
import requests
from typing import List, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------- CONFIG ----------------
GITHUB_REPO = os.environ.get("GITHUB_REPO")       # "usuario/repo"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")     # PAT con permisos
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN")           # token del bot
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")  # csv de chat ids

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)

app = FastAPI(title="TG -> Catalog API")

# ---------------- UTILIDADES ----------------
def allowed_chat(msg: Dict) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    return chat_id in [x.strip() for x in ALLOWED_CHAT_IDS.split(",")]

def get_github_catalog() -> List[Dict]:
    if not GITHUB_REPO:
        return []
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    r = requests.get(url, timeout=15)
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return []
    return []

def save_torrent_to_github(filename: str, content: bytes) -> str:
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return ""
    path = f"torrents/{filename}"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(content).decode("utf-8")
    body = {"message": f"Add torrent {filename}", "content": content_b64}
    r = requests.put(url, headers=headers, json=body, timeout=30)
    if r.status_code in (200,201):
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
    return ""

def update_github_catalog(items: List[Dict]):
    catalog = get_github_catalog()
    # merge evitando duplicados por 'source'
    existing = {x["source"]: x for x in catalog}
    for it in items:
        existing[it["source"]] = it
    merged = list(existing.values())

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r_sha = requests.get(url, headers=headers, timeout=15)
    sha = r_sha.json().get("sha") if r_sha.status_code == 200 else None
    content_b64 = base64.b64encode(json.dumps(merged, indent=2).encode()).decode("utf-8")
    body = {"message": "Update catalog from webhook", "content": content_b64}
    if sha:
        body["sha"] = sha
    requests.put(url, headers=headers, json=body, timeout=30)

# ---------------- ENDPOINT webhook ----------------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": "invalid json", "details": str(e)}, status_code=400)

    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message payload"})

    if not allowed_chat(msg):
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    found_items = []

    # 1️⃣ magnet links
    text = msg.get("text") or msg.get("caption") or ""
    for m in MAGNET_RE.findall(text):
        found_items.append({"title": text.splitlines()[0][:120] or m, "source": m, "type": "magnet"})

    # 2️⃣ .torrent files
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent") and BOT_TOKEN:
        file_id = doc.get("file_id")
        getf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=15)
        if getf.status_code == 200:
            file_path = getf.json().get("result", {}).get("file_path")
            if file_path:
                r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=30)
                if r.status_code == 200:
                    raw_url = save_torrent_to_github(doc.get("file_name"), r.content)
                    if raw_url:
                        found_items.append({"title": doc.get("file_name"), "source": raw_url, "type": "torrent"})

    if found_items:
        update_github_catalog(found_items)
        return JSONResponse({"ok": True, "added": len(found_items)})

    return JSONResponse({"ok": True, "added": 0})

# ---------------- ENDPOINT catalog ----------------
@app.get("/api/catalog")
async def catalog():
    items = get_github_catalog()
    return JSONResponse(items)
