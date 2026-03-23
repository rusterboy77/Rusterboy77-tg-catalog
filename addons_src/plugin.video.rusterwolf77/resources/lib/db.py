# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
addon_id = ADDON.getAddonInfo('id')
ADDON_ICON = ADDON.getAddonInfo('icon')
USERDATA = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
DB_FILE = os.path.join(USERDATA, 'cache.db')

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS items (
  "key" TEXT PRIMARY KEY,
  title TEXT, type TEXT, year TEXT, season TEXT, episode TEXT,
  tmdb_id TEXT, poster TEXT, fanart TEXT, overview TEXT,
  episode_title TEXT, episode_overview TEXT, still_path TEXT,
  clearlogo TEXT, banner TEXT, clearart TEXT, genres TEXT,
  "cast" TEXT, torrents TEXT, date_added TEXT, enriched INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
'''

def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA read_uncommitted = 1;")
    except Exception:
        pass
    return conn

def maybe_update_db_from_remote(force=False):
    """Descarga el archivo .bin encriptado de Cloudflare R2 y actualiza la BD local."""
    import time
    import xbmcgui
    import urllib.request
    import urllib.error
    import zlib
    import itertools
    
    last_update_file = os.path.join(USERDATA, 'last_update.txt')
    etag_file = os.path.join(USERDATA, 'etag.txt')
    
    # Cooldown de 5 minutos (300s) para no saturar al navegar rápido entre menús
    if not force and os.path.exists(last_update_file):
        try:
            with open(last_update_file, 'r') as f:
                if time.time() - float(f.read().strip()) < 300:
                    return False
        except Exception:
            pass
            
        
    os.makedirs(USERDATA, exist_ok=True)
    # Añadir timestamp para evitar la agresiva caché de Cloudflare R2
    url_r2 = f"https://pub-80ab14db311c4254ade7bac002c3ef53.r2.dev/archivos.bin?t={int(time.time())}"
    encryption_key = b'E1y_kG9K1v2L_zNqQOqR4g9Z-2xX8jT1k_O7yD2mPqw='
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # Si tenemos ETag, usar If-None-Match para ahorrar datos si la nube no ha cambiado
    if os.path.exists(DB_FILE) and os.path.exists(etag_file) and not force:
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
        
    try:
        req = urllib.request.Request(url_r2, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            encrypted_data = response.read()
            new_etag = response.headers.get('ETag')
            
        if len(encrypted_data) > 1024:
            if dp: dp.update(50, "Desencriptando base de datos...")
            try:
                decrypted_compressed = bytes(a ^ b for a, b in zip(encrypted_data, itertools.cycle(encryption_key)))
                decrypted_data = zlib.decompress(decrypted_compressed)
            except zlib.error:
                if dp: dp.close()
                xbmcgui.Dialog().ok("RusterWolf - Error", "El archivo en la nube tiene un formato antiguo.\n\nPor favor, ejecuta la tarea programada en tu NAS para subir la nueva base de datos y vuelve a intentarlo.")
                return False
            
            if dp: dp.update(80, "Aplicando cambios...")
            tmp_db = DB_FILE + ".tmp"
            with open(tmp_db, 'wb') as f:
                f.write(decrypted_data)
                
            # Bucle de reintentos para sortear el WinError 5 (archivo en uso por otro proceso de Kodi)
            replaced = False
            for _ in range(10):
                try:
                    os.replace(tmp_db, DB_FILE)
                    replaced = True
                    break
                except Exception:
                    xbmc.sleep(500) # Esperamos medio segundo si Kodi lo está leyendo
            
            if not replaced:
                # Fallback extremo: Sobrescribir los bytes directamente si el OS no nos deja renombrar
                try:
                    with open(DB_FILE, 'wb') as f:
                        f.write(decrypted_data)
                    if os.path.exists(tmp_db):
                        os.remove(tmp_db)
                except Exception as e:
                    xbmc.log(f"RusterWolf: Imposible aplicar actualización DB: {e}", xbmc.LOGERROR)
                    if dp: dp.close()
                    return False
                
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
            if force:
                xbmcgui.Dialog().ok("RusterWolf - Error", f"Fallo al actualizar:\n{str(e)}")
    except Exception as e:
        if dp: dp.close()
        xbmc.log(f"RusterWolf: Error actualizando DB desde R2: {e}", xbmc.LOGERROR)
        if force:
            xbmcgui.Dialog().ok("RusterWolf - Error", f"Fallo al actualizar:\n{str(e)}")
    return False

def init_db():
    os.makedirs(USERDATA, exist_ok=True)
    conn = _connect()
    try:
        c = conn.cursor()
        c.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()

def load_all_items():
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched FROM items')
        rows = c.fetchall()
        items = []
        for r in rows:
            try: season_val = int(r[4]) if r[4] else None
            except: season_val = None
            try: episode_val = int(r[5]) if r[5] else None
            except: episode_val = None
            
            items.append({
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3],
                'season': season_val, 'episode': episode_val, 'tmdb_id': r[6],
                'poster': r[7], 'fanart': r[8], 'overview': r[9],
                'episode_title': r[10], 'episode_overview': r[11], 'still_path': r[12],
                'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19], 'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()

def load_items_by_keys(keys):
    if not keys or not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        placeholders = ','.join('?' for _ in keys)
        c.execute(f'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched FROM items WHERE "key" IN ({placeholders})', keys)
        rows = c.fetchall()
        items = []
        for r in rows:
            items.append({
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3],
                'season': r[4], 'episode': r[5], 'tmdb_id': r[6],
                'poster': r[7], 'fanart': r[8], 'overview': r[9],
                'episode_title': r[10], 'episode_overview': r[11], 'still_path': r[12],
                'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19], 'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()
        

def get_filtered_items(filter_type=None, is_premium_req=False, genre=None, year=None, quality=None, letter=None, sort_by='title', limit=None, offset=None):
    if not os.path.exists(DB_FILE): return []
    conn = _connect()
    try:
        c = conn.cursor()
        query = 'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched FROM items WHERE 1=1'
        args = []

        if filter_type == 'movie': query += " AND type='movie'"
        elif filter_type == 'tv': query += " AND type='tv'"
        elif filter_type == 'documentary':
            query += " AND type='movie' AND genres LIKE '%Documental%'"
        elif filter_type == 'series_documentary':
            query += " AND type='tv' AND genres LIKE '%Documental%'"

        if is_premium_req: query += " AND genres LIKE '%Premium%'"
        else: query += " AND genres NOT LIKE '%Premium%'"

        if genre and genre.lower() != 'premium':
            query += " AND genres LIKE ?"
            args.append(f'%"{genre}"%')

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

        if filter_type in ('tv', 'series_documentary', 'movie', 'documentary'):
            query += " GROUP BY title"

        if sort_by == 'date_added':
            if filter_type in ('tv', 'series_documentary'): query += " ORDER BY MAX(date_added) DESC"
            else: query += " ORDER BY date_added DESC"
        else:
            query += " ORDER BY title ASC"

        if limit:
            query += f" LIMIT {int(limit)}"
            if offset: query += f" OFFSET {int(offset)}"

        c.execute(query, args)
        rows = c.fetchall()
        items = []
        for r in rows:
            try: season_val = int(r[4]) if r[4] else None
            except: season_val = None
            try: episode_val = int(r[5]) if r[5] else None
            except: episode_val = None
            items.append({
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3], 'season': season_val, 'episode': episode_val, 
                'tmdb_id': r[6], 'poster': r[7], 'fanart': r[8], 'overview': r[9], 'episode_title': r[10], 
                'episode_overview': r[11], 'still_path': r[12], 'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [], 'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [], 'date_added': r[19], 'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()

def get_series_episodes(series_title):
    if not os.path.exists(DB_FILE) or not series_title: return []
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute('SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched FROM items WHERE type IN ("tv", "series_documentary") AND title=?', (series_title,))
        rows = c.fetchall()
        items = []
        for r in rows:
            try: season_val = int(r[4]) if r[4] else None
            except: season_val = None
            try: episode_val = int(r[5]) if r[5] else None
            except: episode_val = None
            items.append({
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3], 'season': season_val, 'episode': episode_val, 
                'tmdb_id': r[6], 'poster': r[7], 'fanart': r[8], 'overview': r[9], 'episode_title': r[10], 
                'episode_overview': r[11], 'still_path': r[12], 'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [], 'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [], 'date_added': r[19], 'enriched': bool(r[20])
            })
        return items
    finally:
        conn.close()
  

def search_items_sql(query_str, limit=100):
    if not os.path.exists(DB_FILE) or not query_str: return []
    conn = _connect()
    try:
        c = conn.cursor()
        
        # 1. Búsqueda Exacta
        exact_like = f"%{query_str}%"
        # 2. Búsqueda por Palabras Sueltas (Ignora dobles espacios)
        words_like = "%" + "%".join(query_str.split()) + "%"
        # 3. Búsqueda Difusa Extrema (Faltan letras, ej. "plp fiction" -> "%p%l%p%f%i%c%t%i%o%n%")
        chars = [ch for ch in query_str if ch.isalnum()]
        fuzzy_like = "%" + "%".join(chars) + "%" if len(chars) >= 3 else words_like
        
        c.execute('''
            SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                   episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                   genres, "cast", torrents, date_added, enriched 
            FROM items 
            WHERE title LIKE ? OR episode_title LIKE ? 
               OR title LIKE ? OR episode_title LIKE ?
               OR title LIKE ? OR episode_title LIKE ?
            ORDER BY 
               CASE WHEN title LIKE ? OR episode_title LIKE ? THEN 0 
                    WHEN title LIKE ? OR episode_title LIKE ? THEN 1
                    ELSE 2 END
            LIMIT ?
        ''', (exact_like, exact_like, words_like, words_like, fuzzy_like, fuzzy_like, 
              exact_like, exact_like, words_like, words_like, limit))
        rows = c.fetchall()
        items = []
        for r in rows:
            items.append({
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3],
                'season': r[4], 'episode': r[5], 'tmdb_id': r[6],
                'poster': r[7], 'fanart': r[8], 'overview': r[9],
                'episode_title': r[10], 'episode_overview': r[11], 'still_path': r[12],
                'clearlogo': r[13], 'banner': r[14], 'clearart': r[15],
                'genres': json.loads(r[16]) if r[16] else [],
                'cast': json.loads(r[17]) if r[17] else [],
                'torrents': json.loads(r[18]) if r[18] else [],
                'date_added': r[19], 'enriched': bool(r[20])
            })
        return items
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
                   genres, "cast", torrents, date_added, enriched 
            FROM items 
            WHERE type='tv' AND title LIKE ? AND season=? AND CAST(episode AS INTEGER) = ?
        ''', (tvshowtitle, str(season), int(episode) + 1))
        r = c.fetchone()
        
        # 2. Si no existe, probar a buscar el episodio 1 de la siguiente temporada
        if not r:
            c.execute('''
                SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, 
                       episode_title, episode_overview, still_path, clearlogo, banner, clearart, 
                       genres, "cast", torrents, date_added, enriched 
                FROM items 
                WHERE type='tv' AND title LIKE ? AND CAST(season AS INTEGER)=? AND CAST(episode AS INTEGER) = 1
            ''', (tvshowtitle, int(season) + 1))
            r = c.fetchone()
            
        if r:
            return {
                'key': r[0], 'title': r[1], 'type': r[2], 'year': r[3], 'season': int(r[4]) if r[4] else None, 
                'episode': int(r[5]) if r[5] else None, 'tmdb_id': r[6], 'poster': r[7], 'fanart': r[8], 
                'overview': r[9], 'episode_title': r[10], 'episode_overview': r[11], 'still_path': r[12], 
                'clearlogo': r[13], 'banner': r[14], 'clearart': r[15], 'genres': json.loads(r[16]) if r[16] else [], 
                'cast': json.loads(r[17]) if r[17] else [], 'torrents': json.loads(r[18]) if r[18] else []
            }
    except Exception:
        pass
    finally:
        conn.close()
    return None
