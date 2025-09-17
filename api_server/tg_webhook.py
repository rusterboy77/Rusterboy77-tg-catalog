from fastapi import APIRouter, Request
import requests, json, base64, os

router = APIRouter()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Coloca tu token en variables de entorno
GITHUB_REPO = "Rusterboy77/Rusterboy77-tg-catalog"
CATALOG_PATH = "catalog.json"
BRANCH = "main"

@router.post("/api/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    message = data.get("message") or data.get("channel_post")
    if not message:
        return {"ok": True}

    torrent_entry = None

    # 1️⃣ Magnet links en texto
    text = message.get("text", "")
    if text and text.startswith("magnet:"):
        torrent_entry = {
            "title": "Torrent de prueba",
            "source": text,
            "type": "magnet"
        }

    # 2️⃣ Archivos .torrent
    elif "document" in message and message["document"]["file_name"].endswith(".torrent"):
        file_name = message["document"]["file_name"]
        file_id = message["document"]["file_id"]
        torrent_entry = {
            "title": file_name,
            "source": file_id,  # más adelante podrías usar Telegram API para descargar el archivo si quieres
            "type": "torrent"
        }

    if not torrent_entry:
        return {"ok": True}

    # Leer catalog.json desde GitHub
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{CATALOG_PATH}"
    r = requests.get(url)
    catalog = r.json() if r.status_code == 200 else []

    catalog.append(torrent_entry)

    # Obtener SHA del archivo actual
    url_put = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CATALOG_PATH}"
    r_sha = requests.get(url_put, headers={"Authorization": f"token {GITHUB_TOKEN}"})
    sha = r_sha.json().get("sha") if r_sha.status_code == 200 else None

    # Preparar contenido base64
    content_b64 = base64.b64encode(json.dumps(catalog, indent=2).encode()).decode()

    data_put = {
        "message": f"Add torrent {torrent_entry['title']} from Telegram",
        "content": content_b64,
        "branch": BRANCH
    }
    if sha:
        data_put["sha"] = sha

    r_put = requests.put(url_put, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json=data_put)
    if r_put.status_code not in [200, 201]:
        print("Error updating catalog.json:", r_put.text)

    return {"ok": True}
