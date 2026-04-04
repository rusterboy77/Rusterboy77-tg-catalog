# -*- coding: utf-8 -*-
import os
import sqlite3
import json
import xbmcaddon
import xbmcvfs
import time
import shutil
import zlib
from resources.lib.utils.tools import log

import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import socket

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}")
TEMP_DIR = xbmcvfs.translatePath(f"special://temp/{ADDON_ID}")

DB_FILE = os.path.join(TEMP_DIR, 'session.db')
BIN_FILE_LOCAL = os.path.join(TEMP_DIR, '.sys_buffer.tmp')
REMOTE_DB_URL = "https://raw.githubusercontent.com/Rusterboy7768/Burn-DB/main/cache_choloretro.bin"

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

def _decrypt_local_bin():
    try:
        import sys
        if not os.path.exists(BIN_FILE_LOCAL): return False
            
        _new_k = [67, 104, 111, 108, 111, 82, 101, 116, 114, 111, 95, 83, 101, 99, 117, 114, 101, 95, 50, 48, 50, 53, 33]
        key = bytes(_new_k)
            
        key_len = len(key)
        CHUNK_SIZE = 1035000
        
        import uuid
        tmp_db = DB_FILE + f".{uuid.uuid4().hex[:8]}.tmp"
        decompressor = zlib.decompressobj()
        
        with open(BIN_FILE_LOCAL, 'rb') as f_in, open(tmp_db, 'wb') as f_out:
            while True:
                chunk = bytearray(f_in.read(CHUNK_SIZE))
                if not chunk: break
                for i in range(len(chunk)):
                    chunk[i] ^= key[i % key_len]
                dc = decompressor.decompress(chunk)
                if dc: f_out.write(dc)
            rem = decompressor.flush()
            if rem: f_out.write(rem)
         
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
                time.sleep(0.5)
                
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
        return replaced or _is_db_valid()
    except Exception as e:
        log(f"Database Error decrypting: {e}")
        return False

def _is_db_valid():
    if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) < 50 * 1024:
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("SELECT 1 FROM items LIMIT 1")
        conn.execute("SELECT folder_id, collection_id FROM items LIMIT 1")
        conn.close()
        return True
    except Exception:
        return False

def get_connection():
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA read_uncommitted = 1;")
        conn.execute("PRAGMA journal_mode = OFF;")
        conn.execute("PRAGMA synchronous = 0;")
        conn.execute("PRAGMA cache_size = -2000;")
        conn.execute("PRAGMA mmap_size = 0;")
    except Exception:
        pass
    return conn

def init_db():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    conn = get_connection()
    try:
        c = conn.cursor()
        c.executescript(_SCHEMA)
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_title ON items(title)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_folder_id ON items(folder_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_collection_id ON items(collection_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_items_date_added ON items(date_added)')
        
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

def ensure_session_db():
    os.makedirs(TEMP_DIR, exist_ok=True)
    if not _is_db_valid():
        if os.path.exists(BIN_FILE_LOCAL):
            _decrypt_local_bin()
            if not _is_db_valid():
                try: os.remove(BIN_FILE_LOCAL)
                except: pass
                try: os.remove(os.path.join(PROFILE_DIR, 'version_choloretro.txt'))
                except: pass
                init_db()
            else:
                init_db()
        else:
            init_db()

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

def get_all_items(item_type=None, limit=None, offset=None, exclude_folder_id=None, exclude_genre=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        query = 'SELECT * FROM items WHERE 1=1'
        args = []
        if item_type:
            query += ' AND type = ?'
            args.append(item_type)
        if exclude_folder_id:
            query += ' AND folder_id != ?'
            args.append(exclude_folder_id)
        if exclude_genre:
            query += ' AND genres NOT LIKE ?'
            args.append(f'%{exclude_genre}%')
        
        query += ' ORDER BY date_added DESC'
        
        if limit is not None:
            query += ' LIMIT ?'
            args.append(int(limit))
            if offset is not None:
                query += ' OFFSET ?'
                args.append(int(offset))
        
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
            if ',' in folder_id:
                folders = [f.strip() for f in folder_id.split(',')]
                query += ' AND folder_id IN ({})'.format(','.join(['?'] * len(folders)))
                args.extend(folders)
            else:
                query += ' AND folder_id = ?'
                args.append(folder_id)
        query += ' ORDER BY collection_name'
        
        try:
            c.execute(query, args)
        except sqlite3.OperationalError as e:
            if 'no such column' in str(e):
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

def get_items_by_collection(collection_id, limit=None, offset=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        query = 'SELECT * FROM items WHERE collection_id = ? ORDER BY year'
        args = [collection_id]
        if limit is not None:
            query += ' LIMIT ?'
            args.append(int(limit))
            if offset is not None:
                query += ' OFFSET ?'
                args.append(int(offset))
        c.execute(query, args)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_items_by_folder(folder_id, limit=None, offset=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        try:
            if ',' in folder_id:
                folders = [f.strip() for f in folder_id.split(',')]
                query = 'SELECT * FROM items WHERE folder_id IN ({}) ORDER BY title'.format(','.join(['?'] * len(folders)))
                args = folders
            else:
                query = 'SELECT * FROM items WHERE folder_id = ? ORDER BY title'
                args = [folder_id]
                
            if limit is not None:
                query += ' LIMIT ?'
                args.append(int(limit))
                if offset is not None:
                    query += ' OFFSET ?'
                    args.append(int(offset))
            c.execute(query, args)
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
                    if ',' in folder_id:
                        c.execute('SELECT * FROM items WHERE folder_id IN ({}) ORDER BY title'.format(','.join(['?'] * len(folders))), folders)
                    else:
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
    url = f"{REMOTE_DB_URL}?t={int(time.time())}"
    version_url = f"{REMOTE_DB_URL.rsplit('/', 1)[0]}/version_choloretro.txt?t={int(time.time())}"
    
    last_update_file = os.path.join(PROFILE_DIR, 'last_update.txt')
    local_version_file = os.path.join(PROFILE_DIR, 'version_choloretro.txt')
    
    if os.path.exists(last_update_file):
        try:
            with open(last_update_file, 'r') as f:
                elapsed = time.time() - float(f.read().strip())
                if _is_db_valid() and elapsed < 300:
                    return False
                elif not _is_db_valid() and elapsed < 60:
                    return False
        except:
            pass
            
    try:
        v_file = xbmcvfs.File(f"{version_url}|User-Agent=Mozilla/5.0")
        remote_version = v_file.readBytes(1024).decode('utf-8').strip()
        v_file.close()
    except Exception as e:
        log(f"Database: No se pudo verificar version_choloretro.txt remoto: {e}")
        remote_version = None
        
    if remote_version and os.path.exists(DB_FILE) and os.path.exists(BIN_FILE_LOCAL) and _is_db_valid() and os.path.exists(local_version_file):
        try:
            with open(local_version_file, 'r') as f:
                local_version = f.read().strip()
            if local_version == remote_version:
                log(f"Database: El catálogo ya está en la última versión ({local_version}).")
                with open(last_update_file, 'w') as f:
                    f.write(str(time.time()))
                return False
        except:
            pass
            
    log(f"Database: Descargando nueva versión del catálogo...")
    try:
        vfs_url = f"{url}|User-Agent=Mozilla/5.0"
        f_in = xbmcvfs.File(vfs_url)
        if f_in.size() <= 0:
            f_in.close()
            raise Exception("Kodi VFS C++ falló al conectar con GitHub.")
            
        os.makedirs(TEMP_DIR, exist_ok=True)
        with open(BIN_FILE_LOCAL, 'wb') as out_file:
            while True:
                chunk = f_in.readBytes(1024 * 1024)
                if not chunk: break
                out_file.write(chunk)
        f_in.close()
            
        if not _decrypt_local_bin() or not _is_db_valid():
            try: os.remove(BIN_FILE_LOCAL)
            except: pass
            log("Database: Error desencriptando DB remota descargada.")
            return False
            
        init_db()
        log("Database: Descarga y desencriptación exitosa en memoria temporal.")

        if remote_version:
            with open(local_version_file, 'w') as f:
                f.write(remote_version)
                
        with open(last_update_file, 'w') as f:
            f.write(str(time.time()))
            
        return True
        
    except Exception as e:
        log(f"Database: Error actualizando DB remota: {e}")
        with open(last_update_file, 'w') as f:
            f.write(str(time.time()))
        return False

def search_items_sql(query_str, limit=100, offset=0):
    if not query_str: return []
    conn = get_connection()
    try:
        c = conn.cursor()
        exact_like = f"%{query_str}%"
        words_like = "%" + "%".join(query_str.split()) + "%"
        
        c.execute('''
            SELECT * FROM items 
            WHERE title LIKE ? OR title LIKE ?
            ORDER BY CASE WHEN title LIKE ? THEN 0 ELSE 1 END, date_added DESC
            LIMIT ? OFFSET ?
        ''', (exact_like, words_like, exact_like, limit, offset))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()