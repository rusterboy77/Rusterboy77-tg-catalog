# -*- coding: utf-8 -*-
"""Script de diagnóstico para verificar qué hay en la DB"""
import sqlite3
import json
import os
import xbmcvfs
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}")
DB_FILE = os.path.join(PROFILE_DIR, 'cache.db')

def debug_db():
    if not os.path.exists(DB_FILE):
        print(f"❌ DB NO EXISTE: {DB_FILE}")
        return
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Contar items por tipo
    c.execute("SELECT type, COUNT(*) as count FROM items GROUP BY type")
    print("\n=== ITEMS POR TIPO ===")
    for row in c.fetchall():
        print(f"{row['type'].upper()}: {row['count']} items")
    
    # Ver una película completa
    c.execute("SELECT * FROM items WHERE type='movie' LIMIT 1")
    movie = c.fetchone()
    if movie:
        print("\n=== PELÍCULA DE EJEMPLO ===")
        for key in movie.keys():
            val = movie[key]
            if key in ('genres', 'cast', 'links'):
                try:
                    parsed = json.loads(val) if isinstance(val, str) else val
                    print(f"{key}: {json.dumps(parsed, indent=2)[:200]}...")
                except:
                    print(f"{key}: {val}")
            else:
                print(f"{key}: {val}")
    else:
        print("\n❌ NO HAY PELÍCULAS EN LA BD")
    
    # Ver un episodio completo
    c.execute("SELECT * FROM items WHERE type='tv' LIMIT 1")
    episode = c.fetchone()
    if episode:
        print("\n=== EPISODIO DE EJEMPLO ===")
        for key in episode.keys():
            val = episode[key]
            if key in ('genres', 'cast', 'links'):
                try:
                    parsed = json.loads(val) if isinstance(val, str) else val
                    print(f"{key}: {json.dumps(parsed, indent=2)[:200]}...")
                except:
                    print(f"{key}: {val}")
            else:
                print(f"{key}: {val}")
    else:
        print("\n❌ NO HAY EPISODIOS EN LA BD")
    
    conn.close()
    print("\n✅ DEBUG COMPLETO")

if __name__ == '__main__':
    debug_db()
