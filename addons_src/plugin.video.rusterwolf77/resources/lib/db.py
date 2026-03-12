# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import shutil
import xbmc
import xbmcaddon
import xbmcvfs
import urllib.request
import socket
import time
import tempfile
import traceback
import hashlib

ADDON = xbmcaddon.Addon()
addon_id = ADDON.getAddonInfo('id')
USERDATA = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
# Ubicación principal de cache.db en userdata (solo este archivo se mantiene en addon_data)
DB_FILE = os.path.join(USERDATA, 'cache.db')
try:
    TEMP_DIR = os.path.join(os.environ.get('TMP', os.environ.get('TEMP', os.path.expanduser('~'))), f"rusterwolf_{addon_id}")
except Exception:
    TEMP_DIR = os.path.join(os.path.expanduser('~'), f"rusterwolf_{addon_id}")
os.makedirs(TEMP_DIR, exist_ok=True)

# Flag to indicate whether the UI has been notified about a DB update this session
DB_UPDATE_NOTIFIED = False


def safe_replace_file(src, dst):
    """Replace dst with src safely using Kodi VFS when possible.

    Returns True on success, False otherwise.
    """
    try:
        from xbmcvfs import rename as _vfs_rename
    except Exception:
        _vfs_rename = None
    # Prefer VFS rename when available (works across Android storage boundaries)
    if _vfs_rename:
        try:
            if _vfs_rename(src, dst):
                return True
        except Exception:
            pass
    try:
        shutil.move(src, dst)
        return True
    except Exception:
        pass
    try:
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except Exception:
            pass
        return True
    except Exception:
        return False


def is_db_update_notified():
    """Returns True if the UI has already been notified about DB update this session."""
    try:
        return bool(DB_UPDATE_NOTIFIED)
    except Exception:
        return False


def mark_db_update_notified():
    """Mark that the UI has been notified about DB update this session.

    Returns True on success, False otherwise.
    """
    global DB_UPDATE_NOTIFIED
    try:
        DB_UPDATE_NOTIFIED = True
        return True
    except Exception:
        return False

# URL remota para descargar cache.db si el usuario la provee
REMOTE_DB_URLS = [
    # fallback defaults; will be replaceable from settings
    "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/main/cache.db",
    "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/refs/heads/main/cache.db",
]

try:
    _raw_db_urls = ADDON.getSetting('remote_db_urls') or ''
except Exception:
    _raw_db_urls = ''
DEFAULT_REMOTE_DB_URLS = REMOTE_DB_URLS
REMOTE_DB_URLS = [u.strip() for u in (_raw_db_urls.splitlines() if _raw_db_urls else []) if u.strip()] or DEFAULT_REMOTE_DB_URLS

_SCHEMA = '''
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
  overview TEXT,
    episode_title TEXT,
    episode_overview TEXT,
    still_path TEXT,
        clearlogo TEXT,
        banner TEXT,
        clearart TEXT,
  genres TEXT,
  "cast" TEXT,
  torrents TEXT,
  date_added TEXT,
  enriched INTEGER DEFAULT 0
)
'''

def _connect():
    """Conecta a SQLite con timeout y sin bloquear si la DB está ocupada."""
    conn = sqlite3.connect(DB_FILE, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA read_uncommitted = 1;")
    except Exception:
        pass
    # Si después de los intentos anteriores no existe DB en USERDATA, intentar un último intento explícito
    try:
        if not os.path.exists(DB_FILE) and REMOTE_DB_URLS:
            xbmc.log('RusterWolf: DB no encontrada en userdata tras intentos previos, realizando intento final explícito de descarga', xbmc.LOGWARNING)
            for url in REMOTE_DB_URLS:
                try:
                    xbmc.log(f'RusterWolf: intento final descargando DB desde {url}', xbmc.LOGDEBUG)
                    with urllib.request.urlopen(url, timeout=60) as r:
                        data = r.read()
                    if not data:
                        xbmc.log(f'RusterWolf: intento final desde {url} no devolvió datos', xbmc.LOGDEBUG)
                        continue
                    # write to temp and validate
                    # Write temporary DB inside the userdata folder (same dir as DB_FILE)
                    # Escribir el archivo temporal SIEMPRE en TEMP_DIR
                    try:
                        os.makedirs(TEMP_DIR, exist_ok=True)
                        tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                        with open(tmpf, 'wb') as _tf:
                            _tf.write(data)
                    except Exception as e:
                        xbmc.log(f'RusterWolf: no se pudo escribir el archivo tmp en TEMP_DIR: {e}', xbmc.LOGERROR)
                        # Fallback a temp de sistema si TEMP_DIR falla
                        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                        tmpf = tf.name
                        try:
                            tf.write(data)
                        finally:
                            tf.close()
                                # Fallback to TEMP_DIR then system temp if needed
                        try:
                            os.makedirs(TEMP_DIR, exist_ok=True)
                            tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                            with open(tmpf, 'wb') as _tf:
                                _tf.write(data)
                        except Exception:
                            tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                            tmpf = tf.name
                            try:
                                tf.write(data)
                            finally:
                                tf.close()
                    try:
                        vconn = sqlite3.connect(tmpf, timeout=5)
                        vc = vconn.cursor()
                        vc.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                        _ = vc.fetchall()
                        vconn.close()
                    except Exception as ve:
                        xbmc.log(f'RusterWolf: intento final: archivo descargado NO es sqlite válida desde {url}: {ve}', xbmc.LOGERROR)
                        try:
                            os.remove(tmpf)
                        except Exception:
                            pass
                        continue
                    # move into place
                    try:
                        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
                        # Use module-level helper if present, otherwise fallback
                        try:
                            ok = safe_replace_file(tmpf, DB_FILE)
                        except Exception:
                            ok = False
                        if not ok:
                            try:
                                shutil.move(tmpf, DB_FILE)
                            except Exception:
                                pass
                        xbmc.log(f'RusterWolf: intento final: DB remota descargada y movida a {DB_FILE}', xbmc.LOGWARNING)
                        break
                    except Exception as e:
                        xbmc.log(f'RusterWolf: intento final: fallo moviendo DB a destino: {e}', xbmc.LOGERROR)
                        try:
                            if tmpf and os.path.exists(tmpf):
                                os.remove(tmpf)
                        except Exception:
                            pass
                        continue
                except Exception as e:
                    xbmc.log(f'RusterWolf: intento final: excepción descargando DB desde {url}: {e}', xbmc.LOGDEBUG)
                    continue
    except Exception:
        pass
    return conn


def maybe_update_db_from_remote():
    """Intentar descargar la DB remota siempre en arranque. Validar sqlite y reemplazar sólo si cambia (SHA1).

    No lanza excepción en errores de red; simplemente registra y vuelve.
    """
    if not REMOTE_DB_URLS:
        xbmc.log('RusterWolf: no hay REMOTE_DB_URLS configuradas, saltando comprobación remota', xbmc.LOGDEBUG)
        return False

    def _sha1_of_file(path):
        h = hashlib.sha1()
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    local_hash = _sha1_of_file(DB_FILE) if os.path.exists(DB_FILE) else None

    for url in REMOTE_DB_URLS:
        # Añadir timestamp para evitar cache
        dl_url = f"{url}{'&' if '?' in url else '?'}t={int(time.time())}"
        tmpf = None
        try:
            xbmc.log(f'RusterWolf: intentando descargar DB remota desde {dl_url} (comprobación en arranque)', xbmc.LOGDEBUG)
            data = None
            for attempt in range(1, 4):
                try:
                    with urllib.request.urlopen(dl_url, timeout=60) as r:
                        data = r.read()
                        xbmc.log(f'RusterWolf: descarga remota exitosa desde {url} intentos={attempt} bytes={len(data)}', xbmc.LOGWARNING)
                        break
                except Exception as e:
                    xbmc.log(f'RusterWolf: intento {attempt} fallo descargando DB {url}: {e}', xbmc.LOGDEBUG)
                    if attempt < 3:
                        time.sleep(1)
                    continue
            if not data:
                xbmc.log(f'RusterWolf: no se pudo descargar DB desde {url} tras varios intentos', xbmc.LOGDEBUG)
                continue

            # escribir a fichero temporal
            # Write temporary DB inside the userdata folder (same dir as DB_FILE)
            # Escribir el archivo temporal SIEMPRE en TEMP_DIR
            try:
                os.makedirs(TEMP_DIR, exist_ok=True)
                tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                with open(tmpf, 'wb') as _tf:
                    _tf.write(data)
            except Exception as e:
                xbmc.log(f'RusterWolf: no se pudo escribir el archivo tmp en TEMP_DIR: {e}', xbmc.LOGERROR)
                # Fallback a temp de sistema si TEMP_DIR falla
                tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                tmpf = tf.name
                try:
                    tf.write(data)
                finally:
                    tf.close()
                try:
                    os.makedirs(TEMP_DIR, exist_ok=True)
                    tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                    with open(tmpf, 'wb') as _tf:
                        _tf.write(data)
                except Exception:
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                    tmpf = tf.name
                    try:
                        tf.write(data)
                    finally:
                        tf.close()

            # validar sqlite
            try:
                vconn = sqlite3.connect(tmpf, timeout=5)
                vc = vconn.cursor()
                vc.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                _ = vc.fetchall()
                vconn.close()
            except Exception as ve:
                xbmc.log(f'RusterWolf: archivo descargado NO es una sqlite válida desde {url}: {ve}', xbmc.LOGERROR)
                try:
                    if tmpf and os.path.exists(tmpf):
                        os.remove(tmpf)
                except Exception:
                    pass
                continue

            # calcular hash del temp y comparar con local
            remote_hash = _sha1_of_file(tmpf)
            if not remote_hash:
                xbmc.log(f'RusterWolf: no se pudo calcular SHA1 del DB remota desde {url}', xbmc.LOGDEBUG)
                try:
                    os.remove(tmpf)
                except Exception:
                    pass
                continue

            if local_hash == remote_hash:
                xbmc.log(f'RusterWolf: DB remota idéntica a local (SHA1={remote_hash}), no se reemplaza', xbmc.LOGDEBUG)
                try:
                    os.remove(tmpf)
                except Exception:
                    pass
                return False

            # reemplazar: hacer copia de seguridad del local si existe (backup en TEMP_DIR)
            try:
                # use module-level safe_replace_file helper (defined at top of module)
                if os.path.exists(DB_FILE):
                    try:
                        # Usar un único backup rotativo para evitar acumular ficheros
                        bak = os.path.join(TEMP_DIR, "cache.db.bak")
                        shutil.copy2(DB_FILE, bak)
                        xbmc.log(f'RusterWolf: copia de seguridad rotativa creada en TEMP {bak}', xbmc.LOGWARNING)
                    except Exception as e:
                        xbmc.log(f'RusterWolf: fallo creando copia de seguridad en TEMP {e}', xbmc.LOGERROR)
                ok = safe_replace_file(tmpf, DB_FILE)
                if ok:
                    xbmc.log(f'RusterWolf: DB remota validada y movida a {DB_FILE} (SHA1={remote_hash})', xbmc.LOGWARNING)
                    return True
                else:
                    xbmc.log(f'RusterWolf: error moviendo DB validada a destino (safe_replace_file fallo)', xbmc.LOGERROR)
                    try:
                        if tmpf and os.path.exists(tmpf):
                            os.remove(tmpf)
                    except Exception:
                        pass
                    continue
            except Exception as e:
                xbmc.log(f'RusterWolf: error moviendo DB validada a destino: {e}', xbmc.LOGERROR)
                xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
                try:
                    if tmpf and os.path.exists(tmpf):
                        os.remove(tmpf)
                except Exception:
                    pass
                continue

        except Exception as e:
            xbmc.log(f'RusterWolf: excepción comprobando DB remota desde {url}: {e}', xbmc.LOGDEBUG)
            xbmc.log(traceback.format_exc(), xbmc.LOGDEBUG)
            try:
                if tmpf and os.path.exists(tmpf):
                    os.remove(tmpf)
            except Exception:
                pass
            continue

    return False

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    # Debug: show which URLs we will try and what setting raw value is
    try:
        xbmc.log(f'RusterWolf: init_db starting, DB_FILE={DB_FILE}', xbmc.LOGDEBUG)
        xbmc.log(f'RusterWolf: REMOTE_DB_URLS={REMOTE_DB_URLS}', xbmc.LOGDEBUG)
        xbmc.log(f'RusterWolf: raw remote_db_urls setting (first 400 chars)="{_raw_db_urls[:400]}"', xbmc.LOGDEBUG)
    except Exception:
        pass
    # Si no existe DB local en userdata, intentar descargar la DB remota proporcionada por el usuario
    try:
        if not os.path.exists(DB_FILE):
            for url in REMOTE_DB_URLS:
                # Añadir timestamp para evitar cache
                dl_url = f"{url}{'&' if '?' in url else '?'}t={int(time.time())}"
                try:
                    xbmc.log(f'RusterWolf: intentando descargar DB remota desde {dl_url}', xbmc.LOGDEBUG)
                    data = None
                    # intentar varios reintentos en caso de timeouts o fallos transitorios
                    for attempt in range(1, 4):
                        try:
                            with urllib.request.urlopen(dl_url, timeout=60) as r:
                                data = r.read()
                                xbmc.log(f'RusterWolf: descarga exitosa desde {url} intentos={attempt} bytes={len(data)}', xbmc.LOGWARNING)
                                break
                        except Exception as e:
                            xbmc.log(f'RusterWolf: intento {attempt} fallo descargando DB {url}: {e}', xbmc.LOGDEBUG)
                            if attempt < 3:
                                time.sleep(1)
                            continue
                    if not data:
                        xbmc.log(f'RusterWolf: no se pudo descargar DB desde {url} tras varios intentos', xbmc.LOGDEBUG)
                        continue
                    # write to temporary file first and validate it's a sqlite DB
                    tmpf = None
                    try:
                        # Write temporary DB inside TEMP_DIR to avoid cross-filesystem moves
                        # Escribir el archivo temporal SIEMPRE en TEMP_DIR
                        try:
                            os.makedirs(TEMP_DIR, exist_ok=True)
                            tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                            with open(tmpf, 'wb') as _tf:
                                _tf.write(data)
                        except Exception as e:
                            xbmc.log(f'RusterWolf: no se pudo escribir el archivo tmp en TEMP_DIR: {e}', xbmc.LOGERROR)
                            # Fallback a temp de sistema si TEMP_DIR falla
                            tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                            tmpf = tf.name
                            try:
                                tf.write(data)
                            finally:
                                tf.close()
                            try:
                                os.makedirs(TEMP_DIR, exist_ok=True)
                                tmpf = os.path.join(TEMP_DIR, f'tmp_db_{int(time.time())}.db')
                                with open(tmpf, 'wb') as _tf:
                                    _tf.write(data)
                            except Exception:
                                tf = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                                tmpf = tf.name
                                tf.write(data)
                                tf.close()
                        # validate sqlite by opening and running a simple query
                        try:
                            vconn = sqlite3.connect(tmpf, timeout=5)
                            vc = vconn.cursor()
                            vc.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                            _ = vc.fetchall()
                            vconn.close()
                        except Exception as ve:
                            xbmc.log(f'RusterWolf: archivo descargado NO es una sqlite válida desde {url}: {ve}', xbmc.LOGERROR)
                            try:
                                if tmpf and os.path.exists(tmpf):
                                    os.remove(tmpf)
                            except Exception:
                                pass
                            continue
                        # Move validated tmp file into place
                        try:
                            ok = safe_replace_file(tmpf, DB_FILE)
                            if ok:
                                xbmc.log(f'RusterWolf: DB remota validada y guardada en {DB_FILE}', xbmc.LOGWARNING)
                                break
                            else:
                                raise Exception('safe_replace_file failed')
                        except Exception as e:
                            xbmc.log(f'RusterWolf: error moviendo DB validada a destino: {e}', xbmc.LOGERROR)
                            try:
                                if tmpf and os.path.exists(tmpf):
                                    os.remove(tmpf)
                            except Exception:
                                pass
                            continue
                    except Exception as e:
                        xbmc.log(f'RusterWolf: error procesando DB descargada temporalmente: {e}', xbmc.LOGERROR)
                        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
                        try:
                            if tmpf and os.path.exists(tmpf):
                                os.remove(tmpf)
                        except Exception:
                            pass
                        continue
                except Exception as e:
                    xbmc.log(f'RusterWolf: excepción al intentar descargar DB desde {url}: {e}', xbmc.LOGDEBUG)
                    xbmc.log(traceback.format_exc(), xbmc.LOGDEBUG)
                    continue
    except Exception:
        pass
    # Si hay una DB precargada ya colocada en la carpeta userdata del addon (ej. por instalación manual), usarla
    try:
        if not os.path.exists(DB_FILE):
            # buscar ficheros con nombres comunes en USERDATA
            userdata_dir = os.path.dirname(DB_FILE)
            preload_names = ['preload.db', 'preloaded.db', 'initial.db', 'cache_preloaded.db', 'cache_initial.db']
            for name in preload_names:
                candidate = os.path.join(userdata_dir, name)
                try:
                    if os.path.exists(candidate):
                        try:
                            shutil.copy2(candidate, DB_FILE)
                            xbmc.log(f'RusterWolf: DB precargada encontrada en userdata y copiada {candidate} -> {DB_FILE}', xbmc.LOGWARNING)
                        except Exception as e:
                            xbmc.log(f'RusterWolf: fallo copiando DB precargada desde userdata {candidate}: {e}', xbmc.LOGERROR)
                        break
                except Exception:
                    continue
    except Exception:
        pass
    # Si no existe DB en userdata, buscar una DB precargada dentro de la carpeta del addon
    try:
        if not os.path.exists(DB_FILE):
            try:
                addon_path = xbmcaddon.Addon().getAddonInfo('path')
            except Exception:
                addon_path = None
            preloaded_db = None
            if addon_path:
                # Buscar archivos comunes
                candidates = [
                    os.path.join(addon_path, 'cache.db'),
                    os.path.join(addon_path, 'preload.db'),
                    os.path.join(addon_path, 'preloaded.db'),
                    os.path.join(addon_path, 'resources', 'cache.db'),
                ]
                for c in candidates:
                    try:
                        if c and os.path.exists(c):
                            preloaded_db = c
                            break
                    except Exception:
                        continue
                # Si no encontramos en candidatos, buscar cualquier .db en el addon (primer resultado)
                if not preloaded_db:
                    for root, dirs, files in os.walk(addon_path):
                        for f in files:
                            if f.lower().endswith('.db') and 'cache' in f.lower() or 'preload' in f.lower():
                                candidate = os.path.join(root, f)
                                try:
                                    if os.path.exists(candidate):
                                        preloaded_db = candidate
                                        break
                                except Exception:
                                    continue
                        if preloaded_db:
                            break
            if preloaded_db:
                try:
                    shutil.copy2(preloaded_db, DB_FILE)
                    xbmc.log(f'RusterWolf: DB precargada copiada desde {preloaded_db} a {DB_FILE}', xbmc.LOGWARNING)
                except Exception as e:
                    xbmc.log(f'RusterWolf: fallo copiando DB precargada {preloaded_db} -> {DB_FILE}: {e}', xbmc.LOGERROR)
    except Exception:
        # No bloquear la inicialización por fallos en la copia; la creación continúa abajo
        pass
    conn = _connect()
    try:
        c = conn.cursor()
        c.executescript(_SCHEMA)
        # Ensure new columns exist for backward compatibility (ALTER TABLE when necesario)
        try:
            # fetch current columns
            c.execute("PRAGMA table_info(items)")
            cols = [r[1] for r in c.fetchall()]
            needed = {
                'episode_title': 'TEXT',
                'episode_overview': 'TEXT',
                'still_path': 'TEXT',
                'clearlogo': 'TEXT',
                'banner': 'TEXT',
                'clearart': 'TEXT'
            }
            for col, coltype in needed.items():
                if col not in cols:
                    try:
                        c.execute(f'ALTER TABLE items ADD COLUMN {col} {coltype}')
                        xbmc.log(f'RusterWolf DB: se añadió columna {col} a items', xbmc.LOGWARNING)
                    except Exception as e:
                        xbmc.log(f'RusterWolf DB: fallo añadiendo columna {col}: {e}', xbmc.LOGERROR)
        except Exception:
            pass
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_tmdb ON items(tmdb_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_enriched ON items(enriched)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_title ON items(title)')
        try:
            c.execute('PRAGMA journal_mode=WAL;')
            c.execute('PRAGMA synchronous=NORMAL;')
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()

def bulk_upsert(items):
    if not items:
        return
    conn = _connect()
    try:
        c = conn.cursor()
        vals = []
        for it in items:
            vals.append((
                it.get('key'),
                it.get('title'),
                it.get('type'),
                it.get('year'),
                it.get('season'),
                it.get('episode'),
                it.get('tmdb_id'),
                it.get('poster'),
                it.get('fanart'),
                it.get('overview'),
                it.get('episode_title'),
                it.get('episode_overview'),
                it.get('still_path'),
                it.get('clearlogo'),
                it.get('banner'),
                it.get('clearart'),
                json.dumps(it.get('genres') or []),
                json.dumps(it.get('cast') or []),
                json.dumps(it.get('torrents') or []),
                it.get('date_added'),
                1 if it.get('overview') or it.get('poster') else 0
            ))
        c.executemany('''
            INSERT OR REPLACE INTO items ("key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', vals)
        conn.commit()
    finally:
        conn.close()

def upsert_item(it):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO items ("key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            it.get('key'),
            it.get('title'),
            it.get('type'),
            it.get('year'),
            it.get('season'),
            it.get('episode'),
            it.get('tmdb_id'),
            it.get('poster'),
            it.get('fanart'),
            it.get('overview'),
            it.get('episode_title'),
            it.get('episode_overview'),
            it.get('still_path'),
            it.get('clearlogo'),
            it.get('banner'),
            it.get('clearart'),
            json.dumps(it.get('genres') or []),
            json.dumps(it.get('cast') or []),
            json.dumps(it.get('torrents') or []),
            it.get('date_added'),
            1 if it.get('overview') or it.get('poster') else 0
        ))
        conn.commit()
    finally:
        conn.close()

def load_all_items():
    if not os.path.exists(DB_FILE):
        return []
    conn = _connect()
    try:
        c = conn.cursor()
        xbmc.log('RusterWolf DB: ejecutando SELECT all items', xbmc.LOGDEBUG)
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched FROM items')
        rows = c.fetchall()
        items = []
        for r in rows:
            # Coerce season/episode to integers cuando sea posible para consistencia
            try:
                season_val = int(r[4]) if r[4] is not None and str(r[4]).strip() != '' else None
            except Exception:
                season_val = None
            try:
                episode_val = int(r[5]) if r[5] is not None and str(r[5]).strip() != '' else None
            except Exception:
                episode_val = None
            items.append({
                'key': r[0],
                'title': r[1],
                'type': r[2],
                'year': r[3],
                'season': season_val,
                'episode': episode_val,
                'tmdb_id': r[6],
                'poster': r[7],
                'fanart': r[8],
                'overview': r[9],
                'episode_title': r[10],
                'episode_overview': r[11],
                'still_path': r[12],
                'clearlogo': r[13],
                'banner': r[14],
                'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19],
                'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()

def load_items_by_keys(keys):
    keys = [k for k in keys if k]
    if not keys or not os.path.exists(DB_FILE):
        return []
    conn = _connect()
    try:
        c = conn.cursor()
        placeholders = ','.join('?' for _ in keys)
        query = f'''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched
            FROM items WHERE "key" IN ({placeholders})
        '''
        xbmc.log(f'RusterWolf DB: SELECT by keys batch={len(keys)}', xbmc.LOGDEBUG)
        c.execute(query, keys)
        rows = c.fetchall()
        items = []
        for r in rows:
            items.append({
                'key': r[0],
                'title': r[1],
                'type': r[2],
                'year': r[3],
                'season': r[4],
                'episode': r[5],
                'tmdb_id': r[6],
                'poster': r[7],
                'fanart': r[8],
                'overview': r[9],
                'episode_title': r[10],
                'episode_overview': r[11],
                'still_path': r[12],
                'clearlogo': r[13],
                'banner': r[14],
                'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19],
                'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()

def search_items_sql(query_str, limit=50):
    """Busca items usando SQL LIKE en lugar de cargar todo en memoria."""
    if not os.path.exists(DB_FILE) or not query_str:
        return []
    conn = _connect()
    try:
        c = conn.cursor()
        # Búsqueda insensible a mayúsculas por título
        like_str = f"%{query_str}%"
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched 
            FROM items 
            WHERE title LIKE ? OR episode_title LIKE ?
            LIMIT ?
        ''', (like_str, like_str, limit))
        
        rows = c.fetchall()
        items = []
        for r in rows:
            try:
                season_val = int(r[4]) if r[4] is not None and str(r[4]).strip() != '' else None
                episode_val = int(r[5]) if r[5] is not None and str(r[5]).strip() != '' else None
            except: season_val, episode_val = None, None

            items.append({
                'key': r[0],
                'title': r[1],
                'type': r[2],
                'year': r[3],
                'season': season_val,
                'episode': episode_val,
                'tmdb_id': r[6],
                'poster': r[7],
                'fanart': r[8],
                'overview': r[9],
                'episode_title': r[10],
                'episode_overview': r[11],
                'still_path': r[12],
                'clearlogo': r[13],
                'banner': r[14],
                'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19],
                'enriched': bool(r[20])
            })
        return items
    except Exception as e:
        xbmc.log(f"RusterWolf DB: error en search_items_sql: {e}", xbmc.LOGERROR)
        return []
    finally:
        conn.close()

def find_unenriched(limit=200):
    if not os.path.exists(DB_FILE):
        return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key" FROM items WHERE enriched=0 LIMIT ?', (limit,))
        return [r[0] for r in c.fetchall()]
    finally:
        conn.close()

def get_next_episode(tvshowtitle, season, episode):
    """Busca el siguiente episodio en la base de datos."""
    import unicodedata, re
    
    def normalize(s):
        if not s: return ''
        s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII').lower()
        return re.sub(r'[^a-z0-9]', '', s)
    
    target_title = normalize(tvshowtitle)
    if not target_title: return None

    conn = _connect()
    try:
        c = conn.cursor()
        # Obtenemos todos los items de tipo TV para filtrar en python (más seguro con normalización)
        c.execute('SELECT "key", title, season, episode, torrents, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path FROM items WHERE type="tv"')
        rows = c.fetchall()
        
        try:
            curr_s = int(season)
            curr_e = int(episode)
        except: return None

        # Buscamos S.E+1 o S+1.E1
        target_next = (curr_s, curr_e + 1)
        target_next_season = (curr_s + 1, 1)
        
        cand_next = None
        cand_next_season = None

        for r in rows:
            if normalize(r[1]) != target_title:
                continue
            try:
                s = int(r[2])
                e = int(r[3])
            except: continue

            if (s, e) == target_next:
                cand_next = r
            elif (s, e) == target_next_season:
                cand_next_season = r
        
        res = cand_next or cand_next_season
        if res:
            return {
                'key': res[0],
                'title': res[1],
                'season': int(res[2]),
                'episode': int(res[3]),
                'torrents': json.loads(res[4]) if res[4] else [],
                'tmdb_id': res[5],
                'poster': res[6],
                'fanart': res[7],
                'overview': res[8],
                'episode_title': res[9],
                'episode_overview': res[10],
                'still_path': res[11]
            }
    except Exception as e:
        xbmc.log(f"RusterWolf DB: error buscando siguiente episodio: {e}", xbmc.LOGERROR)
    finally:
        conn.close()
    return None
