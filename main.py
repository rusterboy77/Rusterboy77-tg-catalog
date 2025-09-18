import os, re, json, base64, requests, subprocess
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# -------- Config --------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
CATALOG_PATH = "catalog.json"
TORRENTS_DIR = "torrents"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\\s]*)", re.IGNORECASE)
app = FastAPI(title="TG -> Catalog API")

# -------- Utils --------
def github_api(path):
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"

def github_raw(path):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"

def get_catalog():
    url = github_raw(CATALOG_PATH)
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

def put_file(path, content_str):
    api_url = github_api(path)
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None
    r_get = requests.get(api_url, headers=headers, timeout=15)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    body = {
        "message": f"Update {path}",
        "content": base64.b64encode(content_str.encode()).decode()
    }
    if sha:
        body["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=body, timeout=20)
    return r_put.status_code in (200,201)

def put_binary(path, binary):
    api_url = github_api(path)
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None
    r_get = requests.get(api_url, headers=headers, timeout=15)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    body = {
        "message": f"Add {path}",
        "content": base64.b64encode(binary).decode()
    }
    if sha:
        body["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=body, timeout=20)
    if r_put.status_code in (200,201):
        return github_raw(path)
    return ""

# -------- Webhook --------
@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    msg = payload.get("channel_post") or payload.get("message")
    if not msg:
        return JSONResponse({"ok": True, "info": "no message"})

    new_items = []
    text = msg.get("text") or msg.get("caption") or ""
    # magnet directos en texto
    for m in MAGNET_RE.findall(str(text)):
        new_items.append({"title": text.splitlines()[0][:120] if text else m, "source": m, "type": "magnet"})

    # documentos .torrent
    doc = msg.get("document")
    if doc and doc.get("file_name","").lower().endswith(".torrent"):
        file_id = doc["file_id"]
        if BOT_TOKEN:
            getf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=20)
            file_path = getf.json().get("result", {}).get("file_path")
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            r = requests.get(file_url, timeout=30)
            if r.status_code == 200:
                # Subir torrent a GitHub
                fname = doc["file_name"]
                remote_url = put_binary(f"{TORRENTS_DIR}/{fname}", r.content)
                if remote_url:
                    # Procesar rename.py
                    try:
                        new_name = subprocess.check_output(["python", "rename.py", fname]).decode().strip()
                        if new_name:
                            fname = new_name
                    except Exception as e:
                        print("[ERROR] rename.py:", e)

                    # Procesar magnet.py
                    magnet = ""
                    try:
                        magnet = subprocess.check_output(["python", "magnet.py", fname]).decode().strip()
                    except Exception as e:
                        print("[ERROR] magnet.py:", e)

                    if magnet:
                        new_items.append({
                            "title": fname.replace(".torrent",""),
                            "source": magnet,
                            "type": "magnet"
                        })

    # Actualizar catalog.json
    if new_items:
        catalog = get_catalog()
        catalog.extend(new_items)
        ok = put_file(CATALOG_PATH, json.dumps(catalog, ensure_ascii=False, indent=2))
        if ok:
            print(f"[INFO] {len(new_items)} añadidos al catalog.json")
        else:
            print("[ERROR] al subir catalog.json")

    return JSONResponse({"ok": True, "added": len(new_items)})

@app.get("/api/catalog")
async def catalog():
    return JSONResponse(get_catalog())
