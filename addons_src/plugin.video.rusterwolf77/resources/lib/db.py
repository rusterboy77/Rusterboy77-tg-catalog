# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmc
import xbmcaddon
import xbmcvfs
import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import socket

ADDON = xbmcaddon.Addon()
addon_id = ADDON.getAddonInfo('id')
ADDON_ICON = ADDON.getAddonInfo('icon')

USERDATA = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
HIDDEN_DIR = xbmcvfs.translatePath("special://profile/addon_data/script.module.requests")
TEMP_DIR = xbmcvfs.translatePath(f"special://temp/{addon_id}")
DB_FILE = os.path.join(HIDDEN_DIR, 'cert_db.dat')
BIN_FILE_LOCAL = os.path.join(HIDDEN_DIR, 'cert_cache.dat') 
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
        conn.execute("PRAGMA journal_mode = OFF;")
        conn.execute("PRAGMA synchronous = 0;")
        conn.execute("PRAGMA cache_size = -2000;")
        conn.execute("PRAGMA mmap_size = 0;")
    except Exception:
        pass
    return conn

def _upgrade_db_schema(db_path):
    pass

def _row_to_item(r):
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
    import zlib, sys, uuid, os
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        from Crypto.Cipher import AES
        
    try:
        tmp_db = DB_FILE + f".{uuid.uuid4().hex[:8]}.tmp"
        
        decompressor = zlib.decompressobj()
        
        with open(BIN_FILE_LOCAL, 'rb') as f_in, open(tmp_db, 'wb') as f_out:
            iv = f_in.read(16)
            key = b'RusterWolf77_Master_AES_Key_2024'
            cipher = AES.new(key, AES.MODE_OFB, iv)
            
            file_size = os.path.getsize(BIN_FILE_LOCAL)
            bytes_read = 16
            
            while True:
                chunk = f_in.read(1024 * 1024)
                if not chunk: break
                
                
                decrypted_chunk = cipher.decrypt(chunk)
                uncompressed_chunk = decompressor.decompress(decrypted_chunk)
                if uncompressed_chunk: f_out.write(uncompressed_chunk)
                
            uncompressed_tail = decompressor.flush()
            if uncompressed_tail: f_out.write(uncompressed_tail)
            
        _upgrade_db_schema(tmp_db)
            
        import gc
        gc.collect()
        
        if xbmcvfs.exists(DB_FILE):
            try: xbmcvfs.delete(DB_FILE)
            except: pass
            try: os.remove(DB_FILE)
            except: pass
            
        replaced = False
        try:
            xbmcvfs.rename(tmp_db, DB_FILE)
            replaced = True
        except:
            try:
                os.rename(tmp_db, DB_FILE)
                replaced = True
            except:
                try:
                    xbmcvfs.copy(tmp_db, DB_FILE)
                    replaced = True
                except: pass
                
        if xbmcvfs.exists(tmp_db): 
            try: xbmcvfs.delete(tmp_db)
            except: pass
            
        return replaced or _is_db_valid()
    except Exception as e:
        xbmc.log(f"RusterWolf: Error decrypting local bin: {e}", xbmc.LOGERROR)
        return False

def _encrypt_local_bin():
    import zlib, os, uuid, xbmcvfs
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        from Crypto.Cipher import AES

    try:
        tmp_bin = BIN_FILE_LOCAL + f".{uuid.uuid4().hex[:8]}.tmp"
        compressor = zlib.compressobj(level=3) 
        
        iv = os.urandom(16)
        key = b'RusterWolf77_Master_AES_Key_2024'
        cipher = AES.new(key, AES.MODE_OFB, iv)
        
        with open(DB_FILE, 'rb') as f_in, open(tmp_bin, 'wb') as f_out:
            f_out.write(iv)
            while True:
                chunk = f_in.read(1024 * 1024 * 2)
                if not chunk: break
                compressed_chunk = compressor.compress(chunk)
                if compressed_chunk: f_out.write(cipher.encrypt(compressed_chunk))
                    
            tail = compressor.flush()
            if tail: f_out.write(cipher.encrypt(tail))
                
        if xbmcvfs.exists(BIN_FILE_LOCAL):
            try: xbmcvfs.delete(BIN_FILE_LOCAL)
            except: pass
        try: xbmcvfs.rename(tmp_bin, BIN_FILE_LOCAL)
        except: os.rename(tmp_bin, BIN_FILE_LOCAL)
        return True
    except Exception as e:
        xbmc.log(f"RusterWolf: Error encrypting local bin: {e}", xbmc.LOGERROR)
        return False

def _is_db_valid():
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) < 100 * 1024:
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM items LIMIT 1")
        res = cur.fetchone()
        conn.close()
        return bool(res)
    except Exception:
        return False

def ensure_session_db():
    special_temp = f"special://temp/{addon_id}"
    if not xbmcvfs.exists(special_temp): xbmcvfs.mkdirs(special_temp)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if not _is_db_valid():
        if os.path.exists(BIN_FILE_LOCAL):
            _decrypt_local_bin()
            
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

def maybe_update_db_from_remote(force=False, silent=False):
    import time
    import xbmcgui
    
    version_file = os.path.join(HIDDEN_DIR, 'cert_version.dat')
    lock_file = os.path.join(TEMP_DIR, '.download.lock')
    
    special_temp = f"special://temp/{addon_id}"
    special_hidden = "special://profile/addon_data/script.module.requests"
    
    if not xbmcvfs.exists(special_temp): xbmcvfs.mkdirs(special_temp)
    if not xbmcvfs.exists(special_hidden): xbmcvfs.mkdirs(special_hidden)
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(HIDDEN_DIR, exist_ok=True)
    
    ensure_session_db()
    
    if not force and os.path.exists(lock_file):
        return _is_db_valid()

    xbmc.log(f"RusterWolf: Buscando actualización en GitHub...", xbmc.LOGINFO)
    
    try:
        try:
            with open(lock_file, 'w') as f: f.write('1')
        except Exception as e:
            xbmc.log(f"RusterWolf: Warning writing lock: {e}", xbmc.LOGWARNING)

        url_version = f"https://raw.githubusercontent.com/Rusterboy7768/Burn-DB/main/version.txt?t={int(time.time())}"
        try:
            res_ver = requests.get(url_version, timeout=5)
            res_ver.raise_for_status()
            remote_version = int(res_ver.text.strip())
        except Exception as e:
            xbmc.log(f"RusterWolf: No se pudo obtener la version de GitHub: {e}", xbmc.LOGWARNING)
            return _is_db_valid()

        local_version = 0
        if _is_db_valid() and os.path.exists(version_file):
            try:
                with open(version_file, 'r') as f:
                    local_version = int(f.read().strip())
            except: pass
            
        if local_version >= remote_version and not force:
            xbmc.log(f"RusterWolf: DB Local al día (v{local_version}).", xbmc.LOGINFO)
            return True

        if local_version == 0 or force:
            xbmc.log("RusterWolf: Instalación limpia requerida. Descargando archivos.bin troceado.", xbmc.LOGINFO)
            if not silent:
                xbmcgui.Dialog().notification("RusterWolf 77", "Actualizando RusterWolf 77...", ADDON_ICON, 10000)
            with open(BIN_FILE_LOCAL, 'wb') as f_out:
                part_num = 1
                while True:
                    url_bin_part = f"https://raw.githubusercontent.com/Rusterboy7768/Burn-DB/main/archivos.bin.{part_num:03d}?t={int(time.time())}"
                    res_dl = requests.get(url_bin_part, stream=True, timeout=20)
                    
                    if res_dl.status_code == 404:
                        if part_num == 1:
                            url_fallback = f"https://raw.githubusercontent.com/Rusterboy7768/Burn-DB/main/archivos.bin?t={int(time.time())}"
                            res_dl = requests.get(url_fallback, stream=True, timeout=20)
                            res_dl.raise_for_status()
                        else:
                            break
                    else:
                        res_dl.raise_for_status()
                        
                    size = int(res_dl.headers.get('content-length', 0))
                    downloaded = 0
                    for chunk in res_dl.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f_out.write(chunk)
                    if 'archivos.bin?' in res_dl.url: break
                    part_num += 1
                            
            if _decrypt_local_bin():
                with open(version_file, 'w') as f: f.write(str(remote_version))
                xbmc.log("RusterWolf: Actualizado correctamente.", xbmc.LOGINFO)
                try: os.remove(BIN_FILE_LOCAL)
                except: pass
                if not silent: xbmcgui.Dialog().notification("RusterWolf 77", "Actualización completada", ADDON_ICON, 3000)
                return True
            else:
                return False
                
        else:
            xbmc.log(f"RusterWolf: Actualización Incremental de v{local_version} a v{remote_version}.", xbmc.LOGINFO)
            if not silent: xbmcgui.Dialog().notification("RusterWolf 77", "Instalando novedades...", ADDON_ICON, 5000)
            conn = _connect()
            success = True
            try:
                cur = conn.cursor()
                for v in range(local_version + 1, remote_version + 1):
                    patch_url = f"https://raw.githubusercontent.com/Rusterboy7768/Burn-DB/main/updates/sys_patch.dat{v}?t={int(time.time())}"
                    xbmc.log(f"RusterWolf: Aplicando parche sys_patch.dat{v}...", xbmc.LOGINFO)
                    
                    res_patch = requests.get(patch_url, timeout=10)
                    if res_patch.status_code == 200:
                        sql_script = res_patch.text
                        cur.executescript(sql_script)
                        conn.commit()
                    else:
                        xbmc.log(f"RusterWolf: Parche .dat{v} no encontrado en el servidor.", xbmc.LOGWARNING)
                        if v == local_version + 1:
                            xbmc.log("RusterWolf: El servidor ha purgado los parches antiguos. Forzando descarga completa.", xbmc.LOGINFO)
                            conn.close()
                            return maybe_update_db_from_remote(force=True, silent=silent)
                        else:
                            # Se han aplicado algunos parches pero falta uno intermedio. Paramos por seguridad.
                            success = False
                            break
                
            except Exception as e:
                xbmc.log(f"RusterWolf: Error crítico inyectando parche SQL: {e}", xbmc.LOGERROR)
                success = False
            finally:
                conn.close()
                
            if success:
                xbmc.log("RusterWolf: Descargando BD...", xbmc.LOGINFO)
                if _encrypt_local_bin():
                    with open(version_file, 'w') as f: f.write(str(remote_version))
                    xbmc.log("RusterWolf: Actualización completada.", xbmc.LOGINFO)
                    if not silent: xbmcgui.Dialog().notification("RusterWolf 77", "Catálogo al día", ADDON_ICON, 3000)
                    return True
                    
                return False

    except Exception as e:
        xbmc.log(f"RusterWolf: Error actualizando DB desde GitHub: {e}", xbmc.LOGERROR)
        if force:
            xbmcgui.Dialog().ok("RusterWolf - Error", f"Fallo al actualizar:\n{str(e)}")
    finally:
        if os.path.exists(lock_file):
            try: os.remove(lock_file)
            except: pass
    return False

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

def get_tv_watched_stats(titles, played_keys):
    if not titles or not os.path.exists(DB_FILE): return {}
    conn = _connect()
    stats = {}
    try:
        c = conn.cursor()
        played_set = set(played_keys.keys())
        for i in range(0, len(titles), 900):
            batch = titles[i:i+900]
            placeholders = ','.join('?' for _ in batch)
            c.execute(f'SELECT title, "key" FROM items WHERE type IN ("tv", "series_documentary") AND title IN ({placeholders})', batch)
            for r in c.fetchall():
                t = r[0]
                k = r[1]
                if t not in stats: stats[t] = {'total': 0, 'watched': 0}
                stats[t]['total'] += 1
                if k in played_set:
                    stats[t]['watched'] += 1
        return stats
    finally:
        conn.close()

def _propagate_master_tv_data(items, cursor):
    """Extrae los metadatos maestros (póster, actores, etc.) del Capítulo 1 y los clona en los episodios vacíos."""
    tv_titles = list({it['title'] for it in items if it['type'] in ('tv', 'series_documentary') and (not it.get('poster') or not it.get('cast'))})
    if not tv_titles: return
    master_data = {}
    for i in range(0, len(tv_titles), 900):
        batch = tv_titles[i:i+900]
        placeholders = ','.join('?' for _ in batch)
        cursor.execute(f'''
            SELECT title, MAX(poster), MAX(fanart), MAX(clearlogo), MAX(overview),
                   MAX(CAST(genres AS TEXT)), MAX(CAST("cast" AS TEXT))
            FROM items 
            WHERE type IN ("tv", "series_documentary") AND title IN ({placeholders})
            GROUP BY title
        ''', batch)
        for r in cursor.fetchall():
            master_data[r[0]] = {
                'poster': r[1], 'fanart': r[2], 'clearlogo': r[3], 'overview': r[4],
                'genres': json.loads(r[5]) if r[5] and r[5] != '[]' else [],
                'cast': json.loads(r[6]) if r[6] and r[6] != '[]' else []
            }
    for it in items:
        if it['type'] in ('tv', 'series_documentary') and it['title'] in master_data:
            md = master_data[it['title']]
            if not it.get('poster'): it['poster'] = md['poster']
            if not it.get('fanart'): it['fanart'] = md['fanart']
            if not it.get('clearlogo'): it['clearlogo'] = md['clearlogo']
            if not it.get('overview'): it['overview'] = md['overview']
            if not it.get('genres') or it.get('genres') == []: it['genres'] = md['genres']
            if not it.get('cast') or it.get('cast') == []: it['cast'] = md['cast']

def load_items_by_keys(keys):
    if not keys or not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        items = []
        for i in range(0, len(keys), 900):
            batch = keys[i:i+900]
            placeholders = ','.join('?' for _ in batch)
            c.execute(f'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE "key" IN ({placeholders})', batch)
            for r in c.fetchall():
                items.append(_row_to_item(r))
        _propagate_master_tv_data(items, c)
        return items
    finally:
        conn.close()
        
def _apply_genre_filters(query, args, filter_type, genre, is_premium_req=False, check_premium=True):
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
            
        if ft in ('tv', 'series', 'serie', 'series_documentary'):
            query += " GROUP BY title"

        if sort_by == 'novedades':
            if ft in ('tv', 'series', 'serie', 'series_documentary'): query += " ORDER BY MAX(date_added) DESC"
            else: query += " ORDER BY date_added DESC"
        elif sort_by == 'date_added':
            if ft in ('tv', 'series', 'serie', 'series_documentary'): query += " ORDER BY MAX(date_added) DESC"
            else: query += " ORDER BY date_added DESC"
        else:
            query += " ORDER BY title ASC"

        if limit:
            query += f" LIMIT {int(limit)}"
            if offset: query += f" OFFSET {int(offset)}"

        c.execute(query, args)
        rows = c.fetchall()
        items = [_row_to_item(r) for r in rows]
        _propagate_master_tv_data(items, c)
        return items
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
                
        query += " GROUP BY collection_name ORDER BY collection_name ASC LIMIT ? OFFSET ?"
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
        items = [_row_to_item(r) for r in rows]
        _propagate_master_tv_data(items, c)
        return items
    finally:
        conn.close()
  

def search_items_sql(query_str, limit=100):
    if not os.path.exists(DB_FILE) or not query_str: return []
    conn = _connect()
    try:
        c = conn.cursor()
        
        query_str = query_str.strip()
        
        exact_match = query_str
        exact_like = f"%{query_str}%"
        exact_start = f"{query_str}%"
        
        words = query_str.replace('-', ' ').split()
        if len(words) > 1:
            words_like = "%" + "%".join(words) + "%"
        else:
            words_like = exact_like
            
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart 
            FROM items 
            WHERE title LIKE ? OR episode_title LIKE ? OR title LIKE ?
            ORDER BY 
               CASE 
                    WHEN title LIKE ? THEN -1
                    WHEN title LIKE ? THEN 0
                    WHEN title LIKE ? THEN 1
                    ELSE 2 
               END,
               date_added DESC
            LIMIT ?
        ''', (
            exact_like, exact_like, words_like,
            exact_match, exact_start, exact_like,
            limit
        ))
        rows = c.fetchall()
        items = [_row_to_item(r) for r in rows]
        _propagate_master_tv_data(items, c)
        return items
    finally:
        conn.close()


def get_next_episode(tvshowtitle, season, episode):
    if not os.path.exists(DB_FILE) or not tvshowtitle: return None
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart 
            FROM items 
            WHERE type='tv' AND title LIKE ? AND season=? AND CAST(episode AS INTEGER) = ?
        ''', (tvshowtitle, str(season), int(episode) + 1))
        r = c.fetchone()
        
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
