# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmc
import xbmcaddon
import xbmcvfs

# Parche Global para Android TV: Forzar IPv4 en las peticiones HTTP de Python
# Evita que la descarga desde Cloudflare R2 falle con "Errno 101 Network is unreachable" por mal enrutamiento IPv6
import socket
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    ipv4_res = [r for r in res if r[0] == socket.AF_INET]
    return ipv4_res if ipv4_res else res
socket.getaddrinfo = _ipv4_getaddrinfo

ADDON = xbmcaddon.Addon()
addon_id = ADDON.getAddonInfo('id')
ADDON_ICON = ADDON.getAddonInfo('icon')

# Directorio persistente para archivos de configuración pequeños (estado de actualización)
USERDATA = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
# Directorio temporal para la base de datos descifrada, que se borrará al salir.
TEMP_DIR = xbmcvfs.translatePath(f"special://temp/{addon_id}")
DB_FILE = os.path.join(TEMP_DIR, 'session.db') # Usamos un nombre genérico
BIN_FILE_LOCAL = os.path.join(TEMP_DIR, '.sys_buffer.tmp') # Archivo encriptado, oculto y en carpeta temporal

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS items (
  "key" TEXT PRIMARY KEY,
  title TEXT, type TEXT, year TEXT, season TEXT, episode TEXT,
  tmdb_id TEXT, poster TEXT, fanart TEXT, overview TEXT,
  episode_title TEXT, episode_overview TEXT, still_path TEXT,
  clearlogo TEXT, banner TEXT, clearart TEXT, genres TEXT,
  "cast" TEXT, torrents TEXT, date_added TEXT, enriched INTEGER DEFAULT 0,
  collection_name TEXT, collection_poster TEXT, collection_fanart TEXT,
  is_anime INTEGER DEFAULT 0, is_cartoon INTEGER DEFAULT 0, is_documentary INTEGER DEFAULT 0, is_retro INTEGER DEFAULT 0, is_premium INTEGER DEFAULT 0, last_year TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
CREATE INDEX IF NOT EXISTS idx_items_year ON items(year);
CREATE INDEX IF NOT EXISTS idx_items_collection ON items(collection_name);
CREATE INDEX IF NOT EXISTS idx_items_date ON items(date_added);
CREATE INDEX IF NOT EXISTS idx_type_date ON items(type, date_added DESC);
CREATE INDEX IF NOT EXISTS idx_type_title ON items(type, title ASC);
CREATE INDEX IF NOT EXISTS idx_items_title_nocase ON items(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_items_flags ON items(is_anime, is_cartoon, is_documentary, is_retro, is_premium);
'''

def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA read_uncommitted = 1;")
        # Optimizaciones extremas para Android TV / Fire Stick
        conn.execute("PRAGMA journal_mode = OFF;") # Apaga escrituras temporales en disco
        conn.execute("PRAGMA synchronous = 0;")    # Evita esperar a que el disco responda
        conn.execute("PRAGMA cache_size = -2000;") # Limita la caché en RAM estricto a 2MB
        conn.execute("PRAGMA mmap_size = 0;")      # Ahorra RAM desactivando mapeo de memoria
    except Exception:
        pass
    return conn

def _upgrade_db_schema(db_path):
    """Se asegura de que las columnas e índices de alto rendimiento existan."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try: conn.execute("ALTER TABLE items ADD COLUMN collection_name TEXT")
        except Exception: pass
        try: conn.execute("ALTER TABLE items ADD COLUMN collection_poster TEXT")
        except Exception: pass
        try: conn.execute("ALTER TABLE items ADD COLUMN collection_fanart TEXT")
        except Exception: pass
        
        try: conn.execute("CREATE INDEX IF NOT EXISTS idx_items_date ON items(date_added)")
        except Exception: pass
        try: conn.execute("CREATE INDEX IF NOT EXISTS idx_type_date ON items(type, date_added DESC)")
        except Exception: pass
        try: conn.execute("CREATE INDEX IF NOT EXISTS idx_type_title ON items(type, title ASC)")
        except Exception: pass
        try: conn.execute("CREATE INDEX IF NOT EXISTS idx_items_title_nocase ON items(title COLLATE NOCASE)")
        except Exception: pass
        
        # Auto-reparador de Colecciones (Fusiona el estilo Moria con el estilo TMDB)
        try: conn.execute("UPDATE items SET collection_name = REPLACE(collection_name, ' (Colección)', ' - Colección') WHERE collection_name LIKE '% (Colección)'")
        except Exception: pass
        try: conn.execute("UPDATE items SET collection_name = REPLACE(collection_name, ' Colección', ' - Colección') WHERE collection_name LIKE '% Colección' AND collection_name NOT LIKE '% - Colección'")
        except Exception: pass

        # Migración Ligera: Solo creamos las columnas si no existen para evitar que las queries fallen.
        # Los datos reales (1 y 0) ya vendrán procesados desde el NAS para no saturar Kodi.
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN is_anime INTEGER DEFAULT 0")
        except Exception: pass
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN is_cartoon INTEGER DEFAULT 0")
        except Exception: pass
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN is_documentary INTEGER DEFAULT 0")
        except Exception: pass
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN is_premium INTEGER DEFAULT 0")
        except Exception: pass
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN is_retro INTEGER DEFAULT 0")
        except Exception: pass
        try: 
            conn.execute("ALTER TABLE items ADD COLUMN last_year TEXT")
        except Exception: pass
        try: 
            conn.execute("UPDATE items SET last_year = year WHERE last_year IS NULL OR last_year = ''")
        except Exception: pass

        conn.commit()
        conn.close()
    except Exception: pass

def _row_to_item(r):
    """Helper unificado para parsear filas SQLite a diccionarios."""
    try: season_val = int(r[4]) if r[4] else None
    except: season_val = None
    try: episode_val = int(r[5]) if r[5] else None
    except: episode_val = None
    return {
        'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3], 'season': season_val, 'episode': episode_val, 
        'tmdb_id': r[6], 'poster': r[7], 'fanart': r[8], 'overview': r[9], 'episode_title': r[10], 
        'episode_overview': r[11], 'still_path': r[12], 'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
        'genres': json.loads(r[16]) if r[16] else [], 'cast': json.loads(r[17]) if r[17] else [],
        'torrents': json.loads(r[18]) if r[18] else [], 'date_added': r[19], 'enriched': bool(r[20]),
        'collection_name': r[21] if len(r)>21 else None,
        'collection_poster': r[22] if len(r)>22 else None,
        'collection_fanart': r[23] if len(r)>23 else None
    }

def _decrypt_local_bin():
    import zlib, sys
    _new_k = [69, 49, 121, 95, 107, 71, 57, 75, 49, 118, 50, 76, 95, 122, 78, 113, 81, 79, 113, 82, 52, 103, 57, 90, 45, 50, 120, 88, 56, 106, 84, 49, 107, 95, 79, 55, 121, 68, 50, 109, 80, 113, 119, 61]
    encryption_key = bytes(_new_k)
    key_len = len(encryption_key)
    CHUNK_SIZE = 1056000

    try:
        tmp_db = DB_FILE + ".tmp"
        decompressor = zlib.decompressobj()
        
        with open(BIN_FILE_LOCAL, 'rb') as f_in, open(tmp_db, 'wb') as f_out:
            while True:
                chunk = bytearray(f_in.read(CHUNK_SIZE))
                if not chunk:
                    break
                for i in range(len(chunk)):
                    chunk[i] ^= encryption_key[i % key_len]
                    
                decompressed_chunk = decompressor.decompress(chunk)
                if decompressed_chunk:
                    f_out.write(decompressed_chunk)
            
            remaining = decompressor.flush()
            if remaining:
                f_out.write(remaining)
                
        # Forzar al Garbage Collector de Python a liberar toda la RAM usada por Zlib inmediatamente
        del decompressor
        import gc
        gc.collect()
            
        replaced = False
        for _ in range(10):
            try:
                os.replace(tmp_db, DB_FILE)
                replaced = True
                break
            except Exception:
                xbmc.sleep(500)
                
        if not replaced:
            if not _is_db_valid():
                try:
                    os.remove(DB_FILE)
                    os.replace(tmp_db, DB_FILE)
                    replaced = True
                except Exception: pass
        if os.path.exists(tmp_db): 
            try: os.remove(tmp_db)
            except: pass
            
        # Asegurar que el esquema local está al día tras extraerlo de .bin
        _upgrade_db_schema(DB_FILE)
        return replaced or _is_db_valid()
    except Exception as e:
        xbmc.log(f"RusterWolf: Error decrypting local bin: {e}", xbmc.LOGERROR)
        return False

def _is_db_valid():
    """Comprueba de forma ultra-rápida si la DB existe y no está corrupta."""
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) < 100 * 1024:
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT is_premium FROM items LIMIT 1")
        cur.execute("SELECT count(*) FROM items")
        cur.execute("PRAGMA quick_check(1)")
        res = cur.fetchone()
        conn.close()
        return res and res[0] == "ok"
    except Exception:
        return False

def ensure_session_db():
    """Asegura que la DB en memoria temporal exista y sea VÁLIDA."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if not _is_db_valid():
        if os.path.exists(BIN_FILE_LOCAL):
            _decrypt_local_bin()
            
            # Si tras la extracción sigue corrupta, el .bin original está dañado
            if not _is_db_valid():
                try: os.remove(BIN_FILE_LOCAL)
                except: pass
                try: os.remove(os.path.join(USERDATA, 'etag.txt'))
                except: pass
                try: os.remove(DB_FILE)
                except: pass
            else:
                _upgrade_db_schema(DB_FILE)
        else:
            try: os.remove(os.path.join(USERDATA, 'etag.txt'))
            except: pass
            try: os.remove(DB_FILE)
            except: pass

def maybe_update_db_from_remote(force=False):
    """Descarga el archivo .bin encriptado de Cloudflare R2 y actualiza la BD local."""
    import time
    import xbmcgui
    import urllib.request
    import urllib.error
    
    last_update_file = os.path.join(USERDATA, 'last_update.txt')
    etag_file = os.path.join(USERDATA, 'etag.txt')
    lock_file = os.path.join(TEMP_DIR, '.download.lock')
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(USERDATA, exist_ok=True)
    
    # Bloqueo anti-colisiones: Si cargan múltiples widgets a la vez y la DB no existe,
    # evitamos que todos intenten descargarla al mismo tiempo.
    if not force and os.path.exists(lock_file):
        for _ in range(40): # Esperar hasta 20 segundos
            if not os.path.exists(lock_file):
                break
            xbmc.sleep(500)
        ensure_session_db()
        return _is_db_valid()

    # 1. Recuperar la BD a la memoria temporal si no existe
    ensure_session_db()
    
    # Cooldown: 5 mins si la DB está bien, o 1 minuto si está rota (evita congelar Kodi repetidamente si no hay internet)
    db_is_ready = _is_db_valid()
    if not force and os.path.exists(last_update_file):
        try:
            with open(last_update_file, 'r') as f:
                elapsed = time.time() - float(f.read().strip())
                if db_is_ready and elapsed < 300:
                    return False
                elif not db_is_ready and elapsed < 60:
                    return False
        except Exception:
            pass
            
    # Añadir timestamp para evitar la agresiva caché de Cloudflare R2
    url_r2 = f"https://pub-80ab14db311c4254ade7bac002c3ef53.r2.dev/archivos.bin?t={int(time.time())}"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # Si tenemos ETag, usar If-None-Match para ahorrar datos si la nube no ha cambiado
    if os.path.exists(BIN_FILE_LOCAL) and os.path.exists(etag_file) and not force:
        try:
            with open(etag_file, 'r') as f:
                etag = f.read().strip()
            if etag:
                headers['If-None-Match'] = etag
        except Exception:
            pass
            
    xbmc.log(f"RusterWolf: Buscando actualización en R2...", xbmc.LOGINFO)
    
    dp = None
    if force:
        dp = xbmcgui.DialogProgress()
        dp.create("RusterWolf", "Descargando catálogo desde la nube...")
    else:
        xbmcgui.Dialog().notification("RusterWolf", "Buscando actualizaciones...", ADDON_ICON, 2000)
        
    try:
        # Activar bloqueo de hilo para widgets concurrentes
        with open(lock_file, 'w') as f: f.write('1')

        req = urllib.request.Request(url_r2, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            new_etag = response.headers.get('ETag')
            
            import shutil
            # Descarga en streaming directa a disco para evitar cuelgues (OOM) en Android
            with open(BIN_FILE_LOCAL, 'wb') as f:
                shutil.copyfileobj(response, f, length=1024*1024)
                
        if os.path.exists(BIN_FILE_LOCAL) and os.path.getsize(BIN_FILE_LOCAL) > 1024:
            if dp: dp.update(50, "Guardando actualización...")
            
            # 2. Desencriptarlo hacia la memoria temporal para esta sesión
            if not _decrypt_local_bin() or not _is_db_valid():
                if dp: dp.close()
                # Borrar el binario corrupto que acabamos de descargar para forzar intento nuevo después
                try: os.remove(BIN_FILE_LOCAL)
                except: pass
                if force: xbmcgui.Dialog().ok("RusterWolf - Error", "El catálogo descargado está corrupto. Inténtalo de nuevo.")
                return False
                    
            _upgrade_db_schema(DB_FILE)
                
            # Guardar el ETag para futuras comprobaciones ultrarrápidas
            if new_etag:
                with open(etag_file, 'w') as f:
                    f.write(new_etag)

            # Registrar el momento exacto de la actualización exitosa
            with open(last_update_file, 'w') as f:
                f.write(str(time.time()))
                
            xbmc.log(f"RusterWolf: Base de datos actualizada con éxito desde R2.", xbmc.LOGINFO)
            xbmcgui.Dialog().notification("RusterWolf", "Catálogo actualizado", ADDON_ICON, 3000)
            if dp: dp.close()
            return True
        else:
            if dp: dp.close()
            if force:
                xbmcgui.Dialog().ok("RusterWolf", "El archivo descargado está vacío o corrupto.")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            xbmc.log("RusterWolf: Catálogo en R2 no ha sido modificado (HTTP 304).", xbmc.LOGINFO)
            # Renovamos el tiempo de espera a 5 minutos en silencio
            with open(last_update_file, 'w') as f:
                f.write(str(time.time()))
            if dp: dp.close()
            return False
        else:
            if dp: dp.close()
            xbmc.log(f"RusterWolf: Error HTTP actualizando DB desde R2: {e}", xbmc.LOGERROR)
            with open(last_update_file, 'w') as f:
                f.write(str(time.time()))
            if force:
                xbmcgui.Dialog().ok("RusterWolf - Error", f"Fallo al actualizar:\n{str(e)}")
    except Exception as e:
        if dp: dp.close()
        xbmc.log(f"RusterWolf: Error actualizando DB desde R2: {e}", xbmc.LOGERROR)
        with open(last_update_file, 'w') as f:
            f.write(str(time.time()))
        if force:
            xbmcgui.Dialog().ok("RusterWolf - Error", f"Fallo al actualizar:\n{str(e)}")
    finally:
        # Liberar siempre el archivo de bloqueo aunque haya un error
        if os.path.exists(lock_file):
            try: os.remove(lock_file)
            except: pass
    return False

def init_db():
    os.makedirs(USERDATA, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    conn = _connect()
    try:
        c = conn.cursor()
        c.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    _upgrade_db_schema(DB_FILE)

def load_all_items():
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items')
        rows = c.fetchall()
        return [_row_to_item(r) for r in rows]
    finally:
        conn.close()

def load_items_by_keys(keys):
    """Carga items específicos por su ID de manera óptima (soporta miles de items)."""
    if not keys or not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        items = []
        # SQLite limita a 999 parámetros en IN(), procesamos en lotes de 900
        for i in range(0, len(keys), 900):
            batch = keys[i:i+900]
            placeholders = ','.join('?' for _ in batch)
            c.execute(f'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE "key" IN ({placeholders})', batch)
            for r in c.fetchall():
                items.append(_row_to_item(r))
        return items
    finally:
        conn.close()
        
def _apply_genre_filters(query, args, filter_type, genre, is_premium_req=False, check_premium=True):
    """Helper centralizado para aplicar los filtros complejos de género (Anime, Dibujos, Retro) de forma unificada."""
    if check_premium:
        if is_premium_req: query += " AND is_premium = 1"
        else: query += " AND is_premium = 0"

    if genre and genre.lower() != 'premium':
        for g in genre.split('|'):
            if g == 'Retro': query += " AND is_retro = 1"
            elif g == 'Dibujo': query += " AND is_cartoon = 1"
            elif g == 'Anime': query += " AND is_anime = 1"
            else:
                query += " AND genres LIKE ?"
                args.append(f'%{g}%')
        
    ISOLATED_GENRES = ['Documental', 'Dibujo', 'Anime', 'Retro']
    is_special = False
    if filter_type in ('documentary', 'series_documentary'): is_special = True
    if genre and any(ig.lower() in genre.lower() for ig in ISOLATED_GENRES): is_special = True
        
    if not is_special:
        query += " AND is_retro = 0 AND is_cartoon = 0 AND is_anime = 0 AND is_documentary = 0"
        
    return query, args

def get_filtered_items(filter_type=None, is_premium_req=False, genre=None, year=None, quality=None, letter=None, collection=None, sort_by='title', limit=None, offset=None):
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        query = 'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE 1=1'
        args = []

        ft = filter_type.strip().lower() if filter_type else None

        if ft in ('movie', 'pelicula'): query += " AND type='movie'"
        elif ft in ('tv', 'series', 'serie'): query += " AND type='tv'"
        elif ft == 'documentary':
            query += " AND type='movie' AND is_documentary = 1"
        elif ft == 'series_documentary':
            query += " AND type='tv' AND is_documentary = 1"

        query, args = _apply_genre_filters(query, args, ft, genre, is_premium_req=is_premium_req, check_premium=not collection)


        if year:
            query += " AND year = ?"
            args.append(str(year))

        if quality:
            qf = quality.strip().lower()
            if qf == '4k': query += " AND (torrents LIKE '%4k%' OR torrents LIKE '%2160p%')"
            else:
                query += " AND torrents LIKE ?"
                args.append(f'%{quality}%')

        if letter:
            query += " AND title LIKE ?"
            args.append(f"{letter}%")
            
        if collection:
            query += " AND collection_name = ?"
            args.append(collection)

        import datetime
        current_year = datetime.datetime.now().year
        RECENT_YEAR_THRESHOLD = current_year - 1

        if sort_by == 'novedades':
            query += f" AND CAST(SUBSTR(last_year, 1, 4) AS INTEGER) >= {RECENT_YEAR_THRESHOLD}"
        elif sort_by == 'date_added':
            query += f" AND (last_year IS NULL OR last_year = '' OR CAST(SUBSTR(last_year, 1, 4) AS INTEGER) < {RECENT_YEAR_THRESHOLD})"
            
        # EL GROUP BY DEBE IR SIEMPRE DESPUÉS DE LOS FILTROS 'WHERE/AND'
        if ft in ('tv', 'series', 'serie', 'series_documentary'):
            query += " GROUP BY title"

        if sort_by == 'novedades':
            if ft in ('tv', 'series', 'serie', 'series_documentary'): query += " ORDER BY MAX(REPLACE(date_added, 'T', ' ')) DESC"
            else: query += " ORDER BY REPLACE(date_added, 'T', ' ') DESC"
        elif sort_by == 'date_added':
            if ft in ('tv', 'series', 'serie', 'series_documentary'): query += " ORDER BY MAX(REPLACE(date_added, 'T', ' ')) DESC"
            else: query += " ORDER BY REPLACE(date_added, 'T', ' ') DESC"
        else:
            query += " ORDER BY title ASC"

        if limit:
            query += f" LIMIT {int(limit)}"
            if offset: query += f" OFFSET {int(offset)}"

        c.execute(query, args)
        rows = c.fetchall()
        return [_row_to_item(r) for r in rows]
    finally:
        conn.close()

def get_years(filter_type=None, genre=None):
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        query = "SELECT DISTINCT year FROM items WHERE year IS NOT NULL AND year != ''"
        args = []
        if filter_type: 
            ft = filter_type.strip().lower()
            if ft in ('movie', 'pelicula'): query += " AND type='movie'"
            elif ft in ('tv', 'series', 'serie'): query += " AND type='tv'"
            elif ft == 'documentary': query += " AND type='movie' AND is_documentary = 1"
            elif ft == 'series_documentary': query += " AND type='tv' AND is_documentary = 1"
            
        query, args = _apply_genre_filters(query, args, filter_type, genre, check_premium=False)
        
        query += " ORDER BY year DESC"
        c.execute(query, args)
        return [r[0] for r in c.fetchall() if r[0] and str(r[0]).isdigit()]
    finally:
        conn.close()

def get_letters(filter_type=None, genre=None):
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        query = "SELECT DISTINCT UPPER(SUBSTR(title, 1, 1)) FROM items WHERE title IS NOT NULL AND title != ''"
        args = []
        if filter_type: 
            ft = filter_type.strip().lower()
            if ft in ('movie', 'pelicula'): query += " AND type='movie'"
            elif ft in ('tv', 'series', 'serie'): query += " AND type='tv'"
            elif ft == 'documentary': query += " AND type='movie' AND is_documentary = 1"
            elif ft == 'series_documentary': query += " AND type='tv' AND is_documentary = 1"
            
        query, args = _apply_genre_filters(query, args, filter_type, genre, check_premium=False)
        
        query += " ORDER BY 1"
        c.execute(query, args)
        return [r[0] for r in c.fetchall() if r[0].isalpha()]
    finally:
        conn.close()

def get_collections_paginated(filter_type=None, limit=25, offset=0, genre=None, is_premium_req=False):
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        query = "SELECT collection_name, MAX(collection_poster), MAX(collection_fanart), MAX(clearlogo) FROM items WHERE collection_name IS NOT NULL AND collection_name != '' AND UPPER(collection_name) != 'NONE'"
        args = []
        if filter_type: 
            ft = filter_type.strip().lower()
            if ft in ('movie', 'pelicula'): query += " AND type='movie'"
            elif ft in ('tv', 'series', 'serie'): query += " AND type='tv'"
            elif ft == 'documentary': query += " AND type='movie' AND is_documentary = 1"
            elif ft == 'series_documentary': query += " AND type='tv' AND is_documentary = 1"
            
        query, args = _apply_genre_filters(query, args, filter_type, genre, is_premium_req=is_premium_req, check_premium=True)
                
        query += " GROUP BY collection_name COLLATE NOCASE ORDER BY collection_name ASC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        c.execute(query, args)
        return [{"name": r[0], "poster": r[1], "fanart": r[2], "clearlogo": r[3]} for r in c.fetchall()]
    finally:
        conn.close()

def get_series_representative(title):
    if not os.path.exists(DB_FILE) or not title: return None
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE type IN ("tv", "series_documentary") AND title=? ORDER BY (poster IS NOT NULL AND poster != "") DESC, date_added DESC LIMIT 1', (title,))
        r = c.fetchone()
        if r: return _row_to_item(r)
    finally:
        conn.close()
    return None

def count_episodes_for_series(title):
    if not os.path.exists(DB_FILE) or not title: return 0
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM items WHERE type IN ("tv", "series_documentary") AND title=?', (title,))
        return c.fetchone()[0]
    finally:
        conn.close()

def get_series_episode_keys(series_title):
    if not os.path.exists(DB_FILE) or not series_title: return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key" FROM items WHERE type IN ("tv", "series_documentary") AND title=?', (series_title,))
        return [r[0] for r in c.fetchall()]
    finally:
        conn.close()

def get_series_episodes(series_title):
    if not os.path.exists(DB_FILE) or not series_title: return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE type IN ("tv", "series_documentary") AND title=?', (series_title,))
        rows = c.fetchall()
        return [_row_to_item(r) for r in rows]
    finally:
        conn.close()
  

def search_items_sql(query_str, limit=100):
    if not os.path.exists(DB_FILE) or not query_str: return []
    conn = _connect()
    try:
        c = conn.cursor()
        
        query_str = query_str.strip()
        
        # 1. Búsqueda Exacta
        exact_match = query_str
        exact_like = f"%{query_str}%"
        exact_start = f"{query_str}%"
        
        # 2. Búsqueda Limpia (sin guiones ni espacios, para unir "spider-man" y "spiderman")
        query_clean = query_str.replace('-', '').replace(' ', '')
        clean_match = query_clean
        clean_like = f"%{query_clean}%"
        clean_start = f"{query_clean}%"
        
        # 3. Búsqueda por Palabras (Ignora dobles espacios)
        words = query_str.replace('-', ' ').split()
        if len(words) > 1:
            words_like = "%" + "%".join(words) + "%"
        else:
            words_like = exact_like
            
        # 4. Artículos (Ignorar "El", "La", "The", etc. para priorizar bien)
        articles = ['El ', 'La ', 'Los ', 'Las ', 'Un ', 'Una ', 'The ', 'A ', 'An ']
        art_exacts = [f"{art}{query_str}" for art in articles]
        art_starts = [f"{art}{query_str}%" for art in articles]
            
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart 
            FROM items 
            WHERE title LIKE ? OR episode_title LIKE ? 
               OR title LIKE ? OR episode_title LIKE ?
               OR REPLACE(REPLACE(title, '-', ''), ' ', '') LIKE ?
            ORDER BY 
               CASE 
                    -- Prioridad -1: Coincidencia EXACTA del título (con o sin artículos/guiones)
                    WHEN title LIKE ? THEN -1
                    WHEN title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? THEN -1
                    WHEN REPLACE(REPLACE(title, '-', ''), ' ', '') LIKE ? THEN -1
                    
                    -- Prioridad 0: Empieza por la búsqueda (con o sin artículos/guiones)
                    WHEN title LIKE ? THEN 0
                    WHEN title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? OR title LIKE ? THEN 0
                    WHEN REPLACE(REPLACE(title, '-', ''), ' ', '') LIKE ? THEN 0
                    
                    -- Prioridad 1: Contiene la búsqueda
                    WHEN title LIKE ? THEN 1
                    WHEN REPLACE(REPLACE(title, '-', ''), ' ', '') LIKE ? THEN 1
                    
                    -- Prioridad 2: Coincide en el título del episodio
                    WHEN episode_title LIKE ? THEN 2
                    ELSE 3 
               END,
               year DESC
            LIMIT ?
        ''', (
            # WHERE
            exact_like, exact_like, words_like, words_like, clean_like,
            
            # ORDER BY -1 (Exacta)
            exact_match, *art_exacts, clean_match,
            
            # ORDER BY 0 (Empieza por)
            exact_start, *art_starts, clean_start,
            
            # ORDER BY 1 (Contiene)
            exact_like, clean_like,
            
            # ORDER BY 2 (Episodio)
            exact_like,
            
            # LIMIT
            limit
        ))
        rows = c.fetchall()
        return [_row_to_item(r) for r in rows]
    finally:
        conn.close()


def get_next_episode(tvshowtitle, season, episode):
    if not os.path.exists(DB_FILE) or not tvshowtitle: return None
    conn = _connect()
    try:
        c = conn.cursor()
        # 1. Buscar el siguiente episodio en la misma temporada
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart 
            FROM items 
            WHERE type='tv' AND title LIKE ? AND season=? AND CAST(episode AS INTEGER) = ?
        ''', (tvshowtitle, str(season), int(episode) + 1))
        r = c.fetchone()
        
        # 2. Si no existe, probar a buscar el episodio 1 de la siguiente temporada
        if not r:
            c.execute('''
                SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                       episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                       genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart 
                FROM items 
                WHERE type='tv' AND title LIKE ? AND CAST(season AS INTEGER)=? AND CAST(episode AS INTEGER) = 1
            ''', (tvshowtitle, int(season) + 1))
            r = c.fetchone()
            
        if r:
            return _row_to_item(r)
    except Exception:
        pass
    finally:
        conn.close()
    return None
