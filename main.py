#!/usr/bin/env python3
# main.py para Render
import subprocess
from pathlib import Path
from fastapi import FastAPI, UploadFile, File

app = FastAPI()

TORRENTS_DIR = Path("torrents")
TORRENTS_DIR.mkdir(exist_ok=True)

@app.post("/api/webhook")
async def webhook(file: UploadFile = File(...)):
    # Guardar torrent en carpeta de trabajo
    torrent_path = TORRENTS_DIR / file.filename
    with open(torrent_path, "wb") as f:
        f.write(await file.read())

    # Ejecutar rename.py
    rename_proc = subprocess.run(
        ["python", "rename.py", str(torrent_path)],
        capture_output=True, text=True
    )

    # Ejecutar magnet.py
    magnet_proc = subprocess.run(
        ["python", "magnet.py", str(torrent_path)],
        capture_output=True, text=True
    )

    # Devolver salida
    return {
        "rename_stdout": rename_proc.stdout,
        "rename_stderr": rename_proc.stderr,
        "magnet_stdout": magnet_proc.stdout,
        "magnet_stderr": magnet_proc.stderr,
    }


