# -*- coding: utf-8 -*-
import json
import urllib.request
import xbmcaddon
from resources.lib.database import upsert_items
from resources.lib.utils.tools import log

ADDON = xbmcaddon.Addon()

# URL del catálogo remoto (hardcodeada por seguridad)
CATALOG_URL = "https://raw.githubusercontent.com/rusterboy77/Rusterboy77-tg-catalog/main/catalog_choloretro.json"

def update_catalog():
    """Descarga el catalog.json y actualiza la DB local."""
    url = CATALOG_URL
    
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        items = parse_catalog(data)
        if items:
            upsert_items(items)
            return True
        else:
            return False
    except Exception as e:
        log(f"Catalog Error: {e}")
        return False

def parse_catalog(data):
    """Convierte el JSON remoto al formato de nuestra DB.
    Extrae TODOS los metadatos disponibles de TMDB para películas y series.
    """
    parsed_items = []
    results = data.get('results', [])
    
    for entry in results:
        parsed = entry.get('parsed', {})
        tmdb = entry.get('tmdb_top', {})
        item_type = parsed.get('type')
        
        # Extraer metadatos comunes
        genres_raw = tmdb.get('genres', [])  # Lista de {id, name}
        # Convertir a lista de strings con solo nombres
        genres = [g['name'] if isinstance(g, dict) else str(g) for g in genres_raw]
        
        cast = tmdb.get('cast', [])  # Lista de {name, role, thumbnail}
        clearlogo = tmdb.get('clearlogo', '')
        banner = tmdb.get('banner', '')
        clearart = tmdb.get('clearart', '')
        rating = tmdb.get('vote_average')  # Rating de TMDB
        
        if item_type == 'movie':
            title = parsed.get('title')
            year = parsed.get('year')
            links = entry.get('links') or []
            
            if not links: continue
            
            item = {
                'key': f"movie_{title}_{year}",
                'title': title,
                'type': 'movie',
                'year': year,
                'tmdb_id': tmdb.get('tmdb_id'),
                'poster': tmdb.get('poster_url'),
                'fanart': tmdb.get('backdrop_url'),
                'overview': tmdb.get('overview'),
                'genres': genres,  # Array de nombres de géneros
                'cast': cast,  # Array de actores con name, role, thumbnail
                'rating': rating,
                'clearlogo': clearlogo,
                'banner': banner,
                'clearart': clearart,
                'links': links,
                'date_added': entry.get('date_added')
            }
            parsed_items.append(item)
            
        elif item_type == 'series':
            series_title = parsed.get('series')
            episodes = entry.get('episodes', [])
            
            for ep in episodes:
                links = ep.get('links') or []
                if not links: continue
                
                season = ep.get('season')
                episode = ep.get('episode')
                
                item = {
                    'key': f"tv_{series_title}_{season}_{episode}",
                    'title': series_title,
                    'type': 'tv',
                    'year': tmdb.get('year'),  # Usar año de TMDB
                    'season': season,
                    'episode': episode,
                    'tmdb_id': tmdb.get('tmdb_id'),
                    'poster': tmdb.get('poster_url'),
                    'fanart': tmdb.get('backdrop_url'),
                    'overview': tmdb.get('overview'),
                    'genres': genres,  # Array de nombres de géneros
                    'cast': cast,  # Array de actores con name, role, thumbnail
                    'rating': rating,
                    'clearlogo': clearlogo,
                    'banner': banner,
                    'clearart': clearart,
                    'links': links,
                    'date_added': entry.get('date_added')
                }
                parsed_items.append(item)
    
    return parsed_items