import os
import json
import subprocess
from fastapi import FastAPI, Request

app = FastAPI()

TORRENTS_DIR = "torrents"
CATALOG_FILE = "catalog.json"

# Crear carpeta torrents si no existe
os.makedirs(TORRENTS_DIR, exist_ok=True)

# Cargar catálogo existente o crear uno vacío
if os.path.exists(CATALOG_FILE):
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)
else:
    catalog = {}

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    # Aquí se asume que Telegram envía: {"torrents": [{"name": "...", "content": "base64..."}]}
    torrents = data.get("torrents", [])
    
    for t in torrents:
        fname = t["name"]
        file_content = t["content"].encode("latin1")  # Ajusta según cómo recibas los bytes
        torrent_path = os.path.join(TORRENTS_DIR, fname)
        
        # Guardar archivo torrent
        with open(torrent_path, "wb") as f:
            f.write(file_content)
        
        # Ejecutar rename.py
        try:
            subprocess.run(["python", "rename.py", torrent_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] rename.py falló para {fname}: {e}")
            continue
        
        # Ejecutar magnet.py
        try:
            subprocess.run(["python", "magnet.py", torrent_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] magnet.py falló para {fname}: {e}")
            continue
        
        # Actualizar catalog.json
        # Aquí se asume que rename.py y magnet.py devuelven info que se puede leer
        # Por ejemplo: new_data = {"title": "...", "url": "...", "trackers": [...]}
        # Ajusta según cómo lo tengas implementado
        new_data = {
            "title": fname,  # Esto es un placeholder
            "url": f"https://raw.githubusercontent.com/tuusuario/tu-repo/main/torrents/{fname}",
            "trackers": ["udp://tracker.openbittorrent.com:80/announce"]
        }
        catalog[fname] = new_data
    
    # Guardar catálogo actualizado
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    return {"status": "ok", "processed": len(torrents)}
