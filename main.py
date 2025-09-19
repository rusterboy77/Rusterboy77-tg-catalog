# main.py - Versión completa y corregida
import os
import json
import logging
import datetime
import subprocess
import requests
import base64
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# --- Config desde env ---
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # tu token de Telegram
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")  # opcional
DEBUG_SAVE_PAYLOADS = True
DEBUG_DIR = "debug"
TORRENTS_DIR = "torrents"

os.makedirs(DEBUG_DIR, exist_ok=True)
os.makedirs(TORRENTS_DIR, exist_ok=True)

# --- Logger ---
logger = logging.getLogger("tgcatalog")
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(sh)

# rotate minimal file logging for payloads (append as jsonl)
PAYLOADS_FILE = os.path.join(DEBUG_DIR, "payloads.jsonl")
STATUS_FILE = os.path.join(DEBUG_DIR, "status.jsonl")

# --- Para evitar bucles ---
processed_files = set()

app = FastAPI(title="TG -> Catalog API")

def save_payload(payload: dict):
    if not DEBUG_SAVE_PAYLOADS:
        return
    try:
        entry = {"ts": datetime.datetime.utcnow().isoformat()+"Z", "payload": payload}
        with open(PAYLOADS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.exception("Error guardando payload: %s", e)

def tail_jsonl(path, n=20):
    # lee últimas n líneas de un archivo jsonl (si existe)
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        last = lines[-n:]
        return [json.loads(l) for l in last if l.strip()]
    except Exception as e:
        logger.exception("tail_jsonl error: %s", e)
        return []

def save_status(obj: dict):
    try:
        obj2 = {"ts": datetime.datetime.utcnow().isoformat()+"Z", **obj}
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj2, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.exception("Error saving status: %s", e)

def allowed_chat(payload: dict) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    # look for chat id in payload
    chat = payload.get("message", {}).get("chat") or payload.get("channel_post", {}).get("chat") or {}
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed

def sanitize_filename(name: str) -> str:
    # Keep it simple: remove control chars and trim
    safe = "".join(ch for ch in name if ord(ch) >= 32)
    return safe.replace("\r", "").replace("\n", "").strip()

def run_script_collect(script_name: str, args: list, timeout: int = 60):
    """Ejecuta un script local (rename.py / magnet.py) y captura stdout/stderr."""
    cmd = ["python", script_name] + args
    logger.info("Ejecutando script: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        logger.info("%s exit=%s stdout_len=%d stderr_len=%d", script_name, proc.returncode, len(proc.stdout or ""), len(proc.stderr or ""))
        if proc.stdout:
            logger.debug("stdout (%s):\n%s", script_name, proc.stdout.strip())
        if proc.stderr:
            logger.error("stderr (%s):\n%s", script_name, proc.stderr.strip())
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.CalledProcessError as e:
        logger.exception("CalledProcessError running %s: %s", script_name, e)
        return getattr(e, "returncode", -1), "", str(e)
    except Exception as e:
        logger.exception("Error ejecutando script %s: %s", script_name, e)
        return -1, "", str(e)

def load_local_catalog():
    """Descarga el catalog.json actual desde GitHub"""
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Catalog not found on GitHub, creating new one. Status: {response.status_code}")
            return {"movies": {}, "series": {}}
    except Exception as e:
        logger.error(f"Error downloading catalog from GitHub: {e}")
        return {"movies": {}, "series": {}}

def save_local_catalog(catalog_data):
    """Sube el catalog.json actualizado a GitHub"""
    try:
        # Primero obtener el SHA del archivo actual (si existe)
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Obtener SHA del archivo actual
        current_file_response = requests.get(url, headers=headers, timeout=30)
        sha = None
        if current_file_response.status_code == 200:
            sha = current_file_response.json().get("sha")
        
        # Preparar contenido para subir
        content = json.dumps(catalog_data, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        data = {
            "message": f"Update catalog - {datetime.datetime.utcnow().isoformat()}",
            "content": content_b64,
            "sha": sha  # Necesario para actualizar existente
        }
        
        # Subir a GitHub
        response = requests.put(url, headers=headers, json=data, timeout=30)
        
        if response.status_code in [200, 201]:
            logger.info("Catalog.json updated successfully on GitHub")
            return True
        else:
            logger.error(f"Failed to update catalog on GitHub: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.exception(f"Error uploading catalog to GitHub: {e}")
        return False
    
def update_catalog_with_torrent(metadata, magnet_data, file_size_bytes):
    """
    Actualiza el catalog.json con el nuevo torrent
    metadata: from rename.py (dict con title, year, quality, type, etc.)
    magnet_data: from magnet.py (dict con infohash, magnet, trackers)
    file_size_bytes: tamaño del archivo en bytes
    """
    catalog = load_local_catalog()
    
    # Convertir tamaño a formato legible
    size_gb = round(file_size_bytes / (1024**3), 2)
    size_str = f"{size_gb} GB"
    
    # Determinar categoría
    category = metadata.get("type", "movie")
    if category not in catalog:
        category = "movie"  # Fallback
    
    # Crear clave única (como en tu JSON existente)
    if category == "series":
        season = metadata.get("season", 1)
        key = f"{metadata['title']}||S{season}"
    else:
        key = f"{metadata['title']}||{metadata.get('year', '')}"
    
    # Crear entrada si no existe
    if key not in catalog[category]:
        catalog[category][key] = {
            "title": metadata["title"],
            "year": str(metadata.get("year", "")),
            "torrents": []
        }
    
    # Crear objeto torrent
    new_torrent = {
        "magnet": magnet_data["magnet"],
        "infohash": magnet_data["infohash"],
        "quality": metadata.get("quality", "Unknown"),
        "size": size_str,
        "added": datetime.datetime.utcnow().isoformat() + "Z"
    }
    
    # Evitar duplicados por infohash
    existing_hashes = [t.get("infohash") for t in catalog[category][key]["torrents"]]
    if magnet_data["infohash"] not in existing_hashes:
        catalog[category][key]["torrents"].append(new_torrent)
        logger.info(f"Added new torrent to catalog: {key}")
    else:
        logger.info(f"Torrent already exists in catalog: {magnet_data['infohash']}")
    
    # Guardar cambios
    return save_local_catalog(catalog)

async def process_torrent_file(file_path, original_name):
    """Procesa un archivo torrent completo: rename -> magnet -> catalog"""
    try:
        # 1. Ejecutar rename.py para obtener metadatos
        rc_rename, out_rename, err_rename = run_script_collect("rename.py", [original_name])
        if rc_rename != 0:
            logger.error(f"rename.py failed: {err_rename}")
            return False
        
        metadata = json.loads(out_rename)
        
        # 2. Ejecutar magnet.py para obtener magnet link
        rc_magnet, out_magnet, err_magnet = run_script_collect("magnet.py", [file_path])
        if rc_magnet != 0:
            logger.error(f"magnet.py failed: {err_magnet}")
            return False
        
        magnet_data = json.loads(out_magnet)
        
        # 3. Obtener tamaño del archivo
        file_size = os.path.getsize(file_path)
        
        # 4. Actualizar catalog.json
        success = update_catalog_with_torrent(metadata, magnet_data, file_size)
        
        if success:
            logger.info(f"Successfully processed and added to catalog: {original_name}")
            return {
                "metadata": metadata,
                "magnet_data": magnet_data,
                "catalog_updated": True
            }
        else:
            logger.error(f"Failed to update catalog for: {original_name}")
            return False
            
    except Exception as e:
        logger.exception(f"Error processing torrent {original_name}: {e}")
        return False

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/api/debug/last")
async def debug_last(n: int = 10):
    payloads = tail_jsonl(PAYLOADS_FILE, n)
    statuses = tail_jsonl(STATUS_FILE, n)
    return JSONResponse({"payloads": payloads, "statuses": statuses})

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception as e:
        logger.exception("Invalid JSON payload")
        return JSONResponse({"ok": False, "error": "invalid json", "details": str(e)}, status_code=400)

    logger.info("Nuevo webhook recibido")
    save_payload(payload)

    if not allowed_chat(payload):
        logger.warning("Chat no permitido. payload minimal: %s", {k: payload.get(k) for k in ("update_id",)})
        save_status({"event":"chat_not_allowed", "payload_snippet": {"update_id": payload.get("update_id")}})
        return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        logger.info("No message / channel_post in payload")
        save_status({"event":"no_message"})
        return JSONResponse({"ok": True, "info": "no message payload"})

    # --- EVITAR BUCLE: Verificar si ya procesamos este file_id ---
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        if file_id in processed_files:
            logger.info(f"File {file_id} already processed, skipping")
            return JSONResponse({"ok": True, "info": "already processed"})
        
        # Marcar como procesado
        processed_files.add(file_id)

    # Debug: log what type of message we received
    logger.debug("Message keys: %s", list(msg.keys()))
    # Search magnets in text/caption
    text = msg.get("text") or msg.get("caption") or ""
    if text:
        logger.debug("Text received (first 200 chars): %s", text[:200])

    # If document .torrent present: download it
    processed = []
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        orig_name = sanitize_filename(doc.get("file_name", "file.torrent"))
        logger.info("Detected .torrent document: %s file_id=%s", orig_name, file_id)

        # Step: get file_path
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not set, cannot download file from Telegram")
            save_status({"event":"no_bot_token", "file": orig_name})
            return JSONResponse({"ok": False, "error": "no bot token"}, status_code=500)

        try:
            gf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=15)
            logger.debug("getFile status: %s", gf.status_code)
            gfj = gf.json()
            logger.debug("getFile json keys: %s", gfj.keys() if isinstance(gfj, dict) else "no-json")
            file_path = gfj.get("result", {}).get("file_path")
            if not file_path:
                logger.error("No file_path returned by getFile: %s", gfj)
                save_status({"event":"no_file_path", "file": orig_name, "getfile_resp": gfj})
            else:
                dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                r = requests.get(dl_url, timeout=30)
                logger.info("Download torrent %s status=%s len=%d", orig_name, r.status_code, len(r.content) if r.status_code==200 else 0)
                if r.status_code == 200:
                    save_path = os.path.join(TORRENTS_DIR, orig_name)
                    # ensure unique: if exists, append counter
                    if os.path.exists(save_path):
                        base, ext = os.path.splitext(orig_name)
                        i=1
                        while os.path.exists(os.path.join(TORRENTS_DIR, f"{base} ({i}){ext}")):
                            i+=1
                        save_path = os.path.join(TORRENTS_DIR, f"{base} ({i}){ext}")
                    with open(save_path, "wb") as f:
                        f.write(r.content)
                    logger.info("Saved torrent to %s", save_path)
                    save_status({"event": "torrent_saved", "file": os.path.basename(save_path), "size": os.path.getsize(save_path)})
                    
                    # Procesar el torrent completo: rename -> magnet -> catalog
                    processing_result = await process_torrent_file(save_path, orig_name)
                    if processing_result:
                        processed.append({
                            "file": os.path.basename(save_path),
                            "success": True,
                            "title": processing_result["metadata"]["title"]
                        })
                    else:
                        processed.append({
                            "file": os.path.basename(save_path),
                            "success": False
                        })
                        
                else:
                    save_status({"event":"download_failed", "status": r.status_code, "file": orig_name})
        except Exception as e:
            logger.exception("Exception downloading/saving torrent %s: %s", orig_name, e)
            save_status({"event":"exception_download", "file": orig_name, "error": str(e)})
    else:
        logger.debug("No document torrent found in message")

    return JSONResponse({"ok": True, "processed": processed})