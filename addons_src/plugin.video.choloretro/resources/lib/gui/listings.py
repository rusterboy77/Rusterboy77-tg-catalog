# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import xbmcaddon
import json
import os
from urllib.parse import urlencode, urlparse, parse_qs, unquote_plus
import unicodedata, re
from resources.lib.database import get_all_items, get_tv_shows, get_seasons, get_episodes, get_items_by_folder
from resources.lib.utils.tools import log

def build_url(base_url, query):
    return base_url + '?' + urlencode(query)


def _normalize_title_for_match(s):
    if not s:
        return ''
    try:
        s2 = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII')
        s2 = s2.lower()
        s2 = re.sub(r"[^a-z0-9 ]+", ' ', s2)
        s2 = re.sub(r"\s+", ' ', s2).strip()
        return s2
    except Exception:
        return str(s).lower()

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
    """Menú principal de películas con opciones de filtrado."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    categories = [
        ('Todas', {'action': 'list_all_movies'}),
        ('Colecciones', {'action': 'show_collections'}),
        ('Por Título', {'action': 'list_movies_by_title'}),
        ('Por Género', {'action': 'list_movies_by_genre'}),
        ('Por Año', {'action': 'list_movies_by_year'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_all_movies(base_url, handle, params):
    """Muestra todas las películas normales (sin animación)."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    # Obtener películas reales de la base de datos
    movies = get_all_items('movie')

    for movie in movies:
        # Excluir películas animadas (estarán en Dibujos)
        if _has_genre(movie, 'Animación'):
            continue
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
    """Menú principal de series con opciones de filtrado."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'series.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    categories = [
        ('Todas', {'action': 'list_all_tvshows'}),
        ('Por Título', {'action': 'list_tvshows_by_title'}),
        ('Por Género', {'action': 'list_tvshows_by_genre'}),
        ('Por Año', {'action': 'list_tvshows_by_year'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_all_tvshows(base_url, handle, params):
    """Muestra todas las series normales (sin animación)."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'tvshows')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    items = get_tv_shows()
    for item in items:
        # Excluir series animadas (estarán en Dibujos)
        if _has_genre(item, 'Animación'):
            continue
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
    
    # Retrieve series info to get clearlogo and other metadata
    series_info = None
    try:
        all_series = get_tv_shows()
        for s in all_series:
            if s.get('title', '') == title:
                series_info = s
                break
    except Exception:
        series_info = None
    
    clearlogo_val = ''
    fanart_val = ''
    if series_info:
        clearlogo_val = series_info.get('clearlogo') or series_info.get('logo') or ''
        fanart_val = series_info.get('fanart') or ''
    
    for season in seasons:
        li = xbmcgui.ListItem(label=f"Temporada {season}")
        info = {
            'title': f"Temporada {season}", 
            'mediatype': 'season', 
            'season': int(season)
        }
        _apply_meta(li, info)
        
        # Propagate series logo/fanart to season items
        season_art = {}
        if clearlogo_val:
            season_art['clearlogo'] = clearlogo_val
            season_art['logo'] = clearlogo_val
            season_art['icon'] = clearlogo_val
        if fanart_val:
            season_art['fanart'] = fanart_val
        if season_art:
            try:
                li.setArt(season_art)
            except Exception:
                pass
        
        url_params = {'action': 'list_episodes', 'title': title, 'season': season}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    # Set plugin fanart
    if fanart_val:
        xbmcplugin.setPluginFanart(handle, fanart_val)
    
    xbmcplugin.endOfDirectory(handle)

def show_episodes(base_url, handle, params):
    title = params.get('title')
    season = params.get('season')
    xbmcplugin.setContent(handle, 'episodes')
    episodes = get_episodes(title, season)
    
    # Retrieve series info to get clearlogo and other metadata
    series_info = None
    try:
        all_series = get_tv_shows()
        for s in all_series:
            if s.get('title', '') == title:
                series_info = s
                break
    except Exception:
        series_info = None
    
    clearlogo_val = ''
    fanart_default = ''
    if series_info:
        clearlogo_val = series_info.get('clearlogo') or series_info.get('logo') or ''
        fanart_default = series_info.get('fanart') or ''
    
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
            'aired': ep.get('aired'),
            'tvshowtitle': title
        }
        _apply_meta(li, info)
        
        # Merge episode data with series data for art (similar to rusterwolf77)
        # If episode doesn't have clearlogo, use series' clearlogo
        ep_with_series = dict(ep)
        if not ep_with_series.get('clearlogo'):
            ep_with_series['clearlogo'] = clearlogo_val
        if not ep_with_series.get('fanart') and fanart_default:
            ep_with_series['fanart'] = fanart_default
        
        # Use full art helper like rusterwolf77 (pass merged episode+series data)
        try:
            art_dict = {}
            
            # Poster/thumb: prefer still or episode poster
            poster = ep_with_series.get('poster') or ep_with_series.get('poster_path') or ''
            still = ep_with_series.get('still_path') or ''
            if still:
                art_dict['thumb'] = still
                art_dict['poster'] = still
            elif poster:
                art_dict['thumb'] = poster
                art_dict['poster'] = poster
            
            # Fanart
            fanart = ep_with_series.get('fanart') or ep_with_series.get('backdrop_path') or ''
            if fanart:
                art_dict['fanart'] = fanart
            
            # Logo/clearlogo (crucial for series branding)
            clearlogo = ep_with_series.get('clearlogo') or ep_with_series.get('logo') or ''
            if clearlogo:
                art_dict['clearlogo'] = clearlogo
                art_dict['logo'] = clearlogo
                art_dict['icon'] = clearlogo
            
            # Only set non-empty values
            if art_dict:
                li.setArt(art_dict)
        except Exception:
            pass
        
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(ep['links']) if ep.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': f"{title} S{season}E{ep['episode']}", 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    # Set plugin fanart
    if fanart_default:
        xbmcplugin.setPluginFanart(handle, fanart_default)
    
    xbmcplugin.endOfDirectory(handle)

def _has_genre(item, genre_name):
    """Verifica si un item tiene un género específico."""
    genres_raw = item.get('genres')
    if isinstance(genres_raw, str):
        try:
            genres = json.loads(genres_raw)
        except:
            genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
    else:
        genres = genres_raw or []
    
    return any(genre_name.lower() in (g.lower() if isinstance(g, str) else g.get('name', '').lower()) for g in genres)

def show_animated(base_url, handle, params):
    """Muestra películas y series animadas."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    # Categorías de contenido animado
    categories = [
        ('Películas Animadas', {'action': 'list_animated_movies'}),
        ('Series Animadas', {'action': 'list_animated_tvshows'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_animated_movies(base_url, handle, params):
    """Muestra solo películas con género Animación."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    movies = get_all_items('movie')
    
    for movie in movies:
        if not _has_genre(movie, 'Animación'):
            continue
            
        li = xbmcgui.ListItem(label=movie['title'])
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
        else:
            genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
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
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {
            'poster': movie.get('poster'), 
            'fanart': movie.get('fanart'),
            'clearlogo': movie.get('clearlogo'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': movie['title'], 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_animated_tvshows(base_url, handle, params):
    """Muestra solo series con género Animación."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'tvshows')
    items = get_tv_shows()
    
    for item in items:
        if not _has_genre(item, 'Animación'):
            continue
            
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
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
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
            'clearlogo': item.get('clearlogo'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_collections(base_url, handle, params):
    """Muestra las colecciones especiales definidas por ID de carpeta."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    # Definición de colecciones y sus IDs de carpeta
    collections = [
        ('Cine Quinqui', '19205939'),
        ('Clásicas Español', '19205942'),
        ('Lina Morgan', '19205937'),
        ('Pajares y Esteso', '19205934')
    ]
    
    for title, folder_id in collections:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_collection_items', 'folder_id': folder_id, 'title': title}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_collection_items(base_url, handle, params):
    """Lista items filtrados por folder_id."""
    folder_id = params.get('folder_id')
    
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    items = get_items_by_folder(folder_id)

    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = genres_raw.split(', ') if ', ' in genres_raw else [genres_raw] if genres_raw else []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': item.get('type', 'movie'),
            'genre': genres,
            'rating': item.get('rating'),
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

        # Manejar si es serie o película
        if item.get('type') == 'tv':
             url_params = {'action': 'list_seasons', 'title': item['title']}
             is_folder = True
        else:
             li.setProperty('IsPlayable', 'true')
             links = json.loads(item['links']) if item.get('links') else []
             url_link = links[0]['url'] if links else ''
             url_params = {
                'action': 'play',
                'title': item['title'],
                'url': url_link
             }
             is_folder = False

        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, is_folder)

    xbmcplugin.endOfDirectory(handle)

def show_search(base_url, handle, params):
    """Muestra diálogo de búsqueda y resultados mezclados (películas y series juntas)."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    search_term = params.get('search_term')
    
    # Si no hay término de búsqueda, pedir al usuario
    if not search_term:
        dialog = xbmcgui.Dialog()
        search_term = dialog.input('Buscar contenido')
        if not search_term:
            xbmcplugin.endOfDirectory(handle)
            return
    
    xbmcplugin.setContent(handle, 'movies')  # Mostrar como contenido de video para ver posters
    search_term_lower = search_term.lower()
    found_total = 0
    
    # Buscar películas (incluyendo animadas)
    movies = get_all_items('movie')
    for movie in movies:
        movie_title = movie.get('title', '')
        if not movie_title or search_term_lower not in movie_title.lower():
            continue
        
        found_total += 1
        li = xbmcgui.ListItem(label=movie_title)
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': movie.get('title'),
            'year': int(movie['year']) if movie.get('year') and str(movie['year']).isdigit() else 0,
            'plot': movie.get('overview'),
            'mediatype': 'movie',
            'genre': genres,
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {
            'poster': movie.get('poster'), 
            'fanart': movie.get('fanart'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': movie['title'], 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    items = get_tv_shows()
    for item in items:
        item_title = item.get('title', '')
        if not item_title or search_term_lower not in item_title.lower():
            continue
        
        found_total += 1
        li = xbmcgui.ListItem(label=item_title)
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow',
            'genre': genres,
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if found_total == 0:
        no_results = xbmcgui.ListItem('Sin resultados')
        no_results.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(handle, '', no_results, False)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_movies_menu(base_url, handle, params):
    """Menú con opciones de filtrado para películas."""
    xbmcplugin.setContent(handle, 'files')
    
    ADDON_PATH = xbmcaddon.Addon().getAddonInfo('path')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    categories = [
        ('Todas', {'action': 'list_movies'}),
        ('Por Título', {'action': 'list_movies_by_title'}),
        ('Por Género', {'action': 'list_movies_by_genre'}),
        ('Por Año', {'action': 'list_movies_by_year'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.endOfDirectory(handle)

def show_tvshows_menu(base_url, handle, params):
    """Menú con opciones de filtrado para series."""
    xbmcplugin.setContent(handle, 'files')
    
    ADDON_PATH = xbmcaddon.Addon().getAddonInfo('path')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'series.png')
    
    categories = [
        ('Todas', {'action': 'list_tvshows'}),
        ('Por Título', {'action': 'list_tvshows_by_title'}),
        ('Por Género', {'action': 'list_tvshows_by_genre'}),
        ('Por Año', {'action': 'list_tvshows_by_year'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': icon_path})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.endOfDirectory(handle)

def show_continue_watching(base_url, handle, params):
    """Muestra 'Seguir viendo' - items en reproducción desde bookmarks de Kodi.
    
    Lee la tabla de bookmarks de la DB de Kodi (MyVideos*.db) para obtener
    items a medio reproducir y los enriquece con metadatos del catálogo.
    """
    import sqlite3
    import glob
    import xbmcvfs
    from urllib.parse import urlparse, parse_qs
    
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    # Cargar catálogo local para enriquecer items
    try:
        catalog = get_all_items('movie') + get_tv_shows()
    except:
        catalog = []
    
    # Índice por título para búsqueda rápida
    catalog_by_title = {}
    for item in catalog:
        try:
            title = item.get('title', '').lower()
            if title:
                catalog_by_title[title] = item
        except:
            continue
    
    # Localizar MyVideos*.db en special://profile/Database
    db_path = None
    try:
        try:
            profile = xbmcvfs.translatePath('special://profile/')
        except:
            profile = ''
        
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        
        if db_candidates:
            # Usar la más reciente
            db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
        # Log no sensible para ayudar al diagnóstico
        try:
            from resources.lib.utils.tools import log
            log(f"Choloretro: MyVideos.db candidates={len(db_candidates)} found={bool(db_path)}")
        except Exception:
            pass
    except Exception as e:
        log(f"Choloretro: Error localizando DB de Kodi - {str(e)}")
        db_path = None
    
    # Leer bookmarks
    bookmarks = []
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            
            # Obtener bookmarks con info del archivo
            cur.execute("""
                SELECT b.idBookmark, b.idFile, b.timeInSeconds, b.totalTimeInSeconds, f.strFilename 
                FROM bookmark b 
                JOIN files f ON b.idFile = f.idFile 
                ORDER BY b.idBookmark DESC 
                LIMIT 100
            """)
            rows = cur.fetchall()
            
            for row in rows:
                try:
                    idBookmark, idFile, timeInSeconds, totalTimeInSeconds, strFilename = row
                    
                    # FILTRO: Solo items de plugin.video.choloretro
                    # (Ignorar archivos locales y otros addons)
                    if not strFilename:
                        continue
                    
                    filename_lower = strFilename.lower()
                    
                    # Aceptar solo URLs de nuestro addon o archivos que reconozcamos
                    # Rechazar otros addons
                    if 'plugin://' in filename_lower:
                        # Es una URL de plugin, verificar que sea la nuestra
                        if 'plugin.video.choloretro' not in filename_lower:
                            continue  # Es de otro addon, saltar
                    
                    bookmarks.append({
                        'filename': strFilename,
                        'time': timeInSeconds or 0,
                        'total': totalTimeInSeconds or 0
                    })
                except:
                    continue
            
            conn.close()
        except Exception as e:
            log(f"Choloretro: Error leyendo bookmarks - {str(e)}")
    
    # Mostrar bookmarks
    if not bookmarks:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        li.setProperty('IsPlayable', 'false')
        try:
            li.setArt({'icon': ADDON_ICON, 'fanart': FANART})
        except:
            pass
        xbmcplugin.addDirectoryItem(handle, '', li, False)
        xbmcplugin.endOfDirectory(handle)
        return
    
    # Procesar cada bookmark
    shown = 0
    for bm in bookmarks[:25]:  # Limitar a 25 items
        try:
            filename = bm.get('filename', '')
            display_title = filename
            catalog_item = None
            play_url = filename
            decoded = filename
            parsed = None
            qs = {}
            
            # Intentar extraer info del catálogo con heurísticas más robustas
            if filename:
                # Decodificar la URL para buscar parámetros 'title' o 'season/episode'
                try:
                    decoded = unquote_plus(filename)
                except:
                    decoded = filename

                try:
                    parsed = urlparse(decoded)
                    qs = parse_qs(parsed.query)
                except:
                    parsed = None
                    qs = {}

                # Si hay título explícito en los parámetros, usarlo
                if 'title' in qs and qs.get('title'):
                    display_title = qs.get('title')[0]

                # Normalizar texto para matching
                search_text = _normalize_title_for_match(decoded)

                # Buscar coincidencias en catálogo usando títulos normalizados
                best_match = None
                best_score = 0
                for cat_item in catalog:
                    try:
                        cat_title_raw = cat_item.get('title', '')
                        if not cat_title_raw:
                            continue
                        cat_title = _normalize_title_for_match(cat_title_raw)

                        if not cat_title:
                            continue

                        # Coincidencia directa de substring normalizado
                        if cat_title in search_text:
                            score = len(cat_title)
                        else:
                            # puntuar por intersección de tokens
                            t1 = set(cat_title.split())
                            t2 = set(search_text.split())
                            inter = len(t1 & t2)
                            score = inter

                        if score > best_score:
                            best_score = score
                            best_match = cat_item
                            # Si la coincidencia es razonable, adoptar su título
                            if score >= max(3, int(len(cat_title) * 0.5)):
                                display_title = cat_item.get('title')
                    except:
                        continue

                if best_match:
                    catalog_item = best_match
            
            # Crear ListItem
            li = xbmcgui.ListItem(label=display_title)
            li.setProperty('IsPlayable', 'true')
            
            # Aplicar arte con POSTERS
            art_dict = {'icon': ADDON_ICON, 'fanart': FANART}
            is_episode_item = False
            episode_obj = None
            series_obj = None

            if isinstance(catalog_item, dict):
                # If catalog_item is a TV series, prefer episode-level art when possible
                ctype = (catalog_item.get('type') or '').lower()
                if ctype == 'tv':
                    series_obj = catalog_item
                    # Try to determine season/episode from parsed query or filename (SxxExx)
                    season_num = None
                    ep_num = None
                    try:
                        if parsed and qs:
                            if 'season' in qs and qs.get('season'):
                                season_num = int(qs.get('season')[0])
                            if 'episode' in qs and qs.get('episode'):
                                ep_num = int(qs.get('episode')[0])
                    except Exception:
                        pass

                    # fallback: detect SxxExx pattern in decoded filename
                    if not season_num or not ep_num:
                        try:
                            import re as _re
                            m = _re.search(r'[sS](\d{1,2})[eE](\d{1,3})', decoded if 'decoded' in locals() else filename)
                            if m:
                                season_num = int(m.group(1))
                                ep_num = int(m.group(2))
                        except Exception:
                            pass

                    if season_num and ep_num is not None:
                        try:
                            eps = get_episodes(series_obj.get('title'), season_num)
                            for ep in eps:
                                try:
                                    if int(ep.get('episode') or 0) == int(ep_num):
                                        episode_obj = ep
                                        is_episode_item = True
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                # Build art using episode if available, otherwise series/movie art
                if is_episode_item and episode_obj:
                    poster = episode_obj.get('poster') or episode_obj.get('still_path') or series_obj.get('poster') or ''
                    thumb = episode_obj.get('still_path') or poster
                    fanart = episode_obj.get('fanart') or series_obj.get('fanart') or ''
                    clearlogo = (series_obj.get('clearlogo') or series_obj.get('logo') or '') if series_obj else ''

                    if poster:
                        art_dict['poster'] = poster
                        art_dict['thumb'] = thumb
                    if fanart:
                        art_dict['fanart'] = fanart
                    if clearlogo:
                        art_dict['clearlogo'] = clearlogo
                        art_dict['logo'] = clearlogo
                        art_dict['icon'] = clearlogo
                else:
                    poster = catalog_item.get('poster') or catalog_item.get('poster_path') or catalog_item.get('thumb') or catalog_item.get('thumbnail') or catalog_item.get('poster_url') or ''
                    fanart = catalog_item.get('fanart') or catalog_item.get('backdrop_path') or catalog_item.get('backdrop') or catalog_item.get('fanart_url') or ''
                    clearlogo = catalog_item.get('clearlogo') or catalog_item.get('logo') or ''

                    if poster:
                        art_dict['poster'] = poster
                        art_dict['thumb'] = poster
                    if fanart:
                        art_dict['fanart'] = fanart
                    if clearlogo:
                        art_dict['clearlogo'] = clearlogo
                        art_dict['logo'] = clearlogo
                        art_dict['icon'] = clearlogo
            
            try:
                li.setArt(art_dict)
            except:
                pass
            
            # Aplicar metadatos si hay item del catálogo
            if isinstance(catalog_item, dict):
                try:
                    tag = li.getVideoInfoTag()
                    
                    if catalog_item.get('title'):
                        tag.setTitle(catalog_item.get('title'))
                    
                    if catalog_item.get('overview'):
                        tag.setPlot(catalog_item.get('overview'))
                    
                    try:
                        year = catalog_item.get('year')
                        if year:
                            tag.setYear(int(year))
                    except:
                        pass
                    
                    try:
                        rating = catalog_item.get('rating')
                        if rating:
                            tag.setRating(float(rating))
                    except:
                        pass
                except:
                    pass

            # Marcar si ya está visto en la librería (si hay TMDB id o existe en la librería)
            try:
                def _is_marked_watched(tmdb_id=None, mediatype='movie', series_title=None, season=None, episode=None):
                    try:
                        import xbmc, json as _json
                        if mediatype == 'movie':
                            if not tmdb_id:
                                return False
                            method = 'VideoLibrary.GetMovies'
                            params = {'filter': {'field': 'tmdbid', 'operator': 'is', 'value': str(tmdb_id)}, 'properties': ['playcount'], 'limits': {'start': 0, 'end': 1}}
                            req = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
                            res = xbmc.executeJSONRPC(_json.dumps(req))
                            parsed = _json.loads(res or '{}')
                            if 'result' in parsed:
                                arr = parsed['result'].get('movies', [])
                                if arr and arr[0].get('playcount', 0) > 0:
                                    return True
                            return False
                        else:
                            # Try by tmdb id first
                            if tmdb_id:
                                method = 'VideoLibrary.GetEpisodes'
                                params = {'filter': {'field': 'tmdbid', 'operator': 'is', 'value': str(tmdb_id)}, 'properties': ['playcount'], 'limits': {'start': 0, 'end': 1}}
                                req = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
                                res = xbmc.executeJSONRPC(_json.dumps(req))
                                parsed = _json.loads(res or '{}')
                                if 'result' in parsed:
                                    arr = parsed['result'].get('episodes', [])
                                    if arr and arr[0].get('playcount', 0) > 0:
                                        return True
                            # Fallback: search episodes by season + episode + showtitle
                            if series_title and season is not None and episode is not None:
                                try:
                                    method = 'VideoLibrary.GetEpisodes'
                                    params = {'filter': {'field': 'season', 'operator': 'is', 'value': str(season)}, 'properties': ['season', 'episode', 'playcount', 'showtitle'], 'limits': {'start': 0, 'end': 500}}
                                    req = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
                                    res = xbmc.executeJSONRPC(_json.dumps(req))
                                    parsed = _json.loads(res or '{}')
                                    if 'result' in parsed:
                                        eps = parsed['result'].get('episodes', [])
                                        for e in eps:
                                            try:
                                                if int(e.get('episode') or 0) == int(episode):
                                                    # normalize showtitle
                                                    st = e.get('showtitle') or ''
                                                    if _normalize_title_for_match(st) == _normalize_title_for_match(series_title):
                                                        if e.get('playcount', 0) > 0:
                                                            return True
                                            except Exception:
                                                continue
                                except Exception:
                                    pass
                            return False
                    except Exception:
                        return False

                if isinstance(catalog_item, dict):
                    tmdb = catalog_item.get('tmdb_id') or catalog_item.get('tmdb')
                    ctype = (catalog_item.get('type') or '').lower()
                    # If episode_obj exists, prefer checking episode watched state
                    if 'is_episode_item' in locals() and is_episode_item and episode_obj:
                        st = catalog_item.get('title')
                        sn = int(episode_obj.get('season') or 0)
                        en = int(episode_obj.get('episode') or 0)
                        if _is_marked_watched(tmdb_id=None, mediatype='tv', series_title=st, season=sn, episode=en):
                            try:
                                li.setProperty('playcount', '1')
                            except:
                                pass
                    else:
                        if tmdb:
                            if _is_marked_watched(tmdb, 'movie' if ctype == 'movie' else 'tv'):
                                try:
                                    li.setProperty('playcount', '1')
                                except:
                                    pass
            except Exception:
                pass
            
            # Agregar al listado
            if play_url:
                xbmcplugin.addDirectoryItem(handle, play_url, li, False)
                shown += 1
                
                # Si es una serie, intentar añadir el siguiente episodio (si existe)
                try:
                    series_title = None
                    season_num = None
                    ep_num = None
                    
                    # Prefer catalog_item title como título de la serie
                    if isinstance(catalog_item, dict) and (catalog_item.get('type') or '').lower() == 'tv':
                        series_title = catalog_item.get('title')

                    # Intentar extraer season/episode desde parámetros si están presentes
                    # (parsed y qs ya están disponibles desde arriba)
                    if qs:
                        if 'season' in qs and qs.get('season'):
                            try:
                                season_num = int(qs.get('season')[0])
                            except:
                                season_num = None
                        if 'episode' in qs and qs.get('episode'):
                            try:
                                ep_num = int(qs.get('episode')[0])
                            except:
                                ep_num = None
                    
                    # fallback: detect SxxExx pattern en decoded filename
                    if not season_num or ep_num is None:
                        try:
                            import re as _re
                            m = _re.search(r'[sS](\d{1,2})[eE](\d{1,3})', decoded)
                            if m:
                                season_num = int(m.group(1))
                                ep_num = int(m.group(2))
                        except Exception:
                            pass

                    # Si tenemos suficiente info, buscar siguiente episodio
                    if series_title and season_num is not None and ep_num is not None:
                        try:
                            episodes = get_episodes(series_title, season_num)
                            # Buscar episodio con numero = ep_num + 1
                            for ep in episodes:
                                try:
                                    if int(ep.get('episode') or 0) == int(ep_num) + 1:
                                        # Construir ListItem similar a show_episodes
                                        li2 = xbmcgui.ListItem(label=f"Próximo: {series_title} S{season_num}E{ep['episode']}")
                                        info2 = {
                                            'title': ep.get('title'),
                                            'plot': ep.get('overview'),
                                            'mediatype': 'episode',
                                            'season': int(ep['season']),
                                            'episode': int(ep['episode']),
                                            'rating': ep.get('rating'),
                                            'duration': ep.get('duration'),
                                            'aired': ep.get('aired')
                                        }
                                        _apply_meta(li2, info2)
                                        li2.setArt({'poster': ep.get('poster'), 'fanart': ep.get('fanart'), 'thumb': ep.get('still_path') or ep.get('poster')})
                                        li2.setProperty('IsPlayable', 'true')
                                        links2 = json.loads(ep['links']) if ep.get('links') else []
                                        url_link2 = links2[0]['url'] if links2 else ''
                                        url_params2 = {'action': 'play', 'title': f"{series_title} S{season_num}E{ep['episode']}", 'url': url_link2}
                                        url2 = build_url(base_url, url_params2)
                                        xbmcplugin.addDirectoryItem(handle, url2, li2, False)
                                        shown += 1
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            log(f"Choloretro: Error procesando bookmark - {str(e)}")
            continue
    
    if shown == 0:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        li.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(handle, '', li, False)
    
    xbmcplugin.endOfDirectory(handle)

def show_movies_by_title(base_url, handle, params):
    """Muestra películas agrupadas alfabéticamente por título."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación')]
    
    # Agrupar por primera letra
    groups = {}
    for movie in movies:
        title = movie.get('title', '')
        if not title:
            continue
        first_letter = title[0].upper()
        if first_letter not in groups:
            groups[first_letter] = []
        groups[first_letter].append(movie)
    
    # Mostrar grupos alfabéticamente
    for letter in sorted(groups.keys()):
        li = xbmcgui.ListItem(label=f"{letter}")
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_movies_by_letter', 'letter': letter}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_movies_by_letter(base_url, handle, params):
    """Muestra todas las películas que comienzan con la letra especificada."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    letter = params.get('letter', 'A')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación')]
    movies = [m for m in movies if m.get('title', '').upper().startswith(letter)]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    for movie in movies:
        li = xbmcgui.ListItem(label=movie['title'])
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': movie.get('title'),
            'year': int(movie['year']) if movie.get('year') and str(movie['year']).isdigit() else 0,
            'plot': movie.get('overview'),
            'mediatype': 'movie',
            'genre': genres,
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': movie['title'], 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_movies_by_genre(base_url, handle, params):
    """Muestra películas agrupadas por género."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación')]
    
    genres_set = set()
    for movie in movies:
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        for g in genres:
            if isinstance(g, dict):
                genres_set.add(g.get('name', ''))
            else:
                genres_set.add(str(g))
    
    for genre in sorted(genres_set):
        if not genre:
            continue
        li = xbmcgui.ListItem(label=genre)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_movies_by_genre_filter', 'genre': genre}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_movies_by_genre_filter(base_url, handle, params):
    """Muestra películas de un género específico."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    genre = params.get('genre', '')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación') and _has_genre(m, genre)]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    for movie in movies:
        li = xbmcgui.ListItem(label=movie['title'])
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': movie.get('title'),
            'year': int(movie['year']) if movie.get('year') and str(movie['year']).isdigit() else 0,
            'plot': movie.get('overview'),
            'mediatype': 'movie',
            'genre': genres,
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': movie['title'], 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_movies_by_year(base_url, handle, params):
    """Muestra películas agrupadas por año."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación')]
    
    years_set = set()
    for movie in movies:
        year = movie.get('year')
        if year:
            years_set.add(str(year))
    
    for year in sorted(years_set, reverse=True):
        li = xbmcgui.ListItem(label=year)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_movies_by_year_filter', 'year': year}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_movies_by_year_filter(base_url, handle, params):
    """Muestra películas de un año específico."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    year = params.get('year', '')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _has_genre(m, 'Animación') and str(m.get('year', '')) == year]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    for movie in movies:
        li = xbmcgui.ListItem(label=movie['title'])
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': movie.get('title'),
            'year': int(movie['year']) if movie.get('year') and str(movie['year']).isdigit() else 0,
            'plot': movie.get('overview'),
            'mediatype': 'movie',
            'genre': genres,
            'cast': cast,
            'tmdb_id': movie.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        links = json.loads(movie['links']) if movie.get('links') else []
        url_link = links[0]['url'] if links else ''
        
        url_params = {'action': 'play', 'title': movie['title'], 'url': url_link}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_tvshows_by_title(base_url, handle, params):
    """Muestra series agrupadas alfabéticamente por título."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'series.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación')]
    
    groups = {}
    for item in items:
        title = item.get('title', '')
        if not title:
            continue
        first_letter = title[0].upper()
        if first_letter not in groups:
            groups[first_letter] = []
        groups[first_letter].append(item)
    
    for letter in sorted(groups.keys()):
        li = xbmcgui.ListItem(label=f"{letter}")
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_tvshows_by_letter', 'letter': letter}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_tvshows_by_letter(base_url, handle, params):
    """Muestra series que comienzan con la letra especificada."""
    xbmcplugin.setContent(handle, 'tvshows')
    letter = params.get('letter', 'A')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación')]
    items = [i for i in items if i.get('title', '').upper().startswith(letter)]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow',
            'genre': genres,
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_tvshows_by_genre(base_url, handle, params):
    """Muestra series agrupadas por género."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'series.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación')]
    
    genres_set = set()
    for item in items:
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        for g in genres:
            if isinstance(g, dict):
                genres_set.add(g.get('name', ''))
            else:
                genres_set.add(str(g))
    
    for genre in sorted(genres_set):
        if not genre:
            continue
        li = xbmcgui.ListItem(label=genre)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_tvshows_by_genre_filter', 'genre': genre}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_tvshows_by_genre_filter(base_url, handle, params):
    """Muestra series de un género específico."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'tvshows')
    genre = params.get('genre', '')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación') and _has_genre(i, genre)]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow',
            'genre': genres,
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_tvshows_by_year(base_url, handle, params):
    """Muestra series agrupadas por año."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'series.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación')]
    
    years_set = set()
    for item in items:
        year = item.get('year')
        if year:
            years_set.add(str(year))
    
    for year in sorted(years_set, reverse=True):
        li = xbmcgui.ListItem(label=year)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url_params = {'action': 'list_tvshows_by_year_filter', 'year': year}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_tvshows_by_year_filter(base_url, handle, params):
    """Muestra series de un año específico."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'tvshows')
    year = params.get('year', '')
    
    items = get_tv_shows()
    items = [i for i in items if not _has_genre(i, 'Animación') and str(i.get('year', '')) == year]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try:
                genres = json.loads(genres_raw)
            except:
                genres = []
        else:
            genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try:
                cast = json.loads(cast_raw)
            except:
                cast = []
        else:
            cast = cast_raw or []
        
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow',
            'genre': genres,
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        _apply_meta(li, info)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)