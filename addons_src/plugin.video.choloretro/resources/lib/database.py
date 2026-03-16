# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmcaddon
import xbmcvfs
import time
import urllib.request
import shutil
from resources.lib.utils.tools import log

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}")
DB_FILE = os.path.join(PROFILE_DIR, 'cache.db')
REMOTE_DB_URL = "https://pub-80ab14db311c4254ade7bac002c3ef53.r2.dev/cache_choloretro.bin"

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
  clearlogo TEXT,
  banner TEXT,
  clearart TEXT,
  overview TEXT,
  episode_title TEXT,
  episode_overview TEXT,
  still_path TEXT,
  genres TEXT,
  "cast" TEXT,
  links TEXT,
  date_added TEXT,
  enriched INTEGER DEFAULT 0,
  folder_id TEXT,
  collection_id TEXT,
  collection_name TEXT,
  collection_poster TEXT,
  collection_fanart TEXT,
  collection_clearlogo TEXT
)
'''

def get_connection():
    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.executescript(_SCHEMA)
        # Migraciones o indices adicionales si fueran necesarios
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)')
        
        # Migración: Añadir columnas si no existen (en bloques separados para evitar fallos en cadena)
        try:
            c.execute("ALTER TABLE items ADD COLUMN folder_id TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE items ADD COLUMN collection_id TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE items ADD COLUMN collection_name TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE items ADD COLUMN collection_poster TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE items ADD COLUMN collection_fanart TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE items ADD COLUMN collection_clearlogo TEXT")
        except:
            pass
            
        conn.commit()
    except Exception as e:
        log(f"Database Error Init: {e}")
    finally:
        conn.close()

def upsert_items(items):
    if not items:
        return
    conn = get_connection()
    try:
        c = conn.cursor()
        vals = []
        
        for it in items:
            vals.append((
                it.get('key'),
                it.get('title'),
                it.get('type'),
                str(it.get('year') or ''),
                str(it.get('season') or ''),
                str(it.get('episode') or ''),
                str(it.get('tmdb_id') or ''),
                it.get('poster'),
                it.get('fanart'),
                it.get('clearlogo'),
                it.get('banner'),
                it.get('clearart'),
                it.get('overview'),
                it.get('episode_title'),
                it.get('episode_overview'),
                it.get('still_path'),
                json.dumps(it.get('genres') or [], ensure_ascii=False),
                json.dumps(it.get('cast') or [], ensure_ascii=False),
                json.dumps(it.get('links') or [], ensure_ascii=False),
                it.get('date_added'),
                1,
                it.get('folder_id'),
                it.get('collection_id'),
                it.get('collection_name'),
                it.get('collection_poster'),
                it.get('collection_fanart'),
                it.get('collection_clearlogo')
            ))
        
        c.executemany('''
            INSERT OR REPLACE INTO items 
            ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, overview, episode_title, episode_overview, still_path, genres, "cast", links, date_added, enriched, folder_id, collection_id, collection_name, collection_poster, collection_fanart, collection_clearlogo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', vals)
        conn.commit()
    except Exception as e:
        log(f"Database Error Upsert: {e}")
    finally:
        conn.close()

def get_all_items(item_type=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        query = 'SELECT * FROM items'
        args = []
        if item_type:
            query += ' WHERE type = ?'
            args.append(item_type)
        
        query += ' ORDER BY date_added DESC'
        
        c.execute(query, args)
        rows = c.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_item_by_key(key):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM items WHERE "key" = ?', (key,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_seasons(series_title):
    conn = get_connection()
    try:
        c = conn.cursor()
        # Normalizamos titulo para busqueda si es necesario, aqui asumo exactitud o uso LIKE
        c.execute('SELECT DISTINCT season FROM items WHERE type="tv" AND title=? ORDER BY CAST(season AS INTEGER)', (series_title,))
        return [row['season'] for row in c.fetchall() if row['season']]
    finally:
        conn.close()

def get_episodes(series_title, season):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM items WHERE type="tv" AND title=? AND season=? ORDER BY CAST(episode AS INTEGER)', (series_title, season))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_tv_shows():
    conn = get_connection()
    try:
        c = conn.cursor()
        # Agrupamos por título pero seleccionamos TODOS los campos para tener metadata completa
        c.execute('SELECT * FROM items WHERE type="tv" GROUP BY title ORDER BY MAX(date_added) DESC')
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_collections(genre=None, exclude_genre=None, folder_id=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        query = 'SELECT DISTINCT collection_id, collection_name, collection_poster, collection_fanart, collection_clearlogo FROM items WHERE collection_id IS NOT NULL AND collection_id != ""'
        args = []
        if genre:
            query += ' AND genres LIKE ?'
            args.append(f'%{genre}%')
        if exclude_genre:
            query += ' AND genres NOT LIKE ?'
            args.append(f'%{exclude_genre}%')
        if folder_id:
            query += ' AND folder_id = ?'
            args.append(folder_id)
        query += ' ORDER BY collection_name'
        
        try:
            c.execute(query, args)
        except sqlite3.OperationalError as e:
            if 'no such column' in str(e):
                # Auto-recuperación: Intentar crear las columnas si faltan
                try: c.execute("ALTER TABLE items ADD COLUMN collection_id TEXT")
                except: pass
                try: c.execute("ALTER TABLE items ADD COLUMN collection_name TEXT")
                except: pass
                try: c.execute("ALTER TABLE items ADD COLUMN collection_poster TEXT")
                except: pass
                try: c.execute("ALTER TABLE items ADD COLUMN collection_fanart TEXT")
                except: pass
                try: c.execute("ALTER TABLE items ADD COLUMN collection_clearlogo TEXT")
                except: pass
                conn.commit()
                c.execute(query, args)
            else:
                raise e
                
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_items_by_collection(collection_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM items WHERE collection_id = ? ORDER BY year', (collection_id,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_items_by_folder(folder_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        try:
            c.execute('SELECT * FROM items WHERE folder_id = ? ORDER BY title', (folder_id,))
        except sqlite3.OperationalError as e:
            if 'no such column' in str(e):
                log("Database: Columna folder_id faltante detectada. Aplicando migración automática.")
                try:
                    c.execute("ALTER TABLE items ADD COLUMN folder_id TEXT")
                    c.execute("ALTER TABLE items ADD COLUMN collection_id TEXT")
                    c.execute("ALTER TABLE items ADD COLUMN collection_name TEXT")
                    c.execute("ALTER TABLE items ADD COLUMN collection_poster TEXT")
                    c.execute("ALTER TABLE items ADD COLUMN collection_fanart TEXT")
                    c.execute("ALTER TABLE items ADD COLUMN collection_clearlogo TEXT")
                    conn.commit()
                    c.execute('SELECT * FROM items WHERE folder_id = ? ORDER BY title', (folder_id,))
                except Exception as e2:
                    log(f"Database Error recovering column: {e2}")
                    return []
            else:
                raise e
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def update_db_from_remote():
    """Descarga la base de datos pre-generada desde GitHub."""
    url = REMOTE_DB_URL
    
    log(f"Database: Iniciando descarga de DB desde {url}")
    tmp_db = DB_FILE + ".tmp"
    tmp_bin = DB_FILE + ".bin.tmp"
    
    try:
        # Usar un User-Agent para evitar bloqueos
        req = urllib.request.Request(url, headers={'User-Agent': 'Kodi-Choloretro'})
        with urllib.request.urlopen(req, timeout=60) as response, open(tmp_bin, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
            
        # Desencriptar el archivo .bin descargado
        with open(tmp_bin, 'rb') as f:
            data = bytearray(f.read())
            
        key = bytearray('CholoRetro_XOR_Key_2024', 'utf-8')
        key_len = len(key)
        for i in range(len(data)):
            data[i] ^= key[i % key_len]
            
        with open(tmp_db, 'wb') as f:
            f.write(data)
            
        try: os.remove(tmp_bin)
        except: pass
        
        # Verificar integridad básica (abrir y contar items)
        conn = sqlite3.connect(tmp_db)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM items")
        count = c.fetchone()[0]
        conn.close()
        
        log(f"Database: Descarga exitosa. Items en DB remota: {count}")
        
        # Reemplazar la DB local (Windows requiere cerrar conexiones antes, init_db ya lo hace)
        if os.path.exists(DB_FILE):
            try: os.remove(DB_FILE)
            except: pass # Si falla el borrado, rename podría fallar en Windows, pero intentamos
        
        os.rename(tmp_db, DB_FILE)
        
        # Asegurar que la nueva DB tiene el esquema correcto (migraciones)
        init_db()
        
        return True
        
    except Exception as e:
        log(f"Database: Error actualizando DB remota: {e}")
        if os.path.exists(tmp_db):
            try: os.remove(tmp_db)
            except: pass
        if os.path.exists(tmp_bin):
            try: os.remove(tmp_bin)
            except: pass
        return False