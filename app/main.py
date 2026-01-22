#!/usr/bin/env python3
# Improved main.py - series grouping + processing queue to avoid overlaps
# Reviewed and fixed potential issues found in the original:
# - Use sys.executable for running external scripts
# - Safer int conversions for season/episode
# - Cache lookup normalizes DB titles for matching
# - LAST_CHANGE_TS only updated when a local catalog was actually changed
# - Cleaner handling of temporary files and exceptions
# - Minor robustness and logging improvements
import os, re, json, time, base64, logging, datetime, sqlite3, tempfile, requests, threading, gc, subprocess, queue, hashlib, sys
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Config
GITHUB_REPO = os.environ.get("GITHUB_REPO", "rusterboy77/Rusterboy77-tg-catalog")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
LOCAL_PATH = os.path.dirname(os.path.abspath(__file__))
LOGFILE = os.path.join(LOCAL_PATH, "debug.log")
CATALOG_PATH = os.path.join(LOCAL_PATH, "catalog.json")
CACHE_DB_PATH = os.path.join(LOCAL_PATH, "cache.db")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "-4782889661")
# Safety: minimum allowed ratio of local rows vs remote rows when uploading cache.db
# If local_rows / remote_rows < CACHE_UPLOAD_MIN_RATIO, the upload will be blocked.
CACHE_UPLOAD_MIN_RATIO = float(os.environ.get("CACHE_UPLOAD_MIN_RATIO", "0.8"))

# Logging concise
logger = logging.getLogger("tgcatalog")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
ch = logging.StreamHandler(); ch.setFormatter(fmt)
logger.handlers = []; logger.addHandler(ch)
try:
    fh = logging.FileHandler(LOGFILE); fh.setFormatter(fmt); logger.addHandler(fh)
except Exception:
    logger.warning("No se pudo abrir log %s", LOGFILE)
logger.info("=== TG Catalog (improved, reviewed) iniciado ===")

# Utilities
def _norm_title(s: Optional[str]) -> str:
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^0-9A-Za-z\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()

def _http_get(url, headers=None, timeout=10, stream=False):
    try:
        return requests.get(url, headers=headers, timeout=timeout, stream=stream)
    except Exception as e:
        logger.debug("HTTP GET error %s -> %s", url, e)
        return None

# GitHub helpers (same as before)
def _github_api_get(path: str):
    if not GITHUB_TOKEN: return None, None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        r = requests.get(url, headers=headers, timeout=15); return r, headers
    except Exception as e:
        logger.warning("GitHub GET error: %s", e); return None, headers

def _github_raw_get(path: str):
    owner_repo = GITHUB_REPO
    for branch in ("main","master"):
        url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{path}"
        r = _http_get(url, timeout=15)
        if r and r.status_code==200 and r.text: return r.text
    return None

def _github_put(path: str, content_bytes: bytes, message: str, sha: Optional[str]=None) -> bool:
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN missing -> cannot PUT %s", path); return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"message": message, "content": base64.b64encode(content_bytes).decode()}
    if sha: payload["sha"] = sha
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=120)
        if r.status_code in (200,201):
            logger.info("GitHub: PUT %s OK", path); return True
        else:
            logger.warning("GitHub PUT %s failed status=%s body=%s", path, r.status_code, (r.text or "")[:300]); return False
    except Exception as e:
        logger.exception("GitHub PUT exception: %s", e); return False

def _get_remote_catalog_and_sha():
    r, headers = _github_api_get("catalog.json")
    sha = None; remote = None
    if r and r.status_code==200:
        try:
            jr = r.json(); sha = jr.get("sha")
            if jr.get("content"):
                payload = jr.get("content").strip(); raw = base64.b64decode(payload)
                remote = json.loads(raw.decode("utf-8")); return remote, sha
        except Exception:
            pass
    text = _github_raw_get("catalog.json")
    if text:
        try: remote = json.loads(text); return remote, sha
        except Exception: pass
    return None, sha

# Cache DB helpers
_cache_db_lock = threading.Lock()

def ensure_cache_db_exists_and_schema():
    if not os.path.exists(CACHE_DB_PATH):
        logger.info("cache.db no existe localmente; intentando descargar desde repo")
        txt = _github_raw_get("cache.db")
        if txt:
            owner_repo = GITHUB_REPO
            for branch in ("main","master"):
                url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/cache.db"
                r = _http_get(url, timeout=20)
                if r and r.status_code==200 and r.content:
                    try:
                        with open(CACHE_DB_PATH,"wb") as f: f.write(r.content)
                        logger.info("cache.db descargado desde GitHub"); return True
                    except Exception: break
        try:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); c = conn.cursor()
            try:
                c.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            c.executescript("""
CREATE TABLE IF NOT EXISTS items (
  "key" TEXT PRIMARY KEY,
  title TEXT,
  type TEXT,
  year TEXT,
  season TEXT,
  episode TEXT,
  tmdb_id TEXT,
  poster TEXT,
  fanart TEXT,
    clearlogo TEXT,
    banner TEXT,
    clearart TEXT,
  overview TEXT,
  episode_title TEXT,
  episode_overview TEXT,
  still_path TEXT,
  genres TEXT,
  "cast" TEXT,
  torrents TEXT,
  date_added TEXT,
  enriched INTEGER DEFAULT 0
);
""")
            conn.commit(); conn.close(); logger.info("cache.db creado localmente con esquema básico"); return True
        except Exception as e:
            logger.exception("No se pudo crear cache.db local: %s", e); return False
    else:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); c = conn.cursor()
            try:
                c.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            c.execute("PRAGMA table_info(items)"); rows = c.fetchall()
            if not rows:
                c.executescript("""
CREATE TABLE IF NOT EXISTS items (
  "key" TEXT PRIMARY KEY,
  title TEXT,
  type TEXT,
  year TEXT,
  season TEXT,
  episode TEXT,
  tmdb_id TEXT,
  poster TEXT,
  fanart TEXT,
  clearlogo TEXT,
  banner TEXT,
  clearart TEXT,
  overview TEXT,
  episode_title TEXT,
  episode_overview TEXT,
  still_path TEXT,
  genres TEXT,
  "cast" TEXT,
  torrents TEXT,
  date_added TEXT,
  enriched INTEGER DEFAULT 0
);
"""); conn.commit()
            else:
                # Ensure new optional columns exist in older DBs
                cols = [r[1] for r in rows]
                try:
                    if 'clearlogo' not in cols:
                        c.execute("ALTER TABLE items ADD COLUMN clearlogo TEXT")
                    if 'banner' not in cols:
                        c.execute("ALTER TABLE items ADD COLUMN banner TEXT")
                    if 'clearart' not in cols:
                        c.execute("ALTER TABLE items ADD COLUMN clearart TEXT")
                    conn.commit()
                except Exception:
                    # non-fatal: some SQLite versions may not allow ALTER in certain contexts
                    logger.debug('No se pudo asegurar columnas clearlogo/banner/clearart (puede que ya existan)')
            conn.close()
        except Exception:
            logger.exception("Error comprobando esquema de cache.db")
    return True

def cache_lookup_by_tmdb_or_title(tmdb_id: Optional[str], title_norm: str, year: Optional[str]=None) -> Optional[Dict[str,Any]]:
    """
    Improved lookup: load candidates and compare normalized titles so matching works
    even when the DB stored title has punctuation/case differences.
    """
    with _cache_db_lock:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); conn.row_factory = sqlite3.Row; c = conn.cursor()
            if tmdb_id:
                c.execute("SELECT * FROM items WHERE tmdb_id = ?", (str(tmdb_id),))
                r = c.fetchone()
                if r: return dict(r)
            # fetch all rows with same year (if provided) or a limited set
            if year:
                c.execute("SELECT * FROM items WHERE year = ?", (str(year),))
            else:
                c.execute("SELECT * FROM items")
            rows = c.fetchall()
            for r in rows:
                t = (r["title"] or "")
                if _norm_title(t) == title_norm:
                    return dict(r)
            return None
        except Exception:
            logger.exception("cache lookup failed"); return None

def cache_upsert_item(key: str, item: Dict[str,Any]):
    with _cache_db_lock:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); c = conn.cursor()
            genres = json.dumps(item.get("genres") or []); cast = json.dumps(item.get("cast") or []); torrents = json.dumps(item.get("torrents") or [])
            now = item.get("date_added") or datetime.datetime.utcnow().isoformat()
            # include optional clearlogo/banner/clearart columns
            c.execute("""INSERT OR REPLACE INTO items ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, overview, episode_title, episode_overview, still_path, genres, "cast", torrents, date_added, enriched)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (key, item.get("title") or "", item.get("type") or "", item.get("year") or "", item.get("season"),
                       item.get("episode"), item.get("tmdb_id") or "", item.get("poster") or "", item.get("fanart") or "",
                       item.get("clearlogo") or None, item.get("banner") or None, item.get("clearart") or None,
                       item.get("overview") or "", item.get("episode_title") or "", item.get("episode_overview") or "",
                       item.get("still_path") or "", genres, cast, torrents, now, int(bool(item.get("enriched")))))
            conn.commit(); conn.close(); return True
        except Exception:
            logger.exception("cache upsert failed for key=%s", key); return False


def upsert_cache_from_new_result(new_result: Dict[str,Any]) -> bool:
    """Incremental upsert into local cache.db from a single new_result.
    Preserves existing entries and only appends/merges torrents.
    """
    try:
        parsed = new_result.get('parsed') or {}
        if not parsed:
            return False
    # movie
        if parsed.get('type') == 'movie':
            title = parsed.get('title') or parsed.get('movie') or ''
            year = str(parsed.get('year') or '')
            key_title = re.sub(r'[^0-9a-zA-Z\- ]+', ' ', str(title or '')).strip().lower()
            key = f"movie_{key_title}_{year or ''}"
            # Merge existing torrents in DB (if any) with new_result.torrents to preserve all qualities
            existing_row = None
            try:
                existing_row = cache_lookup_by_tmdb_or_title(None, _norm_title(title), year)
            except Exception:
                existing_row = None

            # parse existing torrents
            existing_torrents = []
            if existing_row and existing_row.get('torrents'):
                try:
                    existing_torrents = json.loads(existing_row.get('torrents') or '[]')
                except Exception:
                    existing_torrents = []

            # normalize new torrents list to objects with quality+magnet
            new_torrents = []
            for t in (new_result.get('torrents') or []):
                if isinstance(t, dict):
                    # allow different keys that may appear
                    mag = t.get('magnet') or t.get('uri') or t.get('url') or ''
                    ih = (t.get('infohash') or '').strip()
                    if not mag and ih:
                        mag = f'magnet:?xt=urn:btih:{ih}'
                    q = t.get('quality') or t.get('quality_label') or ''
                    new_torrents.append({'quality': q or '', 'magnet': mag or ''})

            # If the new_result doesn't contain any magnet/infohash, skip DB upsert
            if not _list_has_magnet(new_result.get('torrents') or []):
                return False

            # merge preserving order and dedup by magnet
            seen = set(); merged = []
            def mag_key(x):
                return (x.get('magnet') or '').strip().lower()
            for t in (existing_torrents or []) + new_torrents:
                if not isinstance(t, dict):
                    continue
                k = mag_key(t)
                if not k:
                    # keep items without magnet (rare)
                    merged.append({'quality': t.get('quality') or '', 'magnet': t.get('magnet') or ''})
                    continue
                if k in seen:
                    continue
                seen.add(k)
                merged.append({'quality': t.get('quality') or '', 'magnet': t.get('magnet') or ''})

            # Preserve existing DB values if new_result doesn't provide them
            tm = (new_result.get('tmdb_top') or {})
            existing = existing_row or {}
            # poster and fanart
            poster = tm.get('poster_url') if tm.get('poster_url') else (existing.get('poster') if existing else '')
            fanart = tm.get('backdrop_url') if tm.get('backdrop_url') else (existing.get('fanart') if existing else '')
            # clearlogo/banner/clearart
            clearlogo = tm.get('clearlogo') if tm.get('clearlogo') else (existing.get('clearlogo') if existing else '')
            banner = tm.get('banner') if tm.get('banner') else (existing.get('banner') if existing else '')
            clearart = tm.get('clearart') if tm.get('clearart') else (existing.get('clearart') if existing else '')
            # overview/genres/cast
            overview = tm.get('overview') if tm.get('overview') else (new_result.get('overview') or (existing.get('overview') if existing else ''))
            try:
                genres = tm.get('genres') if tm.get('genres') is not None else (json.loads(existing.get('genres')) if existing and existing.get('genres') else [])
            except Exception:
                genres = tm.get('genres') or []
            try:
                cast = tm.get('cast') if tm.get('cast') is not None else (json.loads(existing.get('cast')) if existing and existing.get('cast') else [])
            except Exception:
                cast = tm.get('cast') or []

            # Log existing_row and what we will write
            try:
                logger.debug("upsert movie key=%s existing_row summary=%s", key, json.dumps({ 'tmdb_id': existing_row.get('tmdb_id') if existing_row else None, 'poster': (existing_row.get('poster') if existing_row else None), 'fanart': (existing_row.get('fanart') if existing_row else None), 'clearlogo': (existing_row.get('clearlogo') if existing_row else None) }, ensure_ascii=False)[:1000])
            except Exception:
                pass

            item = {
                'title': title,
                'type': 'movie',
                'year': year,
                'tmdb_id': tm.get('id') or parsed.get('tmdb_id') or '',
                'poster': poster or '',
                'fanart': fanart or '',
                'clearlogo': clearlogo or '',
                'banner': banner or '',
                'clearart': clearart or '',
                'overview': overview or '',
                'genres': genres or [],
                'cast': cast or [],
                'torrents': merged,
                'date_added': datetime.datetime.utcnow().isoformat(),
                'enriched': bool(tm.get('id') or poster or overview)
            }
            try:
                logger.info("UPSERT MOVIE key=%s poster=%s fanart=%s clearlogo=%s banner=%s clearart=%s", key, item.get('poster'), item.get('fanart'), item.get('clearlogo'), item.get('banner'), item.get('clearart'))
            except Exception:
                pass
            return cache_upsert_item(key, item)

        # series
        if parsed.get('type') == 'series':
            series = parsed.get('series') or parsed.get('title') or ''
            season = parsed.get('season')
            episode = parsed.get('episode')
            key_title = re.sub(r'[^0-9a-zA-Z\- ]+', ' ', str(series or '')).strip().lower()
            series_key = f"tv_{key_title}"
            ep_key = f"tv_{key_title}_{season or ''}_{episode or ''}"

            # Merge into series row
            # Prefer the series-level row (season/episode NULL) when looking up existing
            existing = None
            try:
                with _cache_db_lock:
                    conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); conn.row_factory = sqlite3.Row; c = conn.cursor()
                    # try tmdb_id match for series row first
                    tmid = (new_result.get('tmdb_top') or {}).get('id') or ''
                    if tmid:
                        c.execute("SELECT * FROM items WHERE tmdb_id = ? AND (season IS NULL OR season = '') AND (episode IS NULL OR episode = '')", (str(tmid),))
                        r = c.fetchone()
                        if r:
                            existing = dict(r)
                    # fallback: try to find a series row by normalized title
                    if not existing:
                        c.execute("SELECT * FROM items WHERE (season IS NULL OR season = '') AND (episode IS NULL OR episode = '')")
                        rows = c.fetchall()
                        for r in rows:
                            try:
                                if _norm_title(r['title'] or '') == _norm_title(series):
                                    existing = dict(r); break
                            except Exception:
                                continue
                    conn.close()
            except Exception:
                existing = None
            existing_eps = []
            if existing and existing.get('torrents'):
                try:
                    existing_eps = json.loads(existing.get('torrents') or '[]')
                except Exception:
                    existing_eps = []
            # new episode objects from new_result
            new_eps = []
            for e in (new_result.get('torrents') or []):
                if isinstance(e, dict) and 'season' in e and 'episode' in e:
                    new_eps.append(e)

            # If the incoming new_result contains no magnet/infohash, skip DB upsert
            # Build a flat list of torrent dicts to inspect
            flat = []
            for e in (new_result.get('torrents') or []):
                if isinstance(e, dict) and 'torrents' in e:
                    flat.extend(e.get('torrents') or [])
                else:
                    flat.append(e)
            if not _list_has_magnet(flat):
                return False

            # merge episodes by (season,episode)
            combined_index = {(e.get('season'), e.get('episode')): e for e in existing_eps}
            for e in new_eps:
                keyse = (e.get('season'), e.get('episode'))
                if keyse in combined_index:
                    # merge torrent lists
                    oldt = combined_index[keyse].get('torrents') or []
                    newt = e.get('torrents') or []
                    seen = set((t.get('infohash') or '').lower() for t in oldt if t.get('infohash'))
                    merged = list(oldt)
                    for t in newt:
                        ih = (t.get('infohash') or '').lower()
                        if ih and ih in seen: continue
                        if ih: seen.add(ih)
                        merged.append(t)
                    combined_index[keyse]['torrents'] = merged
                else:
                    combined_index[keyse] = e

            merged_list = list(combined_index.values())
            tmdb_top = new_result.get('tmdb_top') or {}
            series_item = {
                'title': series,
                'type': 'tv',
                'year': '',
                'tmdb_id': tmdb_top.get('id') or (existing.get('tmdb_id') if existing else ''),
                'poster': tmdb_top.get('poster_url') or (existing.get('poster') if existing else ''),
                'fanart': tmdb_top.get('backdrop_url') or (existing.get('fanart') if existing else ''),
                'clearlogo': tmdb_top.get('clearlogo') if tmdb_top.get('clearlogo') is not None else (existing.get('clearlogo') if existing else ''),
                'banner': tmdb_top.get('banner') if tmdb_top.get('banner') is not None else (existing.get('banner') if existing else ''),
                'clearart': tmdb_top.get('clearart') if tmdb_top.get('clearart') is not None else (existing.get('clearart') if existing else ''),
                'overview': tmdb_top.get('overview') or new_result.get('overview') or (existing.get('overview') if existing else ''),
                'genres': tmdb_top.get('genres') or [],
                'cast': tmdb_top.get('cast') or [],
                'torrents': merged_list,
                'date_added': (existing.get('date_added') if existing else None) or datetime.datetime.utcnow().isoformat(),
                'enriched': bool(tmdb_top.get('id') or series_item if False else False)
            }
            # write series row
            cache_upsert_item(series_key, series_item)

            # Upsert per-episode row as well
            if season is not None and episode is not None:
                # find merged torrents for this ep
                ep_torrents = []
                for e in merged_list:
                    if e.get('season') == season and e.get('episode') == episode:
                        ep_torrents = e.get('torrents') or []
                        break
                ep_item = {
                    'title': series,
                    'type': 'tv',
                    'year': '',
                    'season': season,
                    'episode': episode,
                    'tmdb_id': tmdb_top.get('id') or (existing.get('tmdb_id') if existing else ''),
                    'poster': tmdb_top.get('poster_url') or (existing.get('poster') if existing else ''),
                    'fanart': tmdb_top.get('backdrop_url') or (existing.get('fanart') if existing else ''),
                    'clearlogo': tmdb_top.get('clearlogo') if tmdb_top.get('clearlogo') is not None else (existing.get('clearlogo') if existing else ''),
                    'banner': tmdb_top.get('banner') if tmdb_top.get('banner') is not None else (existing.get('banner') if existing else ''),
                    'clearart': tmdb_top.get('clearart') if tmdb_top.get('clearart') is not None else (existing.get('clearart') if existing else ''),
                    'overview': tmdb_top.get('overview') or new_result.get('overview') or (existing.get('overview') if existing else ''),
                    # episode-specific fields (may be present in tmdb_top/result)
                    'episode_title': tmdb_top.get('episode_title') or (new_result.get('episode_title') or '') or (existing.get('episode_title') if existing else ''),
                    'episode_overview': tmdb_top.get('episode_overview') or (new_result.get('episode_overview') or '') or (existing.get('episode_overview') if existing else ''),
                    'still_path': tmdb_top.get('still_path') or (new_result.get('still_path') or '') or (existing.get('still_path') if existing else ''),
                    'genres': tmdb_top.get('genres') or [],
                    'cast': tmdb_top.get('cast') or [],
                    'torrents': ep_torrents,
                    'date_added': datetime.datetime.utcnow().isoformat(),
                    'enriched': bool(tmdb_top.get('id'))
                }
                cache_upsert_item(ep_key, ep_item)

            return True
    except Exception:
        logger.exception('upsert_cache_from_new_result failed')
        return False

# TMDB helpers (same as prior implementation)
def _tmdb_search(kind: str, query: str):
    if not TMDB_API_KEY: return []
    q = requests.utils.requote_uri(query)
    url = f"https://api.themoviedb.org/3/search/{kind}?api_key={TMDB_API_KEY}&language=es-ES&query={q}"
    r = _http_get(url, timeout=10);
    if not r or not r.ok: return []
    try: return r.json().get("results") or []
    except Exception: return []

def enrich_with_tmdb_if_needed(parsed: Dict[str,Any], existing_cached: Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    result = {}
    # Prefer series name when parsed type is series, otherwise prefer title/movie
    if (parsed.get("type") or "") == "series":
        parsed_title = parsed.get("series") or parsed.get("title") or parsed.get("movie") or ""
    else:
        parsed_title = parsed.get("title") or parsed.get("series") or parsed.get("movie") or ""
    title_norm = _norm_title(parsed_title); year = str(parsed.get("year") or "")
    if existing_cached and existing_cached.get("tmdb_id"):
        result["tmdb_top"] = {"id": existing_cached.get("tmdb_id")}
        result["poster_url"] = existing_cached.get("poster"); result["backdrop_url"] = existing_cached.get("fanart")
        result["overview"] = existing_cached.get("overview"); result["genres"] = json.loads(existing_cached.get("genres") or "[]")
        try: result["cast"] = json.loads(existing_cached.get("cast") or "[]")
        except Exception: result["cast"] = []
        return result
    if not TMDB_API_KEY: return result
    # Search tv first for series, movie first for movies
    kinds = ("tv","movie") if (parsed.get("type") or "") == "series" else ("movie","tv")
    for kind in kinds:
        candidates = _tmdb_search(kind, parsed_title)
        if not candidates: continue
        top = None
        if year:
            for c in candidates:
                rd = c.get("release_date") or c.get("first_air_date") or ""
                if rd and rd.startswith(year): top = c; break
        if not top: top = candidates[0]
        if top:
            tmdb_top = {"id": top.get("id"), "title": top.get("title") or top.get("name"), "original_title": top.get("original_title") or top.get("original_name"), "overview": top.get("overview"), "poster_path": top.get("poster_path"), "backdrop_path": top.get("backdrop_path")}
            try:
                tid = tmdb_top["id"]; kind_ep = "movie" if kind=="movie" else "tv"
                url_item = f"https://api.themoviedb.org/3/{kind_ep}/{tid}?api_key={TMDB_API_KEY}&language=es-ES"
                ri = requests.get(url_item, timeout=8)
                if ri.ok:
                    item_full = ri.json(); genres = [g.get("name") for g in (item_full.get("genres") or [])]
                    rc = requests.get(f"https://api.themoviedb.org/3/{kind_ep}/{tid}/credits?api_key={TMDB_API_KEY}", timeout=8)
                    if rc.ok:
                        try: cast = [c.get("name") for c in rc.json().get("cast", [])[:10] if c.get("name")]
                        except Exception: cast = []
                    else: cast = []
                    # Prefer poster/backdrop from the detailed item_full response when present
                    poster_path_used = None
                    backdrop_path_used = None
                    try:
                        if isinstance(item_full, dict):
                            poster_path_used = item_full.get('poster_path') or None
                            backdrop_path_used = item_full.get('backdrop_path') or None
                    except Exception:
                        poster_path_used = None; backdrop_path_used = None
                    if not poster_path_used:
                        poster_path_used = tmdb_top.get('poster_path') or None
                    if not backdrop_path_used:
                        backdrop_path_used = tmdb_top.get('backdrop_path') or None
                    poster_url = "https://image.tmdb.org/t/p/w500" + (poster_path_used or "")
                    backdrop_url = "https://image.tmdb.org/t/p/original" + (backdrop_path_used or "")
                    # try to fetch images (logos/backdrops/posters) to pick clearlogo/banner/clearart
                    try:
                        imgs = requests.get(f"https://api.themoviedb.org/3/{kind_ep}/{tid}/images?api_key={TMDB_API_KEY}&include_image_language=es,null", timeout=8)
                        if imgs.ok:
                            imgs_json = imgs.json()
                            clearlogo = ''
                            banner = ''
                            # logos
                            for l in (imgs_json.get('logos') or []):
                                if l.get('file_path'):
                                    clearlogo = "https://image.tmdb.org/t/p/original" + l.get('file_path')
                                    break
                            bds = imgs_json.get('backdrops') or []
                            if bds and bds[0].get('file_path'):
                                banner = "https://image.tmdb.org/t/p/original" + bds[0].get('file_path')
                            # clearart: prefer poster
                            clearart = poster_url or ''
                        else:
                            clearlogo = ''; banner = ''; clearart = poster_url or ''
                    except Exception:
                        clearlogo = ''; banner = ''; clearart = poster_url or ''
                else:
                    genres = []; cast = []; poster_url = ""; backdrop_url = ""; clearlogo = ''; banner = ''; clearart = ''
            except Exception:
                genres = []; cast = []; poster_url = ""; backdrop_url = ""; clearlogo = ''; banner = ''; clearart = ''
            # If this is a TV show and parsed contains season/episode, try to fetch episode-specific data
            try:
                parsed_season = parsed.get('season') if isinstance(parsed, dict) else None
                parsed_episode = parsed.get('episode') if isinstance(parsed, dict) else None
                if kind == 'tv' and parsed_season is not None and parsed_episode is not None:
                    try:
                        sid = parsed_season; eid = parsed_episode
                        r_ep = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{sid}/episode/{eid}?api_key={TMDB_API_KEY}&language=es-ES", timeout=8)
                        if r_ep and r_ep.ok:
                            ep_data = r_ep.json()
                            # write episode-specific fields into result
                            result["episode_title"] = ep_data.get("name", "") or ""
                            result["episode_overview"] = ep_data.get("overview", "") or ""
                            if ep_data.get("still_path"):
                                result["still_path"] = "https://image.tmdb.org/t/p/original" + ep_data.get("still_path")
                    except Exception as e:
                        logger.debug(f"TMDB episode fetch failed: {e}")
            except Exception:
                pass
            # include image fields and lists inside tmdb_top so upsert uses them
            tmdb_top['poster_url'] = poster_url
            tmdb_top['backdrop_url'] = backdrop_url
            tmdb_top['genres'] = genres
            tmdb_top['cast'] = cast
            tmdb_top['clearlogo'] = clearlogo if 'clearlogo' in locals() else ''
            tmdb_top['banner'] = banner if 'banner' in locals() else ''
            tmdb_top['clearart'] = clearart if 'clearart' in locals() else poster_url or ''
            # episode-specific into tmdb_top as well
            if result.get('episode_title'):
                tmdb_top['episode_title'] = result.get('episode_title')
            if result.get('episode_overview'):
                tmdb_top['episode_overview'] = result.get('episode_overview')
            if result.get('still_path'):
                tmdb_top['still_path'] = result.get('still_path')
            result["tmdb_top"] = tmdb_top; result["poster_url"] = poster_url; result["backdrop_url"] = backdrop_url; result["overview"] = tmdb_top.get("overview") or ""; result["genres"] = genres; result["cast"] = cast
            return result
    return result

# Catalog helpers with series grouping
_catalog_lock = threading.Lock()
_processed_files = set()
MAX_PROCESSED_FILES = 800
# Upload coordination
PENDING_COUNT = 0
PENDING_LOCK = threading.Lock()
LAST_CHANGE_TS = None
IDLE_SECONDS_BEFORE_UPLOAD = 8
UPLOADER_RUNNING = False
_uploader_thread = None
LAST_UPLOADED_CATALOG_DIGEST = None

def load_local_catalog() -> Dict[str,Any]:
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f: return json.load(f)
        except Exception:
            logger.warning("No se pudo leer catalog.json local, inicializando vacío")
    return {"results": []}

def save_local_catalog(data: Dict[str,Any]) -> bool:
    """Write catalog.json only if content changed. Returns True if file was written/changed."""
    try:
        new_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        if os.path.exists(CATALOG_PATH):
            try:
                with open(CATALOG_PATH, 'rb') as f:
                    old = f.read()
                if old == new_bytes:
                    logger.debug("save_local_catalog: no hay cambios en catalog.json, skip write")
                    return False
            except Exception:
                logger.exception("Error leyendo catalog existente")
        os.makedirs(os.path.dirname(CATALOG_PATH) or ".", exist_ok=True)
        with open(CATALOG_PATH, "wb") as f: f.write(new_bytes)
        logger.info("Catalog saved locally %s", CATALOG_PATH)
        return True
    except Exception:
        logger.exception("Error guardando catalog local")
        return False

def dedupe_torrents_list(torrents: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    seen = set(); out = []
    for t in torrents:
        ih = (t.get("infohash") or "").lower(); key = ih or json.dumps(t, sort_keys=True)
        if key in seen: continue
        seen.add(key); out.append(t)
    return out


def _torrent_has_magnet(t: Dict[str, Any]) -> bool:
    """Return True if torrent dict contains a usable magnet link or infohash."""
    if not isinstance(t, dict):
        return False
    mag = (t.get('magnet') or t.get('uri') or t.get('url') or '')
    ih = (t.get('infohash') or t.get('hash') or '')
    if isinstance(mag, str) and mag.strip():
        return True
    if isinstance(ih, str) and ih.strip():
        return True
    # nested structures: some entries wrap torrents inside 'torrents' key
    nested = t.get('torrents')
    if isinstance(nested, list):
        for x in nested:
            if _torrent_has_magnet(x):
                return True
    return False


def _list_has_magnet(lst: List[Dict[str, Any]]) -> bool:
    """Return True if any torrent item in list contains magnet/infohash."""
    for t in (lst or []):
        if _torrent_has_magnet(t):
            return True
    return False

def merge_new_result_into_remote(remote: Dict[str,Any], new_result: Dict[str,Any]) -> Dict[str,Any]:
    results = remote.get("results") or []
    nr_parsed = new_result.get("parsed") or {}
    nr_type = nr_parsed.get("type")
    nr_title_norm = _norm_title(nr_parsed.get("title") or nr_parsed.get("movie") or nr_parsed.get("series") or "")
    nr_year = str(nr_parsed.get("year") or "")
    nr_tmdb = (new_result.get("tmdb_top") or {}).get("id") or nr_parsed.get("tmdb_id")
    new_torrents = new_result.get("torrents") or []

    # movie flow
    if nr_type == "movie":
        for r in results:
            r_hashes = set((t.get("infohash") or "").lower() for t in (r.get("torrents") or []) if t.get("infohash"))
            new_hashes = set((t.get("infohash") or "").lower() for t in new_torrents if t.get("infohash"))
            if new_hashes and (r_hashes & new_hashes):
                r["torrents"] = dedupe_torrents_list((r.get("torrents") or []) + new_torrents)
                if (not r.get("tmdb_top")) and new_result.get("tmdb_top"): r["tmdb_top"] = new_result.get("tmdb_top")
                return remote
        if nr_tmdb:
            for r in results:
                r_tmdb = (r.get("tmdb_top") or {}).get("id") or (r.get("parsed") or {}).get("tmdb_id")
                if r_tmdb and str(r_tmdb)==str(nr_tmdb):
                    r["torrents"] = dedupe_torrents_list((r.get("torrents") or []) + new_torrents); return remote
        for r in results:
            r_parsed = r.get("parsed") or {}
            if _norm_title(r_parsed.get("title") or r_parsed.get("movie") or "") == nr_title_norm and (not nr_year or str(r_parsed.get("year") or "")==nr_year):
                r["torrents"] = dedupe_torrents_list((r.get("torrents") or []) + new_torrents)
                if (not r.get("tmdb_top")) and new_result.get("tmdb_top"): r["tmdb_top"] = new_result.get("tmdb_top")
                return remote
        # Only append new results that contain at least one magnet/infohash
        if _list_has_magnet(new_torrents):
            results.append(new_result); remote["results"] = results
        return remote

    # === SERIES FLOW ===
    if nr_type == "series":
        series_name = nr_parsed.get("series") or nr_parsed.get("title") or ""
        series_norm = _norm_title(series_name)
        season = nr_parsed.get("season")
        episode = nr_parsed.get("episode")

        # Buscar si ya existe esta serie en el catálogo remoto
        series_entry = None
        for r in results:
            rp = r.get("parsed") or {}
            if rp.get("type") == "series" and _norm_title(rp.get("series") or rp.get("title") or "") == series_norm:
                series_entry = r
                break

        # If no exists, crear una nueva entrada para la serie
        if series_entry is None:
            # Only create a new series entry when we have at least one real torrent (magnet/infohash)
            # Build episode torrent list to inspect
            ep_torrents = []
            for item in new_torrents:
                if isinstance(item, dict) and "torrents" in item:
                    ep_torrents.extend(item.get("torrents") or [])
                else:
                    ep_torrents.append(item)
            if not _list_has_magnet(ep_torrents):
                # nothing to save for this series/episode
                return remote
            series_entry = {
                "file": series_name,
                "parsed": {
                    "type": "series",
                    "series": series_name
                },
                "matched": False,
                "tmdb_top": new_result.get("tmdb_top") or {},
                "episodes": []
            }
            results.append(series_entry)
        else:
            if "episodes" not in series_entry:
                series_entry["episodes"] = []

        if (not series_entry.get("tmdb_top")) and new_result.get("tmdb_top"):
            series_entry["tmdb_top"] = new_result.get("tmdb_top")

        # Buscar episodio concreto
        ep_found = None
        for ep in series_entry["episodes"]:
            if ep.get("season") == season and ep.get("episode") == episode:
                ep_found = ep
                break

        if ep_found is None:
            ep_found = {
                "season": season,
                "episode": episode,
                "overview": new_result.get("overview"),
                "torrents": []
            }
            series_entry["episodes"].append(ep_found)

        # Fusionar torrents del episodio
        ep_torrents = []
        for item in new_torrents:
            if isinstance(item, dict) and "torrents" in item:
                ep_torrents.extend(item.get("torrents") or [])
            else:
                ep_torrents.append(item)

        # Only merge torrents if there is at least one magnet/infohash
        if _list_has_magnet(ep_torrents):
            ep_found["torrents"] = dedupe_torrents_list((ep_found.get("torrents") or []) + ep_torrents)

        return remote

    # fallback append
    results.append(new_result); remote["results"] = results; return remote




def _upload_local_cache_db():
    """Upload the existing local CACHE_DB_PATH to GitHub without regenerating it from catalog.json."""
    if not os.path.exists(CACHE_DB_PATH):
        logger.warning("No local cache.db to upload")
        return False
    # Sanity check: compare local row count with remote row count (if remote exists)
    try:
        local_count = None
        content = None
        with _cache_db_lock:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=30); cur = conn.cursor()
            try:
                cur.execute('SELECT COUNT(*) FROM items')
                local_count = int(cur.fetchone()[0])
            except Exception:
                local_count = None
            conn.close()
            try:
                with open(CACHE_DB_PATH, 'rb') as f:
                    content = f.read()
            except Exception:
                content = None
    except Exception:
        logger.exception("Error leyendo cache.db local para sanity check/upload")
        return False
    
    if content is None:
        return False

    rr, _ = _github_api_get('cache.db')
    cur_sha = None
    remote_count = None
    if rr and rr.status_code == 200:
        try:
            cur_sha = rr.json().get('sha')
            # download remote file bytes to check row count
            owner_repo = GITHUB_REPO
            remote_raw = _http_get(f"https://raw.githubusercontent.com/{owner_repo}/main/cache.db", timeout=20)
            if remote_raw and remote_raw.status_code == 200 and remote_raw.content:
                try:
                    # write to temp and count rows
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                    tf.write(remote_raw.content); tf.close(); tmp_remote = tf.name
                    try:
                        rc = sqlite3.connect(tmp_remote); cur = rc.cursor(); cur.execute('SELECT COUNT(*) FROM items'); remote_count = int(cur.fetchone()[0]); rc.close()
                    except Exception:
                        remote_count = None
                    try: os.unlink(tmp_remote)
                    except Exception: pass
                except Exception:
                    remote_count = None
        except Exception:
            cur_sha = None
    # If we have counts for both, enforce minimal ratio to prevent accidental deletion
    try:
        if remote_count is not None and local_count is not None and remote_count > 0:
            ratio = float(local_count) / float(remote_count)
            if ratio < float(CACHE_UPLOAD_MIN_RATIO):
                logger.warning("Abort upload: local cache.db row count (%s) is < %.2f of remote (%s). Ratio=%.3f", local_count, CACHE_UPLOAD_MIN_RATIO, remote_count, ratio)
                return False
    except Exception:
        logger.exception('Error evaluating sanity ratio; proceeding with upload')

    ok = _github_put('cache.db', content, f"Update cache.db - {datetime.datetime.utcnow().isoformat()}", sha=cur_sha)
    return ok

# External scripts runner - use sys.executable for reliability
def run_script_collect(script_name: str, args: List[str], timeout: int = 30):
    cmd = [sys.executable, script_name] + args; logger.debug("Ejecutando script: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PYTHONUNBUFFERED":"1"})
        logger.info("Script %s rc=%s out_len=%d err_len=%d", script_name, proc.returncode, len(proc.stdout or ""), len(proc.stderr or ""))
        if proc.stderr: logger.warning("stderr %s", (proc.stderr[:1000] + ("...[truncated]" if len(proc.stderr)>1000 else "")))
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout ejecutando %s", script_name); return -2, "", "timeout"
    except Exception as e:
        logger.exception("Error ejecutando %s: %s", script_name, e); return -1, "", str(e)

# Processing queue to avoid overlaps
PROCESS_QUEUE = queue.Queue()
WORKER_RUNNING = False

def worker_loop():
    global WORKER_RUNNING
    WORKER_RUNNING = True
    logger.info("Worker thread iniciado (procesando cola)...")
    while True:
        payload = PROCESS_QUEUE.get()
        if payload is None:
            logger.info("Worker recibido sentinel, saliendo"); break
        try:
            process_sync_payload(payload)
        except Exception:
            logger.exception("Error en worker procesando payload")
        finally:
            PROCESS_QUEUE.task_done()
    WORKER_RUNNING = False


def uploader_loop():
    global UPLOADER_RUNNING, LAST_CHANGE_TS
    UPLOADER_RUNNING = True
    logger.info("Uploader thread iniciado (subidas en lote)...")
    while True:
        try:
            time.sleep(1)
            with PENDING_LOCK:
                pending = PENDING_COUNT
                last = LAST_CHANGE_TS
            logger.debug("uploader_loop state: pending=%s last=%s now=%s", pending, last, time.time())
            if pending == 0 and last and (time.time() - last) >= IDLE_SECONDS_BEFORE_UPLOAD:
                try:
                    with open(CATALOG_PATH, 'rb') as f: catalog_bytes = f.read()
                except Exception:
                    logger.warning("No hay catalog.json local para subir"); catalog_bytes = None

                if catalog_bytes:
                    try:
                        digest = hashlib.sha256(catalog_bytes).hexdigest()
                    except Exception:
                        digest = None

                    rr, _ = _github_api_get("catalog.json"); cur_sha = None; remote_same = False
                    if rr and rr.status_code == 200:
                        try:
                            jr = rr.json(); cur_sha = jr.get('sha')
                            raw = _github_raw_get("catalog.json")
                            if raw is not None and digest is not None:
                                try:
                                    remote_digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                                    if remote_digest == digest:
                                        remote_same = True
                                except Exception:
                                    pass
                        except Exception:
                            cur_sha = None

                    if digest is not None and digest == globals().get('LAST_UPLOADED_CATALOG_DIGEST'):
                        logger.info("Uploader: local catalog unchanged from last upload (digest match), skipping upload")
                        with PENDING_LOCK:
                            LAST_CHANGE_TS = None
                        continue

                    if remote_same:
                        logger.info("Uploader: remote catalog identical to local, will skip catalog PUT and upload local cache.db (no regeneration)")
                        globals()['LAST_UPLOADED_CATALOG_DIGEST'] = digest
                        try:
                            ok_db = _upload_local_cache_db()
                            if ok_db:
                                logger.info("cache.db subido correctamente por uploader (local file)")
                            else:
                                logger.warning("Uploader: fallo subiendo local cache.db")
                        except Exception:
                            logger.exception("Uploader: error subiendo local cache.db")
                        with PENDING_LOCK:
                            LAST_CHANGE_TS = None
                        continue

                    ok = _github_put("catalog.json", catalog_bytes, f"Batch update catalog.json - {datetime.datetime.utcnow().isoformat()}", sha=cur_sha)
                    if ok:
                        logger.info("catalog.json subido correctamente por uploader")
                        globals()['LAST_UPLOADED_CATALOG_DIGEST'] = digest
                        # After successfully uploading catalog.json, upload the local cache.db file (do not regenerate)
                        try:
                            ok_db = _upload_local_cache_db()
                            if ok_db:
                                logger.info("cache.db subido correctamente por uploader (local file)")
                            else:
                                logger.warning("Uploader: fallo subiendo local cache.db")
                        except Exception:
                            logger.exception("Uploader: error subiendo local cache.db")
                    else:
                        logger.warning("Uploader: fallo subiendo catalog.json, reintentará más tarde")
                with PENDING_LOCK:
                    LAST_CHANGE_TS = None
        except Exception:
            logger.exception("Exception en uploader_loop")


# Payload processor (adapted for series grouping)
def _safe_int(val):
    try:
        if val is None: return None
        return int(val)
    except Exception:
        return None

def process_sync_payload(payload: Dict[str,Any]):
    try:
        if len(_processed_files) > MAX_PROCESSED_FILES:
            _processed_files.clear(); gc.collect(); logger.info("Processed files cache cleared")
        global PENDING_COUNT, LAST_CHANGE_TS
        msg = payload.get("channel_post") or payload.get("message")
        if not msg: return
        docs = []
        if "document" in msg: docs.append(msg["document"])
        elif "documents" in msg: docs.extend(msg["documents"])
        if not docs: return
        for doc in docs:
            file_id = doc.get("file_id"); file_name = doc.get("file_name","unknown.torrent")
            logger.info("Documento recibido file_id=%s file_name=%s", file_id, file_name)
            if file_id in _processed_files:
                logger.info("Archivo ya procesado (file_id): %s", file_id); continue
            _processed_files.add(file_id)
            # marcar pendiente
            with PENDING_LOCK:
                PENDING_COUNT += 1
                logger.info("PENDING_COUNT incrementado -> %d", PENDING_COUNT)
            changed_local_catalog = False
            temp_path = None
            try:
                chat = (msg.get("chat") or {}); chat_id = str(chat.get("id") or "")
                if ALLOWED_CHAT_IDS and chat_id not in [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]:
                    logger.warning("Chat no permitido: %s", chat_id); continue
                if not BOT_TOKEN:
                    logger.error("BOT_TOKEN no configurado; imposible descargar archivo"); continue
                r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}", timeout=10)
                try:
                    jr = r.json(); file_path = jr.get("result",{}).get("file_path")
                    if not file_path: logger.error("No file_path"); continue
                except Exception:
                    logger.exception("Error parsing getFile response"); continue
                dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                r2 = requests.get(dl_url, timeout=60, stream=True)
                if not r2 or not r2.ok: logger.error("No se pudo descargar archivo desde Telegram"); continue
                content = b""
                for chunk in r2.iter_content(chunk_size=8192):
                    if chunk: content += chunk
                with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as tf:
                    tf.write(content); temp_path = tf.name
                rc_rename, out_rename, _ = run_script_collect("rename.py", [file_name], timeout=20)
                metadata = {}
                if rc_rename == 0:
                    try: metadata = json.loads(out_rename)
                    except Exception: logger.warning("No pude parsear salida rename.py")
                rc_magnet, out_magnet, _ = run_script_collect("magnet.py", [temp_path], timeout=20)
                if rc_magnet != 0:
                    logger.error("magnet.py falló rc=%s", rc_magnet)
                    continue
                try: magnet_data = json.loads(out_magnet)
                except Exception:
                    logger.exception("No se pudo parsear salida magnet.py"); continue
                new_result = {"file": file_name, "parsed": {}, "matched": False, "tmdb_top": {}, "torrents": []}
                if metadata.get("type") == "movie":
                    title = metadata.get("movie") or metadata.get("title") or file_name
                    quality = metadata.get("quality") or "desconocida"
                    new_result["parsed"] = {"title": title, "type": "movie", "year": metadata.get("year", ""), "quality": quality}
                    new_result["torrents"].append({"quality": quality, "magnet": magnet_data.get("magnet", "")})
                elif metadata.get("type") == "series":
                    series = metadata.get("series", "unknown")
                    quality = metadata.get("quality") or "desconocida"
                    season = _safe_int(metadata.get("season"))
                    episode = _safe_int(metadata.get("episode"))
                    ep_obj = {"season": season, "episode": episode, "torrents": [{"quality": quality, "magnet": magnet_data.get("magnet", "")}]}
                    new_result["parsed"] = {"title": file_name, "type": "series", "series": series, "season": season, "episode": episode, "quality": quality}
                    new_result["torrents"] = [ep_obj]
                else:
                    new_result["parsed"] = {"title": file_name, "type": "movie", "year": "", "quality": metadata.get("quality", "desconocida")}
                    new_result["torrents"].append({"quality": metadata.get("quality", "desconocida"), "magnet": magnet_data.get("magnet", "")})

                parsed = new_result.get("parsed") or {}
                parsed_title = parsed.get("title") or parsed.get("series") or parsed.get("movie") or ""
                title_norm = _norm_title(parsed_title); year = str(parsed.get("year") or "")

                existing_cached = None
                try: existing_cached = cache_lookup_by_tmdb_or_title(None, title_norm, year)
                except Exception: existing_cached = None

                enriched_info = enrich_with_tmdb_if_needed(parsed, existing_cached)

                if enriched_info:
                    # copy whole tmdb info into new_result so upsert can store genres/cast and art
                    tm = new_result.setdefault("tmdb_top", {})
                    if enriched_info.get("tmdb_top"):
                        # merge keys from enriched_info.tmdb_top but skip empty values
                        for k, v in (enriched_info.get("tmdb_top") or {}).items():
                            try:
                                if v is None or (isinstance(v, str) and not v.strip()):
                                    continue
                                tm[k] = v
                            except Exception:
                                if v:
                                    tm[k] = v
                    if enriched_info.get("overview"):
                        new_result["overview"] = enriched_info.get("overview")
                    if enriched_info.get("poster_url"):
                        tm["poster_url"] = enriched_info.get("poster_url")
                    if enriched_info.get("backdrop_url"):
                        tm["backdrop_url"] = enriched_info.get("backdrop_url")
                    if enriched_info.get("genres"):
                        tm["genres"] = enriched_info.get("genres")
                    if enriched_info.get("cast"):
                        tm["cast"] = enriched_info.get("cast")
                    # ensure clearlogo/banner/clearart exist
                    if enriched_info.get("clearlogo"):
                        tm["clearlogo"] = enriched_info.get("clearlogo")
                    if enriched_info.get("banner"):
                        tm["banner"] = enriched_info.get("banner")
                    if enriched_info.get("clearart"):
                        tm["clearart"] = enriched_info.get("clearart")
                    # episode-specific
                    if enriched_info.get("episode_title"):
                        tm["episode_title"] = enriched_info.get("episode_title")
                    if enriched_info.get("episode_overview"):
                        tm["episode_overview"] = enriched_info.get("episode_overview")
                    if enriched_info.get("still_path"):
                        tm["still_path"] = enriched_info.get("still_path")

                with _catalog_lock:
                    catalog = load_local_catalog()
                    remote_catalog, remote_sha = _get_remote_catalog_and_sha()
                    if remote_catalog is None:
                        remote_catalog = catalog
                    merged = merge_new_result_into_remote(remote_catalog, new_result)
                    changed_local_catalog = save_local_catalog(merged)
                    
                    # Intentar siempre actualizar cache.db para asegurar consistencia local,
                    # incluso si catalog.json no cambió (ej. resubida de archivo existente)
                    try:
                        logger.info("About to upsert cache from new_result for file=%s parsed=%s tmdb_id=%s", file_name, json.dumps(new_result.get('parsed') or {} , ensure_ascii=False), (new_result.get('tmdb_top') or {}).get('id'))
                        upsert_cache_from_new_result(new_result)
                    except Exception:
                        logger.exception('Error upserting into cache.db')

                    if changed_local_catalog:
                        with PENDING_LOCK:
                            LAST_CHANGE_TS = time.time()
                    else:
                        logger.info("No changes detected in catalog.json for file=%s (duplicate?)", file_name)
                try:
                    if temp_path and os.path.exists(temp_path): os.unlink(temp_path)
                except Exception: pass
                gc.collect()
            finally:
                # Decrement pending counter (asegurar que siempre ocurra)
                try:
                    with PENDING_LOCK:
                        PENDING_COUNT = max(0, PENDING_COUNT - 1)
                        logger.info("PENDING_COUNT decrementado -> %d", PENDING_COUNT)
                        # Do NOT set LAST_CHANGE_TS here unconditionally; upload should be coordinated above
                except Exception:
                    logger.exception("Error decrementando PENDING_COUNT")
    except Exception:
        logger.exception("Exception en process_sync_payload")

# FastAPI and startup: start worker thread and ensure DB
app = FastAPI(title="TG -> Catalog API (improved)")

@app.on_event("startup")
def startup_tasks():
    ensure_cache_db_exists_and_schema()
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    u = threading.Thread(target=uploader_loop, daemon=True)
    u.start()
    try:
        local_raw = None
        if os.path.exists(CATALOG_PATH):
            try:
                with open(CATALOG_PATH, 'rb') as f: local_raw = f.read()
            except Exception:
                local_raw = None
        remote_raw = _github_raw_get('catalog.json')
        if local_raw is not None and remote_raw is not None:
            try:
                local_digest = hashlib.sha256(local_raw).hexdigest()
                remote_digest = hashlib.sha256(remote_raw.encode('utf-8')).hexdigest()
                if local_digest == remote_digest:
                    globals()['LAST_UPLOADED_CATALOG_DIGEST'] = local_digest
                    with PENDING_LOCK:
                        globals()['LAST_CHANGE_TS'] = None
            except Exception:
                pass
    except Exception:
        logger.exception('Error initializing last uploaded digest')

    def _get_ngrok_public_url():
        candidates = [os.environ.get("NGROK_API_URL"), "http://ngrok:4040/api/tunnels", "http://192.168.1.34:4040/api/tunnels", "http://host.docker.internal:4040/api/tunnels", "http://172.17.0.1:4040/api/tunnels"]
        logger.info("Buscando URL pública de ngrok en: %s", candidates)
        for url in [u for u in candidates if u]:
            try:
                logger.info("Probando endpoint ngrok: %s", url)
                r = requests.get(url, timeout=2)
                if r.ok:
                    try:
                        j = r.json(); tlist = j.get("tunnels")
                        if tlist and isinstance(tlist, list) and len(tlist)>0:
                            found = tlist[0].get("public_url")
                            logger.info("Encontrada public_url en %s: %s", url, found)
                            return found
                    except Exception:
                        m = re.search(r'"public_url"\s*:\s*"([^"]+)"', r.text)
                        if m:
                            found = m.group(1)
                            logger.info("Encontrada public_url (regex) en %s: %s", url, found)
                            return found
            except Exception as e:
                logger.warning("Fallo conectando a %s: %s", url, e)
                continue
        logger.warning("No se encontró ninguna URL pública de ngrok en los candidatos.")
        return None
    pub = _get_ngrok_public_url()
    if pub and BOT_TOKEN:
        try:
            webhook_url = pub.rstrip("/") + "/api/webhook"
            logger.info("Intentando registrar webhook en Telegram: %s", webhook_url)
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", data={"url": webhook_url, "drop_pending_updates":"true"}, timeout=10)
            logger.info("Respuesta setWebhook: %s %s", r.status_code, r.text)
            try: _ = r.json()
            except Exception: pass
        except Exception: logger.exception("Error registrando webhook")
    else:
        logger.error("No se pudo configurar webhook: pub=%s BOT_TOKEN_SET=%s", bool(pub), bool(BOT_TOKEN))

@app.post("/api/webhook")
async def telegram_webhook(req: Request):
    raw = await req.body()
    try: payload = json.loads(raw.decode(errors="replace"))
    except Exception: payload = {}
    chat = (payload.get("message") or payload.get("channel_post") or {}).get("chat") or {}
    chat_id = chat.get("id")
    msg_type = "channel_post" if "channel_post" in payload else ("message" if "message" in payload else "unknown")
    logger.info("Webhook recibido tipo=%s chat_id=%s has_message=%s", msg_type, chat_id, bool(payload.get("message") or payload.get("channel_post")))
    try:
        PROCESS_QUEUE.put(payload, block=False)
    except Exception:
        PROCESS_QUEUE.put(payload)
    return JSONResponse({"ok": True})


@app.post("/api/force-upload")
async def force_upload():
    """Forzar subida inmediata del catalog.json y cache.db (útil para debug)."""
    if not os.path.exists(CATALOG_PATH):
        return JSONResponse({"ok": False, "error": "No local catalog.json"}, status_code=400)
    try:
        with open(CATALOG_PATH, 'rb') as f: catalog_bytes = f.read()
    except Exception:
        return JSONResponse({"ok": False, "error": "Failed reading local catalog"}, status_code=500)
    rr, _ = _github_api_get("catalog.json"); cur_sha = None
    if rr and rr.status_code==200:
        try: cur_sha = rr.json().get('sha')
        except Exception: cur_sha = None
    ok = _github_put("catalog.json", catalog_bytes, f"Force update catalog.json - {datetime.datetime.utcnow().isoformat()}", sha=cur_sha)
    if not ok:
        return JSONResponse({"ok": False, "error": "Failed uploading catalog.json"}, status_code=500)
    try:
        # For force-upload, upload the local cache.db file directly (no regeneration)
        ok_db = _upload_local_cache_db()
        if not ok_db:
            return JSONResponse({"ok": False, "error": "Failed uploading local cache.db"}, status_code=500)
    except Exception:
        logger.exception("Force upload: error generating/uploading cache.db")
        return JSONResponse({"ok": False, "error": "Exception generating cache.db"}, status_code=500)
    return JSONResponse({"ok": True, "uploaded_catalog": True, "uploaded_cache": True})

@app.get("/api/health")
async def health():
    return {"status":"ok","time": datetime.datetime.utcnow().isoformat()+"Z"}

@app.get("/")
async def root():
    return {"message":"TG Catalog API (improved)","status":"running"}
