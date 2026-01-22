import os, json

# Minimal load_catalog that reads the current rotated catalog file (same logic as main.py)
def get_current_catalog_file():
    LOCAL_PATH = os.path.dirname(__file__)
    n = 1
    while True:
        fname = f"catalog{'' if n == 1 else n}.json"
        fpath = os.path.join(LOCAL_PATH, fname)
        if not os.path.exists(fpath) or os.path.getsize(fpath) < (80 * 1024 * 1024):
            return fpath, fname
        n += 1

def load_catalog():
    fpath, _ = get_current_catalog_file()
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print('Failed to load catalog:', e)
    return {"results": []}

def save_catalog_merge_local(new_result):
    # Load remote-like catalog (using repo file in same folder for test)
    repo_file = os.path.join(os.path.dirname(__file__), '..', '..', 'catalog.json')
    repo_file = os.path.normpath(repo_file)
    if os.path.exists(repo_file):
        try:
            with open(repo_file, 'r', encoding='utf-8') as f:
                remote = json.load(f)
        except Exception as e:
            print('Failed to load repo catalog for test:', e)
            remote = {"results": []}
    else:
        remote = {"results": []}
    results = remote.get('results') or []
    existing = set(r.get('file') for r in results if isinstance(r, dict))
    if new_result.get('file') in existing:
        print('Already present, skipping')
        return True
    results.append(new_result)
    remote['results'] = results
    try:
        with open(repo_file, 'w', encoding='utf-8') as f:
            json.dump(remote, f, ensure_ascii=False, indent=2)
        print('Merged new_result to repo file (test)')
        return True
    except Exception as e:
        print('Failed writing repo file:', e)
        return False


catalog = load_catalog()
print('Loaded local rotated catalog, top-level keys:', list(catalog.keys())[:5])

new_result = {
    "file": "TEST_TITLE [1080p].torrent",
    "parsed": {
        "title": "TEST_TITLE",
        "type": "movie",
        "year": "2025",
        "quality": "1080p"
    },
    "matched": False,
    "tmdb_top": {},
    "torrents": [
        {"quality": "1080p", "magnet": "magnet:?xt=urn:btih:DEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEE", "infohash": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}
    ]
}

print('Merging new_result into repo file for test...')
ok = save_catalog_merge_local(new_result)
print('Result:', ok)

print('Test finished')
