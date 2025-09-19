# main.py - Versión optimizada
import os
import json
import logging
import datetime
import subprocess
import requests
import base64
import tempfile
import gc
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# --- Config desde env ---
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

# --- Logger optimizado ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("tgcatalog")

# --- Para evitar bucles (optimizado) ---
processed_files = set()
MAX_PROCESSED_FILES = 50  # Reducido

def allowed_chat(payload: dict) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    allowed_ids = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = (payload.get("message", {}).get("chat") or 
            payload.get("channel_post", {}).get("chat") or {})
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed_ids

app = FastAPI(title="TG -> Catalog API")

def cleanup_processed_files():
    global processed_files
    if len(processed_files) > MAX_PROCESSED_FILES:
        processed_files.clear()
        gc.collect()
        logger.info("Cleaned up processed_files set")

def run_script_collect(script_name: str, args: list, timeout: int = 15):  # Timeout reducido
    cmd = ["python", script_name] + args
    try:
        proc = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        if proc.stderr:
            logger.warning("stderr (%s): %s", script_name, proc.stderr[:100])
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout ejecutando %s", script_name)
        return -2, "", "timeout"
    except Exception as e:
        logger.error("Error ejecutando script %s: %s", script_name, str(e))
        return -1, "", str(e)

def load_local_catalog():
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
        response = requests.get(url, timeout=10)
        return response.json() if response.status_code == 200 else {"movies": {}, "series": {}}
    except Exception as e:
        logger.error("Error downloading catalog: %s", str(e))
        return {"movies": {}, "series": {}}

def save_local_catalog(catalog_data):
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}", 
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Obtener SHA actual
        current_file = requests.get(url, headers=headers, timeout=10)
        sha = current_file.json().get("sha") if current_file.status_code == 200 else None
        
        # Optimizar JSON
        content = json.dumps(catalog_data, ensure_ascii=False, separators=(',', ':'))
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        data = {
            "message": f"Update catalog - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            "content": content_b64,
            "sha": sha
        }
        
        response = requests.put(url, headers=headers, json=data, timeout=15)
        return response.status_code in [200, 201]
    except Exception as e:
        logger.error("Error uploading to GitHub: %s", str(e))
        return False

def save_torrent_to_github(file_content, filename):
    """Sube el torrent a GitHub solo si es pequeño"""
    try:
        # Limitar tamaño máximo (5MB)
        if len(file_content) > 5 * 1024 * 1024:
            logger.warning("Torrent demasiado grande para subir: %s", filename)
            return False
            
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/torrents/{filename}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}", 
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Verificar si ya existe
        current_file = requests.get(url, headers=headers, timeout=10)
        sha = current_file.json().get("sha") if current_file.status_code == 200 else None
        
        content_b64 = base64.b64encode(file_content).decode("utf-8")
        
        data = {
            "message": f"Add torrent - {filename}",
            "content": content_b64,
            "sha": sha
        }
        
        response = requests.put(url, headers=headers, json=data, timeout=15)
        if response.status_code in [200, 201]:
            logger.info("Torrent uploaded to GitHub: %s", filename)
            return True
        else:
            logger.warning("Failed to upload torrent: %s", response.text[:200])
            return False
    except Exception as e:
        logger.error("Error uploading torrent: %s", str(e))
        return False
    
def update_catalog_with_torrent(metadata, magnet_data, file_size_bytes):
    catalog = load_local_catalog()
    
    size_gb = round(file_size_bytes / (1024**3), 2)
    size_str = f"{size_gb} GB"
    
    category = metadata.get("type", "movie")
    if category not in catalog:
        category = "movie"
    
    if category == "series":
        season = metadata.get("season", 1)
        key = f"{metadata['title']}||S{season}"
    else:
        key = f"{metadata['title']}||{metadata.get('year', '')}"
    
    if key not in catalog[category]:
        catalog[category][key] = {
            "title": metadata["title"],
            "year": str(metadata.get("year", "")),
            "torrents": []
        }
    
    new_torrent = {
        "magnet": magnet_data["magnet"],
        "infohash": magnet_data["infohash"],
        "quality": metadata.get("quality", "Unknown"),
        "size": size_str,
        "added": datetime.datetime.utcnow().isoformat() + "Z"
    }
    
    # Verificar si ya existe
    existing_hashes = [t.get("infohash") for t in catalog[category][key]["torrents"]]
    if magnet_data["infohash"] not in existing_hashes:
        catalog[category][key]["torrents"].append(new_torrent)
        logger.info("Added torrent to catalog: %s", key)
        return save_local_catalog(catalog)
    
    return True  # Ya existe, no hacer nada

async def process_torrent_from_content(file_content, original_name):
    """Procesa el torrent optimizando memoria"""
    temp_path = None
    try:
        # Verificar tamaño máximo (10MB)
        if len(file_content) > 10 * 1024 * 1024:
            logger.warning("Torrent demasiado grande: %s (%d bytes)", original_name, len(file_content))
            return False
        
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        # Ejecutar rename.py
        rc_rename, out_rename, err_rename = run_script_collect("rename.py", [original_name])
        if rc_rename != 0:
            logger.error("Error en rename.py: %s", err_rename)
            return False
        
        metadata = json.loads(out_rename)
        
        # Ejecutar magnet.py
        rc_magnet, out_magnet, err_magnet = run_script_collect("magnet.py", [temp_path])
        if rc_magnet != 0:
            logger.error("Error en magnet.py: %s", err_magnet)
            return False
        
        magnet_data = json.loads(out_magnet)
        
        # Subir torrent a GitHub (opcional)
        if len(file_content) < 2 * 1024 * 1024:  # Solo subir si < 2MB
            save_torrent_to_github(file_content, original_name)
        
        # Actualizar catálogo
        file_size = len(file_content)
        return update_catalog_with_torrent(metadata, magnet_data, file_size)
            
    except json.JSONDecodeError as e:
        logger.error("Error decoding JSON: %s", str(e))
        return False
    except Exception as e:
        logger.error("Error processing torrent: %s", str(e))
        return False
    finally:
        # Limpiar archivo temporal
        try:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass
        # Forzar garbage collection
        gc.collect()

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    cleanup_processed_files()

    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message"})

    # Verificación antibucle
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        if file_id in processed_files:
            logger.info("File already processed: %s", file_id)
            return JSONResponse({"ok": True, "info": "already processed"})
        processed_files.add(file_id)

    if not allowed_chat(payload):
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    processed = []
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        orig_name = doc.get("file_name", "file.torrent").replace("\r", "").replace("\n", "").strip()

        if not BOT_TOKEN:
            return JSONResponse({"ok": False, "error": "no bot token"}, status_code=500)

        try:
            # Descargar torrent con límite de tamaño
            gf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=10)
            file_path = gf.json().get("result", {}).get("file_path")
            if not file_path:
                return JSONResponse({"ok": False, "error": "no file path"})
            
            dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            r = requests.get(dl_url, timeout=30, stream=True)
            
            if r.status_code == 200:
                # Leer contenido con límite
                max_size = 15 * 1024 * 1024  # 15MB máximo
                content = b""
                for chunk in r.iter_content(chunk_size=8192):
                    content += chunk
                    if len(content) > max_size:
                        logger.warning("Torrent excede tamaño máximo: %s", orig_name)
                        break
                
                if len(content) <= max_size:
                    success = await process_torrent_from_content(content, orig_name)
                    processed.append({"file": orig_name, "success": success})
                else:
                    processed.append({"file": orig_name, "success": False, "error": "size_limit"})
                
        except Exception as e:
            logger.error("Error processing: %s", str(e))

    return JSONResponse({"ok": True, "processed": processed})

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/")
async def root():
    return {"message": "TG Catalog API", "status": "running"}