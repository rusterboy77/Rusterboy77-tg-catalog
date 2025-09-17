# main.py
import os
import re
import json
import base64
import requests
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api_server.tg_webhook import router as tg_router

app = FastAPI()
app.include_router(tg_router)


# ------------- CONFIG desde variables de entorno -------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")       # format owner/repo
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")     # PAT with repo permissions
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")           # token del bot de Telegram
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")  # opcional csv de chat ids a aceptar (seguridad)

# ------------- constantes y utilidades -------------
MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)

app = FastAPI(title="TG -> Catalog API")

def get_raw_github_file():
    """
    Lee el raw content de GitHub (raw.githubusercontent.com owner/main/<path>)
    Devuelve lista (si existe) o [].
    """
    if not GITHUB_REPO:
        return []
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    r = requests.get(raw_url, timeout=15)
    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return []
    return []

def github_put_file(catalog_list: List[Dict]):
    """
    Crea/actualiza el archivo en el repo GitHub usando la API (PUT /repos/:owner/:repo/contents/:path)
    """
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return False, "No repo/token configured"

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    # obtener sha si existe
    get_resp = requests.get(api_url, headers=headers, timeout=15)
    sha = None
    if get_resp.status_code == 200:
        try:
            sha = get_resp.json().get("sha")
        except Exception:
            sha = None

    content_b64 = base64.b64encode(json.dumps(catalog_list, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    body = {
        "message": "Update catalog from webhook",
        "content": content_b64
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(api_url, headers=headers, json=body, timeout=20)
    return resp.status_code in (200, 201), resp.text

def save_torrent_to_github(filename: str, binary_content: bytes) -> str:
    """
    Guarda un .torrent en el repo en la carpeta 'torrents/' y devuelve la URL raw si OK.
    """
    if not (GITHUB_REPO and GITHUB_TOKEN):
        return ""
    path = f"torrents/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(binary_content).decode("utf-8")
    body = {"message": f"Add torrent {filename}", "content": content_b64}
    resp = requests.put(api_url, headers=headers, json=body, timeout=30)
    if resp.status_code in (200,201):
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
        return raw_url
    return ""

def allowed_chat(message: Dict) -> bool:
    """
    Opcional: si ALLOWED_CHAT_IDS configurado, filtrar para aceptar sólo ese canal/chat.
    """
    if not ALLOWED_CHAT_IDS:
        return True
    allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = message.get("chat", {}) or message.get("channel_post", {}).get("chat", {}) or {}
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed

# ------------------ ENDPOINT webhook ------------------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    """
    Receives Telegram webhook (channel_post or message). Extracts magnet links and .torrent files.
    Updates catalog.json in GitHub.
    """
    try:
        payload = await req.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": "invalid json", "details": str(e)}, status_code=400)

    # Telegram uses 'channel_post' for channels or 'message' for groups/private
    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message payload"})

    # security: optional filter by chat id
    if not allowed_chat(payload):
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    found_items = []

    # 1) search for magnet links in text/caption
    text = msg.get("text") or msg.get("caption") or ""
    for m in MAGNET_RE.findall(str(text)):
        item = {
            "title": (text.splitlines()[0][:120] if text else m) or m,
            "source": m,
            "type": "magnet"
        }
        found_items.append(item)

    # 2) check for .torrent document
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        # download file from Telegram servers using Bot API getFile
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
                            found_items.append({
                                "title": filename,
                                "source": raw_url,
                                "type": "torrent"
                            })

    # If found_items, merge into existing catalog on GitHub
    if found_items:
        existing = get_raw_github_file() or []
        # merge avoiding duplicates by 'source'
        existing_map = {it.get("source"): it for it in existing}
        for it in found_items:
            existing_map[it.get("source")] = it
        merged = list(existing_map.values())
        ok, resp_text = github_put_file(merged)
        if ok:
            return JSONResponse({"ok": True, "added": len(found_items)})
        else:
            return JSONResponse({"ok": False, "error": "github_put_failed", "details": resp_text}, status_code=500)

    return JSONResponse({"ok": True, "added": 0})

# ------------------ ENDPOINT catalog ------------------
@app.get("/api/catalog")
async def catalog():
    items = get_raw_github_file()
    return JSONResponse(items)
