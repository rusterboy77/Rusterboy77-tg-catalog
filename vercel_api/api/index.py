# api/index.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os
import json
import base64

# Configuración desde variables de entorno
GITHUB_REPO = os.environ.get("GITHUB_REPO", "owner/repo")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = FastAPI()

# 🔹 Función: actualizar catalog.json en GitHub
def update_github_catalog(catalog_data):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    resp = requests.get(url, headers=headers)
    sha = resp.json()["sha"] if resp.status_code == 200 else None

    content = json.dumps(catalog_data, indent=2).encode("utf-8")
    data = {
        "message": "Update catalog",
        "content": base64.b64encode(content).decode("utf-8"),
    }
    if sha:
        data["sha"] = sha

    r = requests.put(url, headers=headers, json=data)
    return r.status_code, r.text

# 🔹 Webhook de Telegram
@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    message = data.get("channel_post")
    if not message:
        return JSONResponse({"ok": True, "message": "ignored non-channel message"})

    text = message.get("text", "")
    document = message.get("document", {})
    catalog = []

    if text.startswith("magnet:"):
        catalog.append({"title": text[:50], "magnet": text})
    elif document.get("file_name", "").endswith(".torrent"):
        url = f"https://example.com/torrents/{document['file_name']}"  # 👈 cámbialo según dónde publiques los .torrent
        catalog.append({"title": document["file_name"], "url": url})

    # Leer catalog.json existente
    r = requests.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}")
    existing_catalog = r.json() if r.status_code == 200 else []

    updated_catalog = existing_catalog + catalog
    update_github_catalog(updated_catalog)

    return JSONResponse({"ok": True, "added": len(catalog)})

# 🔹 Catálogo para Kodi
@app.get("/api/catalog")
async def catalog():
    r = requests.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}")
    if r.status_code == 200:
        return JSONResponse(r.json())
    else:
        return JSONResponse([], status_code=200)


