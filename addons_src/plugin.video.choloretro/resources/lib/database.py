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
REMOTE_DB_URL = "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/main/cache_choloretro.db"

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
  folder_id TEXT
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
        
        # Migración: Añadir columna folder_id si no existe (para usuarios que ya tienen la DB creada)
        try:
            c.execute("ALTER TABLE items ADD COLUMN folder_id TEXT")
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
                json.dumps(it.get('genres') or []),
                json.dumps(it.get('cast') or []),
                json.dumps(it.get('links') or []),
                it.get('date_added'),
                1,
                it.get('folder_id')
            ))
        
        c.executemany('''
            INSERT OR REPLACE INTO items 
            ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, overview, episode_title, episode_overview, still_path, genres, "cast", links, date_added, enriched, folder_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        c.execute('SELECT * FROM items WHERE type="tv" GROUP BY title ORDER BY title')
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_items_by_folder(folder_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM items WHERE folder_id = ? ORDER BY title', (folder_id,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def update_db_from_remote():
    """Descarga la base de datos pre-generada desde GitHub."""
    url = REMOTE_DB_URL
    
    log(f"Database: Iniciando descarga de DB desde {url}")
    tmp_db = DB_FILE + ".tmp"
    
    try:
        # Usar un User-Agent para evitar bloqueos de GitHub
        req = urllib.request.Request(url, headers={'User-Agent': 'Kodi-Choloretro'})
        with urllib.request.urlopen(req, timeout=60) as response, open(tmp_db, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
            
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
        return True
        
    except Exception as e:
        log(f"Database: Error actualizando DB remota: {e}")
        if os.path.exists(tmp_db):
            try: os.remove(tmp_db)
            except: pass
        return False