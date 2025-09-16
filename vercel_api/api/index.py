from sanic import Sanic
from sanic.response import json
import os, re, requests, base64, json as jsonlib

app = Sanic('tg_vercel_app')

MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[A-Za-z0-9]+[^\s]*', re.IGNORECASE)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')  # format owner/repo
GITHUB_PATH = os.environ.get('GITHUB_PATH','catalog.json')

def get_github_file():
    if not GITHUB_REPO:
        return [], None
    url = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}'
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        sha = data.get('sha')
        try:
            content = base64.b64decode(data.get('content','')).decode('utf-8')
            items = jsonlib.loads(content)
        except Exception:
            items = []
        return items, sha
    return [], None

def update_github(items_to_add):
    if not GITHUB_REPO or not GITHUB_TOKEN:
        return False
    items, sha = get_github_file()
    existing = {it.get('source'): it for it in items}
    for it in items_to_add:
        existing[it.get('source')] = it
    merged = list(existing.values())
    content_b64 = base64.b64encode(jsonlib.dumps(merged, ensure_ascii=False).encode('utf-8')).decode('utf-8')
    url = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}'
    body = {'message': 'Update catalog', 'content': content_b64}
    if sha:
        body['sha'] = sha
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    r = requests.put(url, headers=headers, json=body)
    return r.status_code in (200,201)

@app.post('/webhook')
async def webhook(request):
    update = request.json or {}
    msg = update.get('message') or update.get('channel_post') or {}
    text_msg = msg.get('text','') or msg.get('caption','') or ''
    items = []
    for m in MAGNET_RE.findall(text_msg):
        title = text_msg.strip().splitlines()[0][:120] or m
        items.append({'title': title, 'source': m, 'type': 'magnet', 'date': msg.get('date')})
    # handle .torrent documents
    if msg.get('document'):
        doc = msg['document']
        fname = doc.get('file_name','')
        if fname.endswith('.torrent'):
            file_id = doc.get('file_id')
            if BOT_TOKEN:
                r = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}')
                if r.status_code == 200:
                    file_path = r.json()['result']['file_path']
                    file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
                    r2 = requests.get(file_url)
                    if r2.status_code == 200 and GITHUB_TOKEN and GITHUB_REPO:
                        path_t = f'torrents/{fname}'
                        content_b64 = base64.b64encode(r2.content).decode('utf-8')
                        url = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{path_t}'
                        body = {'message': f'Add torrent {fname}', 'content': content_b64}
                        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
                        r3 = requests.put(url, headers=headers, json=body)
                        if r3.status_code in (200,201):
                            raw_url = f'https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path_t}'
                            items.append({'title': fname, 'source': raw_url, 'type': 'torrent', 'date': msg.get('date')})
    if items:
        ok = update_github(items)
        return json({'ok': ok, 'added': len(items)})
    return json({'ok': True, 'added': 0})

@app.get('/catalog')
async def catalog(request):
    items, _ = get_github_file()
    return json(items)
