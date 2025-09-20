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

# Configuración
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_PATH = os.environ.get("GITHUB_PATH", "catalog.json")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")

# Logging completo
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
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
        logger.debug("Processed files set cleared")

def run_script_collect(script_name: str, args: list, timeout: int = 15):
    cmd = ["python", script_name] + args
    logger.debug("Running script: %s %s", script_name, args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PYTHONUNBUFFERED":"1"})
        logger.debug("Return code: %s", proc.returncode)
        if proc.stdout:
            logger.debug("stdout (%s): %s", script_name, proc.stdout.strip())
        if proc.stderr:
            logger.warning("stderr (%s): %s", script_name, proc.stderr.strip())
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        logger.error("Error running script %s: %s", script_name, e)
        return -1, "", str(e)

def load_local_catalog():
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{GITHUB_PATH}"
        logger.debug("Downloading catalog from %s", url)
        r = requests.get(url, timeout=10)
        logger.debug("GitHub response code: %s", r.status_code)
        return r.json() if r.status_code == 200 else {"movies": {}, "series": {}}
    except Exception as e:
        logger.error("Error downloading catalog: %s", e)
        return {"movies": {}, "series": {}}

def save_local_catalog(catalog_data):
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept":"application/vnd.github.v3+json"}
        current_file = requests.get(url, headers=headers, timeout=10)
        sha = current_file.json().get("sha") if current_file.status_code == 200 else None
        content = base64.b64encode(json.dumps(catalog_data, ensure_ascii=False, separators=(',',':')).encode()).decode()
        data = {"message": f"Update catalog - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", "content": content, "sha": sha}
        resp = requests.put(url, headers=headers, json=data, timeout=15)
        logger.debug("GitHub PUT status: %s", resp.status_code)
        if resp.status_code in [200, 201]:
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
    logger.info("Starting torrent processing: %s, size=%d bytes", original_name, len(file_content))
    try:
        if len(file_content) > 15*1024*1024:
            logger.warning("Torrent too large: %s", original_name)
            return False, None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as f:
            f.write(file_content)
            temp_path = f.name
        logger.debug("Temporary file created: %s", temp_path)

        rc_rename, out_rename, _ = run_script_collect("rename.py", [original_name])
        if rc_rename != 0:
            logger.error("rename.py failed for %s", original_name)
            return False, None

        logger.debug("rename.py output: %s", out_rename.strip())

        rc_magnet, out_magnet, _ = run_script_collect("magnet.py", [temp_path])
        if rc_magnet != 0:
            logger.error("magnet.py failed for %s", original_name)
            return False, None

        magnet_data = json.loads(out_magnet)
        logger.debug("magnet.py output: %s", out_magnet.strip())

        gc.collect()
        logger.info("Torrent %s processed successfully", original_name)
        return True, magnet_data
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
                logger.debug("Temporary file deleted: %s", temp_path)
            except Exception as e:
                logger.warning("Could not delete temporary file: %s", e)
        gc.collect()

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    logger.debug("Webhook payload: %s", json.dumps(payload))
    cleanup_processed_files()

    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        logger.debug("No message content in payload")
        return JSONResponse({"ok": True, "info": "no message"})

    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc.get("file_id")
        file_name = doc.get("file_name")
        logger.info("Received torrent: file_id=%s, file_name=%s", file_id, file_name)

        if file_id in processed_files:
            logger.info("Already processed file_id=%s", file_id)
            return JSONResponse({"ok": True, "info": "already processed"})
        processed_files.add(file_id)

        if not allowed_chat(payload):
            logger.warning("Chat not allowed for file_id=%s", file_id)
            return JSONResponse({"ok": False, "error": "chat not allowed"}, status_code=403)

        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=10)
        file_path = r.json().get("result", {}).get("file_path")
        logger.debug("Telegram file_path: %s", file_path)
        if not file_path:
            logger.error("No file_path returned by Telegram API for file_id=%s", file_id)
            return JSONResponse({"ok": False, "error": "no file path"})

        dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        r2 = requests.get(dl_url, timeout=30, stream=True)
        content = b"".join([chunk for chunk in r2.iter_content(chunk_size=8192) if chunk])
        logger.info("Downloaded torrent %s, size=%d bytes", file_name, len(content))

        success, magnet_data = await process_torrent_from_content(content, file_name)

        if success and magnet_data:
            catalog = load_local_catalog()
            catalog['movies'][file_name] = magnet_data
            saved = save_local_catalog(catalog)
            logger.info("Processed %s, catalog saved=%s", file_name, saved)

        return JSONResponse({"ok": True, "processed":[{"file": file_name, "success": success}]})
    else:
        logger.debug("No .torrent document found in message")
        return JSONResponse({"ok": True, "info": "no .torrent document"})

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/")
async def root():
    return {"message": "TG Catalog API", "status": "running"}

