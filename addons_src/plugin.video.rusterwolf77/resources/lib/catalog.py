# -*- coding: utf-8 -*-
import json
import time
import os
import urllib.parse
import urllib.request
import xbmc
import xbmcaddon
import re
import xbmcvfs
import threading
import queue
from resources.lib import db as _db

ADDON = xbmcaddon.Addon()
# LANG por defecto
LANG = "es-ES"
# Defaults (coinciden con resources/settings.xml)
WORKERS_DEFAULT = 6
UNENRICHED_BATCH_DEFAULT = 200


def _read_worker_settings():
    try:
        workers = ADDON.getSettingInt('background_workers')
        if not workers or workers <= 0:
            workers = WORKERS_DEFAULT
    except Exception:
        workers = WORKERS_DEFAULT
    try:
        batch = ADDON.getSettingInt('unenriched_batch')
        if not batch or batch <= 0:
            batch = UNENRICHED_BATCH_DEFAULT
    except Exception:
        batch = UNENRICHED_BATCH_DEFAULT
    return int(workers), int(batch)


def _log(level, msg):
    """Log helper que respeta el ajuste debug_logging."""
    try:
        debug = ADDON.getSettingBool('debug_logging')
    except Exception:
        debug = False
    # Si es DEBUG y no está activado, degradar a LOGDEBUG pero no mostrar como WARNING
    try:
        if level == xbmc.LOGDEBUG and not debug:
            xbmc.log(f"RusterWolf: {msg}", xbmc.LOGDEBUG)
        else:
            xbmc.log(f"RusterWolf: {msg}", level)
    except Exception:
        pass


# En este despliegue, el enriquecimiento (arte, sinopsis, cast) se gestiona externamente
# por las imágenes Docker. Deshabilitamos cualquier uso de TMDB desde el addon.
try:
    import tmdbsimple as tmdb  # type: ignore
except Exception:
    tmdb = None
_HAS_TMDBSIMPLE = False
xbmc.log("RusterWolf: enriquecimiento TMDB deshabilitado en addon (gestión externa en Docker)", xbmc.LOGWARNING)


# Carpeta de datos persistentes del addon en userdata
addon_id = ADDON.getAddonInfo('id')
userdata_path = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
# Usar carpeta temporal para caches no críticos; solo la copia de cache.db se mantendrá en userdata
try:
    temp_dir = os.path.join(os.environ.get('TMP', os.environ.get('TEMP', os.path.expanduser('~'))), f"rusterwolf_{addon_id}")
except Exception:
    temp_dir = os.path.join(os.path.expanduser('~'), f"rusterwolf_{addon_id}")
os.makedirs(temp_dir, exist_ok=True)
# Cache.json temporal (no contiene datos personales, solo metadata enriquecida)
CACHE_FILE = os.path.join(temp_dir, "cache.json")

# URLs de catálogos: intentar leer desde la configuración del addon (multilínea), con valores por defecto
try:
    raw = ADDON.getSetting('catalog_urls') or ''
except Exception:
    raw = ''
DEFAULT_CATALOG_URLS = [
    "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/refs/heads/main/catalog.json",
    "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/main/catalog.json",
]
CATALOG_URLS = [u.strip() for u in (raw.splitlines() if raw else []) if u.strip()] or DEFAULT_CATALOG_URLS

# Mapeo simple de acentos
ACCENT_MAP = {
    "anos": "años",
    "Ano": "Año",
    "si": "sí",
    "Si": "Sí"
}

def make_key(item):

    title = fix_accents(clean_title_for_tmdb(item.get("title", "")))
    if item.get("type") == "movie":
        return f"movie_{title}_{item.get('year','')}"
    else:
        return f"tv_{title}_{item.get('season','')}_{item.get('episode','')}"


def fetch_catalogs():
    """
    Intenta cargar los items desde un `catalog.json` remoto (lista `CATALOG_URLS`).

    Si ninguno de los catálogos remotos está disponible, vuelve a la estrategia
    original: inicializar/usar `cache.db` local y devolver sus filas.
    """
    # Intentar usar DB local primero (si existe y tiene items).
    try:
        try:
            _db.init_db()
        except Exception:
            pass
        items_db = _db.load_all_items()
        if items_db:
            xbmc.log(f"RusterWolf: cargados {len(items_db)} items desde DB local (prioridad sobre catálogo remoto)", xbmc.LOGWARNING)
            return items_db
    except Exception:
        pass

    # Intentar catálogos remotos primero
    for url in CATALOG_URLS:
        try:
            xbmc.log(f"RusterWolf: intentando descargar catálogo remoto desde {url}", xbmc.LOGDEBUG)
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    raw = resp.read()
            except Exception as e:
                xbmc.log(f"RusterWolf: fallo descargando {url}: {e}", xbmc.LOGDEBUG)
                continue
            try:
                data = json.loads(raw.decode('utf-8')) if raw else None
            except Exception as e:
                xbmc.log(f"RusterWolf: fallo parseando JSON desde {url}: {e}", xbmc.LOGERROR)
                continue
            if not isinstance(data, dict):
                xbmc.log(f"RusterWolf: catálogo remoto {url} no tiene formato esperado", xbmc.LOGWARNING)
                continue
            # Intentar cargar cache local para preservar metadata enriquecida si existe
            cached = {}
            try:
                if os.path.exists(CACHE_FILE):
                    with open(CACHE_FILE, 'r', encoding='utf-8') as cf:
                        cached = json.load(cf) or {}
            except Exception:
                cached = {}
            try:
                items = parse_json(data, cached, parallel=False)
                xbmc.log(f"RusterWolf: cargados {len(items)} items desde catálogo remoto {url}", xbmc.LOGWARNING)
                return items
            except Exception as e:
                xbmc.log(f"RusterWolf: error parseando catálogo remoto {url}: {e}", xbmc.LOGERROR)
                continue
        except Exception:
            continue

    # Fallback: usar DB local (inicializar si es necesario)
    try:
        _db.init_db()
    except Exception as e:
        xbmc.log(f"RusterWolf: error inicializando DB: {e}", xbmc.LOGERROR)

    try:
        items_db = _db.load_all_items()
        if items_db:
            xbmc.log(f"RusterWolf: cargados {len(items_db)} items desde DB (rápido)", xbmc.LOGWARNING)
            return items_db
    except Exception as e:
        xbmc.log(f"RusterWolf: error cargando items desde DB: {e}", xbmc.LOGERROR)

    xbmc.log("RusterWolf: No se encontró catálogo remoto ni cache.db local.", xbmc.LOGWARNING)
    return []
def parse_json(data, cached, parallel=False, max_workers=None, enrich=True):
    """
    Convierte el JSON en lista de items normalizados y enriquecidos.
    """
    items = []
    movie_items = []
    series_items = []

    # Películas
    for title, info in (data.get("movies") or {}).items():
        clean_title = clean_title_for_tmdb(title)
        clean_title = fix_accents(clean_title)
        torrents = [{"quality": q, "magnet": qinfo.get("magnet")} for q, qinfo in (info.get("qualities") or {}).items()]
        key = f"movie_{clean_title}_{info.get('year','')}"
        cached_item = cached.get(key)
        item = {
            "title": clean_title,
            "year": str(info.get("year") or ""),
            "type": "movie",
            "torrents": torrents,
            "date_added": info.get("date_added") or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tmdb_id": info.get("tmdb_id")
        }
        if cached_item and isinstance(cached_item, dict):
            _log(xbmc.LOGDEBUG, f"cached_item encontrado para {key} con keys={list(cached_item.keys())}")
            # Actualizar pero asegurar después que el tipo correcto se mantiene
            item.update(cached_item)
            if 'type' not in cached_item:
                _log(xbmc.LOGDEBUG, f"cached_item para {key} no tiene 'type'; forzando 'movie'")
        elif cached_item is not None:
            _log(xbmc.LOGDEBUG, f"cached_item para {key} no es dict, se ignora: {type(cached_item)}")
        # Asegurarnos de que el campo 'type' sea correcto
        item['type'] = 'movie'
        movie_items.append(item)

    # Series
    for title, seasons in (data.get("series") or {}).items():
        clean_title = clean_title_for_tmdb(title)
        clean_title = fix_accents(clean_title)
        for season, episodes in seasons.items():
            if not isinstance(episodes, dict):
                continue
            for episode, qualities in episodes.items():
                if not isinstance(qualities, dict):
                    continue
                torrents = [{"quality": q, "magnet": qinfo.get("magnet")} for q, qinfo in qualities.items() if isinstance(qinfo, dict)]
                key = f"tv_{clean_title}_{season}_{episode}"
                cached_item = cached.get(key)
                item = {
                    "title": clean_title,
                    "type": "tv",
                    # Normalizar season/episode a enteros cuando sea posible
                    "season": int(season) if (isinstance(season, (str, int)) and str(season).isdigit()) else season,
                    "episode": int(episode) if (isinstance(episode, (str, int)) and str(episode).isdigit()) else episode,
                    "torrents": torrents,
                    "date_added": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "tmdb_id": qualities.get("tmdb_id") if isinstance(qualities.get("tmdb_id"), (str, int)) else None
                }
                if cached_item and isinstance(cached_item, dict):
                    _log(xbmc.LOGDEBUG, f"cached_item encontrado para {key} con keys={list(cached_item.keys())}")
                    # Merge cached item carefully: no sobrescribir campos enriquecidos vacíos
                    for k, v in cached_item.items():
                        try:
                            if k in ('overview', 'episode_overview', 'poster', 'fanart', 'episode_title', 'still_path'):
                                # solo escribir si el cached tiene valor no vacío y actual no tiene mejor valor
                                if v:
                                    item[k] = v
                            else:
                                item[k] = v
                        except Exception:
                            continue
                    if 'type' not in cached_item:
                        _log(xbmc.LOGDEBUG, f"cached_item para {key} no tiene 'type'; forzando 'tv'")
                elif cached_item is not None:
                    _log(xbmc.LOGDEBUG, f"cached_item para {key} no es dict, se ignora: {type(cached_item)}")
                # Asegurarnos de que el campo 'type' sea correcto
                item['type'] = 'tv'
                series_items.append(item)

    def _maybe_enrich(item):
        if not enrich:
            return item
        if "overview" in item and "poster" in item:
            return item
        return enrich_with_tmdb(item)

    # Paralelizar enriquecimiento si se solicita
    import inspect
    args = inspect.getfullargspec(parse_json).args
    parallel = False
    if "parallel" in args:
        frame = inspect.currentframe()
        parallel = frame.f_back.f_locals.get("parallel", False)

    def _thread_map(func, seq, workers):
        """Map helper using daemon threads to avoid non-daemon ThreadPoolExecutor threads.

        Returns list of results in original order.
        """
        if not seq:
            return []
        q = queue.Queue()
        results = [None] * len(seq)

        for idx, val in enumerate(seq):
            q.put((idx, val))

        def _w():
            while True:
                try:
                    idx, val = q.get_nowait()
                except Exception:
                    break
                try:
                    res = func(val)
                    results[idx] = res
                except Exception:
                    results[idx] = None
                finally:
                    try:
                        q.task_done()
                    except Exception:
                        pass

        threads = []
        for _ in range(max(1, workers or 1)):
            t = threading.Thread(target=_w, daemon=True)
            t.start()
            threads.append(t)
        q.join()
        return results

    if parallel:
        # permitir sobreescritura desde quien llama, si no usar configuración
        if not max_workers:
            max_workers, _ = _read_worker_settings()
        items.extend([r for r in _thread_map(_maybe_enrich, movie_items, max_workers) if r is not None])
        items.extend([r for r in _thread_map(_maybe_enrich, series_items, max_workers) if r is not None])
    else:
        items.extend([_maybe_enrich(item) for item in movie_items])
        items.extend([_maybe_enrich(item) for item in series_items])

    return items


def enrich_items_by_keys(keys, max_workers=2):
    """Enriquece un conjunto pequeño de items identificados por su key.

    Esta función se deja como no-op por diseño: el enriquecimiento se realiza
    externamente (p. ej. en las imágenes Docker que preparan la base de datos
    y el arte). Se mantiene la firma para compatibilidad.
    """
    try:
        xbmc.log('RusterWolf: enrich_items_by_keys llamado pero enriquecimiento está deshabilitado (gestión externa).', xbmc.LOGDEBUG)
    except Exception:
        pass
    return 0


# Enrichment queue + single worker to avoid spawning many threads from the UI
_enrich_queue = None
_enrich_thread = None
_enrich_thread_lock = threading.Lock()
_last_refresh = 0

def _enrich_worker():
    # Worker deshabilitado — no procesará cola de enriquecimiento ya que ese proceso es externo.
    try:
        xbmc.log('RusterWolf: enrich worker no iniciado; enriquecimiento gestionado externamente.', xbmc.LOGDEBUG)
    except Exception:
        pass
    return


def enqueue_enrich(keys):
    """Encola keys para enriquecimiento por un único worker daemon.

    keys: lista de keys o iterable
    """
    global _enrich_queue, _enrich_thread
    with _enrich_thread_lock:
        if _enrich_queue is None:
            _enrich_queue = queue.Queue()
        if _enrich_thread is None or not _enrich_thread.is_alive():
            _enrich_thread = threading.Thread(target=_enrich_worker, daemon=True)
            _enrich_thread.start()
    # No encolamos nada: enriquecimiento está deshabilitado
    try:
        xbmc.log('RusterWolf: enqueue_enrich llamada pero enriquecimiento está deshabilitado; ignorando.', xbmc.LOGDEBUG)
    except Exception:
        pass


def clean_title_for_tmdb(title):
    """
    Limpia títulos de cualquier sufijo residual.
    """
    title = re.sub(r'\b(1080p|720p|2160p|4k|HDTV|Bluray|Esp|Eng|Cap|WebRip|WebDL|Remux|SubEsp|Latam|Multi|Especial|Especial Navidad|Cap\d+)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[\[\]\(\)\{\}]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()

    return title


def fix_accents(title):
    """
    Aplica correcciones simples de acentos y palabras en español.
    """
    for k, v in ACCENT_MAP.items():
        title = re.sub(rf"\b{k}\b", v, title, flags=re.IGNORECASE)
    return title


def enrich_with_tmdb(item):
    # Enriquecimiento TMDB deshabilitado — devolver el item tal cual.
    try:
        xbmc.log(f"RusterWolf: enrich_with_tmdb llamado para {item.get('title')} pero enriquecimiento deshabilitado; devolviendo item sin cambios.", xbmc.LOGDEBUG)
    except Exception:
        pass
    return item


def load_cache():
    """
    Carga el cache desde cache.json en forma de diccionario.
    """
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: v for k, v in data.items()}
    except Exception as e:
        xbmc.log(f"RusterWolf: error cargando cache: {e}", xbmc.LOGERROR)
        return {}


def save_cache(items):
    """
    Guarda items enriquecidos en cache.json.
    """
    cache_dict = {}
    for it in items:
        if it.get("type") == "movie":
            key = f"movie_{it['title']}_{it.get('year','')}"
        else:
            key = f"tv_{it['title']}_{it.get('season','')}_{it.get('episode','')}"
        cache_dict[key] = it
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_dict, f, ensure_ascii=False, indent=2)
        xbmc.log(f"RusterWolf: cache guardada ({len(cache_dict)} items)", xbmc.LOGDEBUG)
    except Exception as e:
        xbmc.log(f"RusterWolf: error guardando cache: {e}", xbmc.LOGERROR)
        

def sort_by_newest(items):
    """
    Devuelve los items ordenados por fecha de inserción (date_added) más reciente primero.
    """
    return sorted(items, key=lambda x: x.get("date_added",""), reverse=True)


def prioritize_items(keys):
    """Pide al background worker que enriquezca con prioridad los items cuyas keys se pasan.

    keys: lista de strings (keys en la DB)
    """
    # Prioritización deshabilitada por petición del usuario: evitar enriquecimiento en background
    try:
        xbmc.log("RusterWolf: prioritize_items llamada pero deshabilitada (no se realizará enriquecimiento)", xbmc.LOGWARNING)
    except Exception:
        pass
    return


def prioritize_visible_items(item_dicts):
    """Prioriza el enriquecimiento para una lista de items (dicts) ya obtenidos en memoria.

    Útil en primera carga cuando la DB aún no contiene las entradas.
    """
    # Prioritización visible deshabilitada por petición del usuario
    try:
        xbmc.log("RusterWolf: prioritize_visible_items llamada pero deshabilitada (no se realizará enriquecimiento visible)", xbmc.LOGWARNING)
    except Exception:
        pass
    return
        
    
