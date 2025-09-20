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

# Configuración desde variables de entorno
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tgcatalog")

processed_files = set()
MAX_PROCESSED_FILES = 50

app = FastAPI(title="TG -> Catalog API")

def allowed_chat(payload: dict) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    allowed_ids = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
    chat = (payload.get("message", {}).get("chat") or payload.get("channel_post", {}).get("chat") or {})
    chat_id = str(chat.get("id", ""))
    return chat_id in allowed_ids

def cleanup_processed_files():
    global processed_files
    if len(processed_files) > MAX_PROCESSED_FILES:
        processed_files.clear()
        gc.collect()
        logger.info("Processed files set cleared")

def run_script_collect(script_name: str, args: list, timeout: int = 15):
    cmd = ["python", script_name] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PYTHONUNBUFFERED":"1"})
        if proc.stderr:
            logger.warning("stderr (%s): %s", script_name, proc.stderr.strip())
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout ejecutando %s", script_name)
        return -2, "", "timeout"
    except Exception as e:
        logger.error("Error ejecutando %s: %s", script_name, str(e))
        return -1, "", str(e)

def load_local_catalog():
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else {"movies": {}, "series": {}}
    except Exception as e:
        logger.error("Error downloading catalog: %s", e)
        return {"movies": {}, "series": {}}

def save_local_catalog(catalog_data):
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept":"application/vnd.github.v3+json"}
        current_file = requests.get(url, headers=headers, timeout=10)
        sha = current_file.json().get("sha") if current_file.status_code==200 else None
        content = base64.b64encode(json.dumps(catalog_data, ensure_ascii=False, separators=(',',':')).encode()).decode()
        data = {"message": f"Update catalog - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", "content": content, "sha": sha}
        resp = requests.put(url, headers=headers, json=data, timeout=15)
        if resp.status_code in [200,201]:
            logger.info("Catalog.json updated successfully in GitHub")
            return True
        else:
            logger.error("Failed to update catalog.json in GitHub: %s", resp.text)
            return False
    except Exception as e:
        logger.error("Error uploading to GitHub: %s", e)
        return False

async def process_torrent_from_content(file_content, original_name):
    temp_path = None
    magnet_data = None
    try:
        if len(file_content) > 15*1024*1024:
            logger.warning("Torrent demasiado grande: %s", original_name)
            return False, None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as f:
            f.write(file_content)
            temp_path = f.name
        
        # Ejecutar rename.py
        rc_rename, out_rename, _ = run_script_collect("rename.py", [original_name])
        if rc_rename != 0:
            logger.error("rename.py falló para %s", original_name)
            return False, None
        metadata = json.loads(out_rename)
        
        # Ejecutar magnet.py
        rc_magnet, out_magnet, _ = run_script_collect("magnet.py", [temp_path])
        if rc_magnet != 0:
            logger.error("magnet.py falló para %s", original_name)
            return False, None
        magnet_data = json.loads(out_magnet)
        
        # Guardar en GitHub inmediatamente
        catalog = load_local_catalog()
        catalog['movies'][original_name] = magnet_data
        saved = save_local_catalog(catalog)
        logger.info("Processed torrent: %s, catalog saved=%s", original_name, saved)
        
        gc.collect()
        return True, magnet_data
    finally:
        try: os.unlink(temp_path)
        except: pass
        gc.collect()

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    cleanup_processed_files()
    msg = payload.get("channel_post") or payload.get("message")
    if not msg: 
        return JSONResponse({"ok": True, "info": "no message"})
    
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        if file_id in processed_files: 
            return JSONResponse({"ok": True, "info": "already processed"})
        processed_files.add(file_id)
        orig_name = doc.get("file_name").replace("\r","").replace("\n","").strip()
        if not allowed_chat(payload): 
            return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)
        
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=10)
        file_path = r.json().get("result",{}).get("file_path")
        if not file_path: 
            return JSONResponse({"ok": False, "error": "no file path"})
        dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        r2 = requests.get(dl_url, timeout=30, stream=True)
        content = b"".join([chunk for chunk in r2.iter_content(chunk_size=8192) if chunk])
        
        success, magnet_data = await process_torrent_from_content(content, orig_name)
        return JSONResponse({"ok": True, "processed":[{"file": orig_name, "success": success}]})

@app.get("/api/health")
async def health(): 
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/")
async def root(): 
    return {"message": "TG Catalog API", "status": "running"}
