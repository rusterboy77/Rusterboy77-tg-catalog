import os
import re
import json
import base64
import requests
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------- CONFIG ----------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)

app = FastAPI(title="TG -> Catalog API DEBUG")

# ---------------- UTILIDADES ----------------
def get_raw_github_file() -> List[Dict]:
    if not GITHUB_REPO:
        print("[DEBUG] GITHUB_REPO no definido")
        return []
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
    print(f"[DEBUG] Leyendo {raw_url}")
    try:
        r = requests.get(raw_url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[DEBUG] Error leyendo archivo de GitHub: {e}")
        return []

def github_put_file(catalog_list: List[Dict]):
    if not (GITHUB_REPO and GITHUB_TOKEN):
        print("[DEBUG] No hay repo o token definidos")
        return False, "No repo/token configured"

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    try:
        get_resp = requests.get(api_url, headers=headers, timeout=15)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None
    except Exception as e:
        print(f"[DEBUG] Error obteniendo SHA: {e}")
        sha = None

    content_b64 = base64.b64encode(json.dumps(catalog_list, ensure_ascii=False, indent=2).encode()).decode()
    body = {"message": "Update catalog from webhook", "content": content_b64}
    if sha:
        body["sha"] = sha

    try:
        resp = requests.put(api_url, headers=headers, json=body, timeout=20)
        if resp.status_code in (200, 201):
            print("[DEBUG] Archivo subido correctamente a GitHub")
            return True, resp.text
        else:
            print(f"[DEBUG] Error PUT GitHub: {resp.status_code} {resp.text}")
            return False, resp.text
    except Exception as e:
        print(f"[DEBUG] Exception PUT GitHub: {e}")
        return False, str(e)

def save_torrent_to_github(filename: str, binary_content: bytes) -> str:
    print(f"[DEBUG] Guardando torrent: {filename}, tamaño={len(binary_content)} bytes")
    path = f"torrents/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    content_b64 = base64.b64encode(binary_content).decode("utf-8")
    body = {"message": f"Add torrent {filename}", "content": content_b64}
    try:
        resp = requests.put(api_url, headers=headers, json=body, timeout=30)
        print(f"[DEBUG] PUT GitHub status: {resp.status_code}")
        if resp.status_code in (200, 201):
            raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
            print(f"[DEBUG] Torrent subido: {raw_url}")
            return raw_url
        else:
            print(f"[DEBUG] Error subiendo torrent {filename}: {resp.text}")
            return ""
    except Exception as e:
        print(f"[DEBUG] Exception subiendo torrent {filename}: {e}")
        return ""

def allowed_chat(message: Dict) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = message.get("chat", {}) or message.get("channel_post", {}).get("chat", {}) or {}
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed

# ---------------- WEBHOOK ----------------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception as e:
        print(f"[DEBUG] JSON invalido: {e}")
        return JSONResponse({"ok": False, "error": "invalid json", "details": str(e)}, status_code=400)

    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        print("[DEBUG] No message in payload")
        return JSONResponse({"ok": True, "info": "no message payload"})

    if not allowed_chat(payload):
        print("[DEBUG] Chat no permitido")
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    found_items = []

    # 1) Magnet links
    text = msg.get("text") or msg.get("caption") or ""
    for m in MAGNET_RE.findall(str(text)):
        print(f"[DEBUG] Magnet encontrado: {m}")
        found_items.append({"title": (text.splitlines()[0][:120] if text else m), "source": m, "type": "magnet"})

    # 2) Torrent documents
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
                        else:
                            print(f"[DEBUG] No se pudo subir el torrent {filename}")
                    else:
                        print(f"[DEBUG] Error descargando torrent {file_id}: {r.status_code}")
            else:
                print(f"[DEBUG] Error getFile Telegram: {getf.status_code}")

    if found_items:
        existing = get_raw_github_file() or []
        existing_map = {it.get("source"): it for it in existing}
        for it in found_items:
            existing_map[it.get("source")] = it
        merged = list(existing_map.values())
        ok, resp_text = github_put_file(merged)
        if ok:
            print(f"[DEBUG] {len(found_items)} items añadidos correctamente")
            return JSONResponse({"ok": True, "added": len(found_items)})
        else:
            print(f"[DEBUG] Error subiendo a GitHub: {resp_text}")
            return JSONResponse({"ok": False, "error": "github_put_failed", "details": resp_text}, status_code=500)

    return JSONResponse({"ok": True, "added": 0})

# ---------------- CATALOG ----------------
@app.get("/api/catalog")
async def catalog():
    items = get_raw_github_file()
    print(f"[DEBUG] Catalog request: {len(items)} items")
    return JSONResponse(items)
