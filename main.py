import os
import requests
import subprocess
import logging
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "rusterboy77/Rusterboy77-tg-catalog"
TORRENTS_DIR = "torrents"

os.makedirs(TORRENTS_DIR, exist_ok=True)

def run_script_collect(script, args):
    """Ejecuta un script y devuelve (returncode, stdout, stderr)."""
    proc = subprocess.Popen(
        ["python", script] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, err = proc.communicate()
    return proc.returncode, out.strip(), err.strip()

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    logging.info("Nuevo webhook recibido")

    if "document" not in data.get("message", {}):
        logging.debug("Webhook sin documento .torrent, ignorado.")
        return {"ok": True}

    doc = data["message"]["document"]
    fname = doc["file_name"]

    if not fname.endswith(".torrent"):
        logging.debug("Archivo no es .torrent, ignorado.")
        return {"ok": True}

    file_id = doc["file_id"]
    logging.info(f"Detectado .torrent: {fname} file_id={file_id}")

    # Paso 1: obtener ruta del archivo en Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    r = requests.get(url)
    if r.status_code != 200:
        logging.error(f"getFile fallo: {r.text}")
        return {"ok": False}

    file_path = r.json()["result"]["file_path"]

    # Paso 2: descargar el torrent
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    r = requests.get(download_url)
    if r.status_code != 200:
        logging.error(f"Fallo descargando torrent: {r.text}")
        return {"ok": False}

    save_path = os.path.join(TORRENTS_DIR, fname)
    with open(save_path, "wb") as f:
        f.write(r.content)
    logging.info(f"Torrent guardado en {save_path}")

    # Paso 3: ejecutar rename.py
    rc1, out1, err1 = run_script_collect("rename.py", [save_path])
    logging.info(f"rename.py rc={rc1}")
    if rc1 == 0:
        logging.debug(f"rename.py output: {out1}")
        renamed_file = out1
    else:
        logging.error(f"rename.py error: {err1}")
        return {"ok": False}

    # Paso 4: ejecutar magnet.py con SOLO el nombre
    fname_only = os.path.basename(renamed_file)
    rc2, out2, err2 = run_script_collect("magnet.py", [fname_only])
    logging.info(f"magnet.py rc={rc2}")
    if rc2 != 0:
        logging.error(f"magnet.py error: {err2}")
        return {"ok": False}

    return {"ok": True}

