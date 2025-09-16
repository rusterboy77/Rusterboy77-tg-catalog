# api/index.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os
import json

# Configuración
GITHUB_REPO = os.environ.get("GITHUB_REPO", "owner/repo")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = FastAPI()

# Función para actualizar catalog.json en GitHub
def update_github_catalog(catalog_data):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # Obtener sha del archivo si existe
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json()["sha"]
    else:
        sha = None

    content = json.dumps(catalog_data, indent=2).encode("utf-8")
    import base64
    data = {
        "message": "Update catalog",
        "content": base64.b64encode(content).decode("utf-8"),
    }
    if sha:
        data["sha"] = sha

    r = requests.put(url, headers=headers, json=data)
    return r.status_code, r.text

# Webhook para recibir mensajes de Telegram
@app.post("/api/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    # Solo procesamos mensajes de canal
    message = data.get("channel_post")
    if not message:
        return JSONResponse({"ok": True, "message": "ignored non-channel message"})

    text = message.get("text", "")
    document = message.get("document", {})
    catalog = []

    # Procesar magnet o archivo .torrent
    if text.startswith("magnet:"):
        catalog.append({"title": text[:50], "magnet": text})
    elif document.get("file_name", "").endswith(".torrent"):
        # Generar URL pública del torrent (ej: Dropbox, GitHub raw, etc.)
        url = f"https://example.com/torrents/{document['file_name']}"
        catalog.append({"title": document["file_name"], "url": url})

    # Leer catalog.json existente de GitHub
    r = requests.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}")
    if r.status_code == 200:
        existing_catalog = r.json()
    else:
        existing_catalog = []

    updated_catalog = existing_catalog + catalog
    # Actualizar en GitHub
    update_github_catalog(updated_catalog)

    return JSONResponse({"ok": True, "added": len(catalog)})

# Endpoint para que Kodi consuma
@app.get("/api/catalog")
async def catalog():
    r = requests.get(f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}")
    if r.status_code == 200:
        return JSONResponse(r.json())
    else:
        return JSONResponse([], status_code=200)

