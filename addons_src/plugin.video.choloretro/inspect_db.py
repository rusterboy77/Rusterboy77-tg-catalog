# -*- coding: utf-8 -*-
"""Script simple para inspeccionar la cache.db"""
import sqlite3
import json
import os

DB_PATH = os.path.expanduser("~/.kodi/userdata/addon_data/plugin.video.choloretro/cache.db")
# Ajusta esta ruta si necesario

if not os.path.exists(DB_PATH):
    print(f"❌ {DB_PATH} NO EXISTE")
else:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Contar por tipo
    c.execute("SELECT type, COUNT(*) as cnt FROM items GROUP BY type")
    print("\n=== ITEMS EN LA BD ===")
    for row in c.fetchall():
        print(f"{row['type'].upper()}: {row['cnt']}")
    
    # Ver detalles de una película
    c.execute("SELECT * FROM items WHERE type='movie' LIMIT 1")
    movie = c.fetchone()
    if movie:
        print("\n=== PELÍCULA DE EJEMPLO ===")
        print(f"Título: {movie['title']}")
        print(f"Año: {movie['year']}")
        print(f"Rating: {movie['rating']}")
        print(f"Poster: {movie['poster']}")
        print(f"Géneros RAW: {movie['genres']}")
        try:
            g = json.loads(movie['genres'])
            print(f"Géneros PARSED: {g}")
        except:
            print("❌ Error al parsear géneros")
        print(f"Cast RAW: {movie['cast'][:100] if movie['cast'] else 'VACIO'}...")
        
    conn.close()
    print("\n✅ Inspección completa")
