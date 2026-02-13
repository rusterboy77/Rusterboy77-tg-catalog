# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import json
from urllib.parse import urlencode
from resources.lib.database import get_all_items, get_tv_shows, get_seasons, get_episodes
from resources.lib.utils.tools import log

def build_url(base_url, query):
    return base_url + '?' + urlencode(query)

def _apply_meta(li, info):
    """Aplica metadata válida al ListItem de forma segura para Kodi 19+.
    Soporta tanto setInfo() antiguo como InfoTagVideo (Kodi 20+).
    """
    # Limpiar valores nulos
    info = {k: v for k, v in info.items() if v is not None}
    
    # setInfo básico (Kodi < 20 y compatibilidad)
    # Filtramos datos complejos que setInfo no soporta (como cast lista de dicts)
    legacy_info = {}
    for k, v in info.items():
        if k == 'cast': continue
        if k == 'tmdb_id': continue
        if isinstance(v, (int, float)):
            legacy_info[k] = str(v)
        else:
            legacy_info[k] = v
            
    try: li.setInfo('video', legacy_info)
    except: pass
    
    # InfoTagVideo (Kodi 20+) - ESTO ES CRUCIAL PARA KODI 21
    try:
        tag = li.getVideoInfoTag()
        if 'title' in info: tag.setTitle(info['title'])
        if 'plot' in info: tag.setPlot(info['plot'])
        if 'year' in info: 
            try: tag.setYear(int(info['year']))
            except: pass
        if 'mediatype' in info: tag.setMediaType(info['mediatype'])
        if 'genre' in info: 
            try:
                genres = info['genre'] if isinstance(info['genre'], list) else (info['genre'].split(', ') if isinstance(info['genre'], str) else [])
                if genres: tag.setGenres(genres)
            except: pass
        if 'rating' in info: 
            try: tag.setRating(float(info['rating']))
            except: pass
        if 'duration' in info: 
            try: tag.setDuration(int(info['duration']))
            except: pass
        if 'trailer' in info and info['trailer']: tag.setTrailer(info['trailer'])
        if 'director' in info and info['director']: 
            try: tag.setDirectors([info['director']])
            except: pass
        if 'studio' in info and info['studio']: 
            try: tag.setStudios([info['studio']])
            except: pass
        if 'cast' in info and info['cast']: 
            try:
                cast_list = [xbmcgui.Actor(name=c['name'], role=c.get('role',''), thumbnail=c.get('thumbnail')) if isinstance(c, dict) else xbmcgui.Actor(name=c) for c in info['cast']]
                if cast_list: tag.setCast(cast_list)
            except: pass
        # IMPORTANTE: Establecer TMDB ID para que el skin pueda enriquecer metadata
        if 'tmdb_id' in info and info['tmdb_id']:
            try: tag.setUniqueIDs({'tmdb': str(info['tmdb_id'])})
            except: pass
    except Exception as e:
        pass

def show_movies(base_url, handle, params):
    xbmcplugin.setContent(handle, 'movies')
    
    # Obtener películas reales de la base de datos
    movies = get_all_items('movie')

    for movie in movies:
        li = xbmcgui.ListItem(label=movie['title'])
        
        # Procesar géneros - ya vienen como lista de strings desde catalog.py
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)  # Si viene como JSON string desde DB
            except Exception as e:
                # Si viene como string pero no es JSON, asumir que está separado por comas
                genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
        else:
            genres = genres_raw or []
        
        # Procesar cast si es un JSON string
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except Exception as e:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': movie.get('title'),
            'year': int(movie['year']) if movie.get('year') and str(movie['year']).isdigit() else 0,
            'plot': movie.get('overview'),
            'mediatype': 'movie',
            'genre': genres,
            'rating': movie.get('rating'),
            'duration': movie.get('duration'),
            'trailer': movie.get('trailer'),
            'director': movie.get('director'),
            'studio': movie.get('studio'),
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        # Aplicar arte DESPUÉS de _apply_meta (importante para actualizar)
        art = {
            'poster': movie.get('poster'), 
            'fanart': movie.get('fanart'),
            'clearlogo': movie.get('clearlogo'),
            'clearart': movie.get('clearart'),
            'banner': movie.get('banner'),
            'landscape': movie.get('landscape'),
            'discart': movie.get('discart')
        }
        # Filtrar valores vacíos/None y aplicar
        art_filtered = {k: v for k, v in art.items() if v}
        if art_filtered:
            try:
                li.setArt(art_filtered)
            except:
                pass

        li.setProperty('IsPlayable', 'true')

        # Extraer el enlace del JSON almacenado en la DB
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''

        # Construir URL para la acción 'play'
        url_params = {
            'action': 'play',
            'title': movie['title'],
            'url': url_link
        }
        url = build_url(base_url, url_params)

        xbmcplugin.addDirectoryItem(handle, url, li, False)

    xbmcplugin.endOfDirectory(handle)

def show_tvshows(base_url, handle, params):
    xbmcplugin.setContent(handle, 'tvshows')
    items = get_tv_shows()
    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        # Procesar géneros - ya vienen como lista de strings desde catalog.py
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)  # Si viene como JSON string desde DB
            except Exception as e:
                # Si viene como string pero no es JSON, asumir que está separado por comas
                genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
        else:
            genres = genres_raw or []
        
        # Procesar cast si es un JSON string
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except Exception as e:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow',
            'genre': genres,
            'rating': item.get('rating'),
            'studio': item.get('studio'),
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
            'clearlogo': item.get('clearlogo'),
            'banner': item.get('banner')
        }
        li.setArt({k: v for k, v in art.items() if v})
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    xbmcplugin.endOfDirectory(handle)

def show_seasons(base_url, handle, params):
    title = params.get('title')
    xbmcplugin.setContent(handle, 'seasons')
    seasons = get_seasons(title)
    for season in seasons:
        li = xbmcgui.ListItem(label=f"Temporada {season}")
        info = {
            'title': f"Temporada {season}", 
            'mediatype': 'season', 
            'season': int(season)
        }
        _apply_meta(li, info)
        
        url_params = {'action': 'list_episodes', 'title': title, 'season': season}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    xbmcplugin.endOfDirectory(handle)

def show_episodes(base_url, handle, params):
    title = params.get('title')
    season = params.get('season')
    xbmcplugin.setContent(handle, 'episodes')
    episodes = get_episodes(title, season)
    
    for ep in episodes:
        li = xbmcgui.ListItem(label=f"Episodio {ep['episode']}")
        info = {
            'title': ep.get('title'), 
            'plot': ep.get('overview'), 
            'mediatype': 'episode',
            'season': int(ep['season']),
            'episode': int(ep['episode']),
            'rating': ep.get('rating'),
            'duration': ep.get('duration'),
            'aired': ep.get('aired')
        }
        _apply_meta(li, info)
        
        li.setArt({'poster': ep.get('poster'), 'fanart': ep.get('fanart'), 'thumb': ep.get('still_path') or ep.get('poster')})
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(ep['links']) if ep['links'] else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': f"{title} S{season}E{ep['episode']}", 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    xbmcplugin.endOfDirectory(handle)