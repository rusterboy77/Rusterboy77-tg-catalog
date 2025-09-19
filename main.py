# main_debug.py  (reemplaza / integra con tu main.py existente)
import os
import json
import logging
import datetime
import subprocess
import requests
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

app = FastAPI(title="TG -> Catalog API (debug)")

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

    # Debug: log what type of message we received
    logger.debug("Message keys: %s", list(msg.keys()))
    # Search magnets in text/caption
    text = msg.get("text") or msg.get("caption") or ""
    if text:
        logger.debug("Text received (first 200 chars): %s", text[:200])

    # If document .torrent present: download it
    doc = msg.get("document")
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
                    # Run rename.py and magnet.py on that newly saved file
                    # Ejecutamos rename.py primero
                    rc1, out1, err1 = run_script_collect("rename.py", [save_path])

                    # Si rename.py generó salida (nuevo path), la usamos
                    new_path = out1.strip() if out1.strip() else save_path

                    # Ejecutamos magnet.py con el archivo renombrado
                    rc2, out2, err2 = run_script_collect("magnet.py", [new_path])

                    processed.append({"file": os.path.basename(save_path), "rename_rc": rc1, "magnet_rc": rc2})
                    save_status({"event":"scripts_ran", "file": os.path.basename(save_path), "rename_rc": rc1, "magnet_rc": rc2})
                else:
                    save_status({"event":"download_failed", "status": r.status_code, "file": orig_name})
        except Exception as e:
            logger.exception("Exception downloading/saving torrent %s: %s", orig_name, e)
            save_status({"event":"exception_download", "file": orig_name, "error": str(e)})
    else:
        logger.debug("No document torrent found in message")

    # magnets in text:
    # (Not modifying your catalog here; just log found magnets)
    # Add your existing magnet-add-to-catalog logic where appropriate.
    # For now, we return what we processed.
    return JSONResponse({"ok": True, "processed": processed})

