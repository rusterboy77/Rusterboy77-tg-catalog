# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import xbmcaddon
import time
import json
import os
from urllib.parse import urlencode, urlparse, parse_qs, unquote_plus
import unicodedata, re
from resources.lib.database import get_all_items, get_tv_shows, get_seasons, get_episodes, get_items_by_folder, get_collections, get_items_by_collection, search_items_sql
from resources.lib.utils.tools import log

ITEMS_PER_PAGE = 40

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

_PROGRESS_CACHE = None

def get_cached_progress():
    global _PROGRESS_CACHE
    if _PROGRESS_CACHE is None:
        _PROGRESS_CACHE = load_progress_override()
    return _PROGRESS_CACHE

def get_progress_file():
    import xbmcvfs
    ADDON = xbmcaddon.Addon()
    profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    if not os.path.exists(profile_dir): os.makedirs(profile_dir)
    return os.path.join(profile_dir, 'progress_override.json')

def load_progress_override():
    pf = get_progress_file()
    if os.path.exists(pf):
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {'hidden': [], 'manual': {}}

def save_progress_override(data):
    pf = get_progress_file()
    if pf:
        try:
            with open(pf, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

def action_add_progress(params):
    global _PROGRESS_CACHE
    _PROGRESS_CACHE = None
    po = load_progress_override()
    val = params.get('val')
    if not val: return
    if val in po['hidden']: po['hidden'].remove(val)
    po['manual'][val] = {'wtype': params.get('wtype'), 'title': params.get('title'), 'key': params.get('key'), 'added': time.time()}
    save_progress_override(po)
    xbmcgui.Dialog().notification('Choloretro', f'{params.get("title", "")} añadido a Seguir Viendo', xbmcaddon.Addon().getAddonInfo('icon'))

def action_remove_progress(params):
    global _PROGRESS_CACHE
    _PROGRESS_CACHE = None
    po = load_progress_override()
    val = params.get('val')
    if not val: return
    if val in po['manual']: del po['manual'][val]
    if val not in po['hidden']: po['hidden'].append(val)
    save_progress_override(po)
    xbmcgui.Dialog().notification('Choloretro', f'{params.get("title", "Elemento")} quitado de Seguir Viendo', xbmcaddon.Addon().getAddonInfo('icon'))
    import xbmc
    xbmc.executebuiltin('Container.Refresh')

def generate_context_menu(base_url, item_type, val, title, is_watched, watched_eps=0, total_eps=0, item_key=None):
    cm = []
    if item_type in ('movie', 'tv'):
        po = get_cached_progress()
        is_manual = val in po.get('manual', {})
        is_hidden = val in po.get('hidden', [])
        has_progress = False
        if item_type == 'tv' and 0 < watched_eps < total_eps: has_progress = True
        elif item_type == 'movie' and item_key and item_key in _get_resume_points(): has_progress = True
        is_in_seguir_viendo = (is_manual or has_progress) and not is_hidden
        if is_in_seguir_viendo: cm.append(('Quitar de Seguir Viendo', f'RunPlugin({build_url(base_url, {"action": "remove_progress", "val": val, "title": title})})'))
        else: cm.append(('Añadir a Seguir Viendo', f'RunPlugin({build_url(base_url, {"action": "add_progress", "wtype": item_type, "val": val, "title": title, "key": item_key})})'))
    if item_type in ('tv', 'season'):
        if is_watched: cm.append(('Marcar como no visto', 'Action(ToggleWatched)'))
        else: cm.append(('Marcar como visto', 'Action(ToggleWatched)'))
    return cm

_PLAYED_KEYS = None

def _get_played_keys():
    global _PLAYED_KEYS
    if _PLAYED_KEYS is not None:
        return _PLAYED_KEYS
    
    _PLAYED_KEYS = {}
    import xbmc, xbmcvfs, os, glob, sqlite3
    from urllib.parse import urlparse, parse_qs
    try:
        profile = xbmcvfs.translatePath('special://profile/')
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if db_candidates:
            db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            try:
                cur.execute("SELECT strFilename, lastPlayed FROM files WHERE strFilename LIKE 'plugin://plugin.video.choloretro/%' AND playCount > 0")
            except Exception:
                cur.execute("SELECT strFilename, NULL FROM files WHERE strFilename LIKE 'plugin://plugin.video.choloretro/%' AND playCount > 0")
            for row in cur.fetchall():
                try:
                    qs = parse_qs(urlparse(row[0]).query)
                    action = qs.get('action', [''])[0]
                    if action == 'play':
                        tvshow = qs.get('tvshowtitle', [''])[0]
                        if tvshow:
                            s = qs.get('season', [''])[0]
                            e = qs.get('episode', [''])[0]
                            ident = f"tv_{_normalize_title_for_match(tvshow)}_{s}_{e}"
                        else:
                            t = qs.get('title', [''])[0]
                            ident = f"movie_{_normalize_title_for_match(t)}"
                        _PLAYED_KEYS[ident] = row[1] if len(row) > 1 and row[1] else ""
                except Exception:
                    pass
            conn.close()
    except Exception:
        pass
    return _PLAYED_KEYS

_RESUME_POINTS = None

def _get_resume_points():
    global _RESUME_POINTS
    if _RESUME_POINTS is not None:
        return _RESUME_POINTS
    
    _RESUME_POINTS = {}
    import xbmc, xbmcvfs, os, glob, sqlite3
    from urllib.parse import urlparse, parse_qs
    try:
        profile = xbmcvfs.translatePath('special://profile/')
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if db_candidates:
            db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT f.strFilename, b.timeInSeconds, b.totalTimeInSeconds FROM bookmark b JOIN files f ON b.idFile = f.idFile WHERE f.strFilename LIKE 'plugin://plugin.video.choloretro/%' AND b.type = 1")
            for row in cur.fetchall():
                try:
                    qs = parse_qs(urlparse(row[0]).query)
                    action = qs.get('action', [''])[0]
                    if action == 'play':
                        tvshow = qs.get('tvshowtitle', [''])[0]
                        if tvshow:
                            s = qs.get('season', [''])[0]
                            e = qs.get('episode', [''])[0]
                            ident = f"tv_{_normalize_title_for_match(tvshow)}_{s}_{e}"
                        else:
                            t = qs.get('title', [''])[0]
                            ident = f"movie_{_normalize_title_for_match(t)}"
                        _RESUME_POINTS[ident] = {'time': float(row[1]), 'total': float(row[2])}
                except Exception:
                    pass
            conn.close()
    except Exception:
        pass
    return _RESUME_POINTS

_SERIES_PROGRESS_CACHE = {}
def _get_series_progress(series_title):
    global _SERIES_PROGRESS_CACHE
    if series_title in _SERIES_PROGRESS_CACHE:
        return _SERIES_PROGRESS_CACHE[series_title]
        
    from resources.lib.database import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT season, episode FROM items WHERE type="tv" AND title=?', (series_title,))
        rows = c.fetchall()
        played = _get_played_keys()
        total_eps, watched_eps = len(rows), 0
        series_norm = _normalize_title_for_match(series_title)
        for r in rows:
            if f"tv_{series_norm}_{r['season']}_{r['episode']}" in played: watched_eps += 1
        _SERIES_PROGRESS_CACHE[series_title] = (total_eps, watched_eps)
        return total_eps, watched_eps
    except Exception: return 0, 0
    finally: conn.close()

_SEASON_PROGRESS_CACHE = {}
def _get_season_progress(series_title, season):
    global _SEASON_PROGRESS_CACHE
    cache_key = f"{series_title}_{season}"
    if cache_key in _SEASON_PROGRESS_CACHE:
        return _SEASON_PROGRESS_CACHE[cache_key]
        
    from resources.lib.database import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT season, episode FROM items WHERE type="tv" AND title=? AND season=?', (series_title, str(season)))
        rows = c.fetchall()
        played = _get_played_keys()
        total_eps, watched_eps = len(rows), 0
        series_norm = _normalize_title_for_match(series_title)
        for r in rows:
            if f"tv_{series_norm}_{r['season']}_{r['episode']}" in played: watched_eps += 1
        _SEASON_PROGRESS_CACHE[cache_key] = (total_eps, watched_eps)
        return total_eps, watched_eps
    except Exception: return 0, 0
    finally: conn.close()

def _inject_playback_state(info, li):
    import xbmc
    try:
        kodi_version = int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
    except:
        kodi_version = 20

    played, resumes = _get_played_keys(), _get_resume_points()
    itype = info.get('mediatype')
    is_watched = False
    total_eps = 0
    watched_eps = 0
    
    if itype == 'movie':
        ident = f"movie_{_normalize_title_for_match(info.get('title', ''))}"
        if ident in played: 
            info['playcount'] = 1
            is_watched = True
        if ident in resumes:
            info['resume_time'], info['resume_total'] = resumes[ident]['time'], resumes[ident]['total']
            if kodi_version < 20:
                li.setProperty('ResumeTime', str(info['resume_time']))
                li.setProperty('TotalTime', str(info['resume_total']))
            
    elif itype == 'tvshow':
        total_eps, watched_eps = _get_series_progress(info.get('title', ''))
        if total_eps > 0:
            li.setProperty('TotalEpisodes', str(total_eps))
            li.setProperty('WatchedEpisodes', str(watched_eps))
            li.setProperty('UnWatchedEpisodes', str(total_eps - watched_eps))
            if watched_eps == total_eps: 
                info['playcount'] = 1
                is_watched = True
            
    elif itype == 'season':
        total_eps, watched_eps = _get_season_progress(info.get('tvshowtitle', ''), info.get('season'))
        if total_eps > 0:
            li.setProperty('TotalEpisodes', str(total_eps))
            li.setProperty('WatchedEpisodes', str(watched_eps))
            li.setProperty('UnWatchedEpisodes', str(total_eps - watched_eps))
            if watched_eps == total_eps: 
                info['playcount'] = 1
                is_watched = True
            
    elif itype == 'episode':
        ident = f"tv_{_normalize_title_for_match(info.get('tvshowtitle', ''))}_{info.get('season', '')}_{info.get('episode', '')}"
        if ident in played: 
            info['playcount'] = 1
            is_watched = True
        if ident in resumes:
            info['resume_time'], info['resume_total'] = resumes[ident]['time'], resumes[ident]['total']
            if kodi_version < 20:
                li.setProperty('ResumeTime', str(info['resume_time']))
                li.setProperty('TotalTime', str(info['resume_total']))
            
    return is_watched, watched_eps, total_eps

def _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps):
    itype = info.get('mediatype')
    cm = []
    if itype == 'movie':
        ident = f"movie_{_normalize_title_for_match(info.get('title', ''))}"
        cm = generate_context_menu(base_url, 'movie', ident, info.get('title', ''), is_watched, item_key=ident)
    elif itype == 'tvshow':
        title = info.get('title', '')
        ident = _normalize_title_for_match(title)
        cm = generate_context_menu(base_url, 'tv', ident, title, is_watched, watched_eps=watched_eps, total_eps=total_eps)
    elif itype == 'season':
        cm = generate_context_menu(base_url, 'season', None, None, is_watched)
    elif itype == 'episode':
        cm = generate_context_menu(base_url, 'episode', None, None, is_watched)
    if cm: li.addContextMenuItems(cm)

def _apply_meta(li, info):
    """Aplica metadata válida al ListItem de forma segura para Kodi 19+.
    Soporta tanto setInfo() antiguo como InfoTagVideo (Kodi 20+).
    """
    import xbmc
    try:
        kodi_version = int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
    except:
        kodi_version = 20

    # Limpiar valores nulos
    info = {k: v for k, v in info.items() if v is not None}
    
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
        if 'playcount' in info: 
            try: tag.setPlaycount(int(info['playcount']))
            except: pass
        if 'resume_time' in info and 'resume_total' in info: 
            try: tag.setResumePoint(float(info['resume_time']), float(info['resume_total']))
            except: pass
    except Exception as e:
        pass

    # setInfo básico (Kodi < 20 y compatibilidad)
    if kodi_version < 20:
        legacy_info = {}
        for k, v in info.items():
            if k in ('cast', 'tmdb_id', 'resume_time', 'resume_total'): continue
            if isinstance(v, (int, float)):
                legacy_info[k] = str(v)
            else:
                legacy_info[k] = v
                
        try: li.setInfo('video', legacy_info)
        except: pass

def _add_next_page(handle, base_url, params, page):
    next_page = page + 1
    new_params = params.copy()
    new_params['page'] = next_page
    url = build_url(base_url, new_params)
    li = xbmcgui.ListItem(label=f'>>> Página Siguiente ({next_page}) >>>')
    li.setArt({'icon': 'DefaultFolder.png'})
    xbmcplugin.addDirectoryItem(handle, url, li, True)

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
        ('Sagas', {'action': 'list_sagas'}),
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

    # Filtrar películas de animación usando ID de carpeta
    movies = [m for m in movies if not _is_animated_movie(m) and not _is_anime(m)]

    # Ordenar alfabéticamente primero y luego por fecha (sólo por día) para evitar orden Z-A
    movies.sort(key=lambda x: x.get('title') or '')
    movies.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
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

        # Construir URL para la acción 'play' usando el ID (key) por seguridad y eficiencia
        url_params = {
            'action': 'play',
            'title': movie['title'],
            'key': movie.get('key')
        }
        url = build_url(base_url, url_params)

        xbmcplugin.addDirectoryItem(handle, url, li, False)

    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    # Filtrar series de animación usando ID de carpeta
    items = [i for i in items if not _is_animated_tvshow(i) and not _is_anime(i)]

    # Ordenar alfabéticamente primero y luego por fecha (sólo por día) para evitar orden Z-A
    items.sort(key=lambda x: x.get('title') or '')
    items.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
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

    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
            'season': int(season),
            'tvshowtitle': title
        }
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
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
    
    page = int(params.get('page', 1))
    total_items = len(episodes)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

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
    
    for ep in episodes[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
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
        
        url_params = {
            'action': 'play',
            'title': f"{title} S{season}E{ep['episode']}",
            'key': ep.get('key'),
            'tvshowtitle': title,
            'season': season,
            'episode': ep['episode'],
            'tmdb': series_info.get('tmdb_id') if series_info else ''
        }
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    # Set plugin fanart
    if fanart_default:
        xbmcplugin.setPluginFanart(handle, fanart_default)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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

def _is_anime(item):
    """Determina si un item es anime por carpeta."""
    folder_id = str(item.get('folder_id') or '').strip()
    return folder_id in ['19385669', '19410546', '19740846', '19740847', '19841488']

def _is_animated_movie(item):
    """Determina si una película es de animación por carpeta (ID 19168455) o por género."""
    folder_id = str(item.get('folder_id') or '').strip()
    if folder_id in ['19168455', '19207971', '19208195', '19207967', '19740832']:
        return True
    return _has_genre(item, 'Animación')

def _is_animated_tvshow(item):
    """Determina si una serie es de animación por carpeta (ID 19161644) o por género."""
    folder_id = str(item.get('folder_id') or '').strip()
    
    # Añade aquí las IDs de las subcarpetas rebeldes
    animated_tv_folders = [
        '19161644', '19207971', '19208195', '19207967', '19207956', '19545621',
        '19410563', '19839530', '19841491', '19820148', '19852607', '19738901', '19839541', '19852608'
   ]
    
    if folder_id in animated_tv_folders:
        return True
    return _has_genre(item, 'Animación')

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
        ('Sagas Animadas', {'action': 'list_sagas', 'folder_id': '19168455,19740832'}),
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
    mode = params.get('mode')
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    if not mode:
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        categories = [
            ('Todas', {'action': params.get('action', 'list_animated_movies'), 'mode': 'all'}),
            ('Por Título', {'action': params.get('action', 'list_animated_movies'), 'mode': 'title'}),
            ('Por Año', {'action': params.get('action', 'list_animated_movies'), 'mode': 'year'}),
        ]
        for title, query_params in categories:
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url = build_url(base_url, query_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    movies = get_all_items('movie')
    movies = [m for m in movies if _is_animated_movie(m) and not _is_anime(m)]
    
    if mode == 'title':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        groups = {}
        for movie in movies:
            title = movie.get('title', '')
            if not title: continue
            first_letter = title[0].upper()
            if first_letter not in groups: groups[first_letter] = []
            groups[first_letter].append(movie)
        for letter in sorted(groups.keys()):
            li = xbmcgui.ListItem(label=f"{letter}")
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_animated_movies'), 'mode': 'title_filter', 'letter': letter}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return
        
    elif mode == 'year':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        years_set = set()
        for movie in movies:
            year = movie.get('year')
            if year: years_set.add(str(year))
        for year in sorted(years_set, reverse=True):
            li = xbmcgui.ListItem(label=year)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_animated_movies'), 'mode': 'year_filter', 'year': year}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    if mode == 'title_filter':
        letter = params.get('letter', 'A')
        movies = [m for m in movies if m.get('title', '').upper().startswith(letter)]
        movies = sorted(movies, key=lambda x: x.get('title', ''))
    elif mode == 'year_filter':
        year = params.get('year', '')
        movies = [m for m in movies if str(m.get('year', '')) == year]
        movies = sorted(movies, key=lambda x: x.get('title', ''))
    else:
        movies.sort(key=lambda x: x.get('title') or '')
        movies.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    xbmcplugin.setContent(handle, 'movies')

    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {
            'poster': movie.get('poster'), 
            'fanart': movie.get('fanart'),
            'clearlogo': movie.get('clearlogo'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        li.setProperty('IsPlayable', 'true')
        
        url_params = {'action': 'play', 'title': movie['title'], 'key': movie.get('key')}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_animated_tvshows(base_url, handle, params):
    """Muestra solo series con género Animación."""
    mode = params.get('mode')
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    if not mode:
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        categories = [
            ('Todas', {'action': params.get('action', 'list_animated_tvshows'), 'mode': 'all'}),
            ('Por Título', {'action': params.get('action', 'list_animated_tvshows'), 'mode': 'title'}),
            ('Por Año', {'action': params.get('action', 'list_animated_tvshows'), 'mode': 'year'}),
        ]
        for title, query_params in categories:
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url = build_url(base_url, query_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    items = get_tv_shows()
    items = [i for i in items if _is_animated_tvshow(i) and not _is_anime(i)]
    
    if mode == 'title':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        groups = {}
        for item in items:
            title = item.get('title', '')
            if not title: continue
            first_letter = title[0].upper()
            if first_letter not in groups: groups[first_letter] = []
            groups[first_letter].append(item)
        for letter in sorted(groups.keys()):
            li = xbmcgui.ListItem(label=f"{letter}")
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_animated_tvshows'), 'mode': 'title_filter', 'letter': letter}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return
        
    elif mode == 'year':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'dibujos.png')
        xbmcplugin.setContent(handle, 'files')
        years_set = set()
        for item in items:
            year = item.get('year')
            if year: years_set.add(str(year))
        for year in sorted(years_set, reverse=True):
            li = xbmcgui.ListItem(label=year)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_animated_tvshows'), 'mode': 'year_filter', 'year': year}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    if mode == 'title_filter':
        letter = params.get('letter', 'A')
        items = [i for i in items if i.get('title', '').upper().startswith(letter)]
        items = sorted(items, key=lambda x: x.get('title', ''))
    elif mode == 'year_filter':
        year = params.get('year', '')
        items = [i for i in items if str(i.get('year', '')) == year]
        items = sorted(items, key=lambda x: x.get('title', ''))
    else:
        items.sort(key=lambda x: x.get('title') or '')
        items.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    xbmcplugin.setContent(handle, 'tvshows')

    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
            'clearlogo': item.get('clearlogo'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def show_anime(base_url, handle, params):
    """Muestra películas y series de anime."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    # Categorías de contenido anime
    categories = [
        ('Películas Anime', {'action': 'list_anime_movies'}),
        ('Series Anime', {'action': 'list_anime_tvshows'}),
        ('Sagas Anime', {'action': 'list_sagas', 'folder_id': '19385669,19410546,19740846,19740847'}),
    ]
    
    for title, query_params in categories:
        li = xbmcgui.ListItem(label=title)
        # Usamos icono específico si existe, o fallback
        li.setArt({'icon': icon_path, 'fanart': FANART})
        url = build_url(base_url, query_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_anime_movies(base_url, handle, params):
    """Muestra solo películas de la carpeta Anime."""
    mode = params.get('mode')
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    if not mode:
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        categories = [
            ('Todas', {'action': params.get('action', 'list_anime_movies'), 'mode': 'all'}),
            ('Por Título', {'action': params.get('action', 'list_anime_movies'), 'mode': 'title'}),
            ('Por Año', {'action': params.get('action', 'list_anime_movies'), 'mode': 'year'}),
        ]
        for title, query_params in categories:
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url = build_url(base_url, query_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    movies = get_all_items('movie')
    movies = [m for m in movies if _is_anime(m)]
    
    if mode == 'title':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        groups = {}
        for movie in movies:
            title = movie.get('title', '')
            if not title: continue
            first_letter = title[0].upper()
            if first_letter not in groups: groups[first_letter] = []
            groups[first_letter].append(movie)
        for letter in sorted(groups.keys()):
            li = xbmcgui.ListItem(label=f"{letter}")
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_anime_movies'), 'mode': 'title_filter', 'letter': letter}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return
        
    elif mode == 'year':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        years_set = set()
        for movie in movies:
            year = movie.get('year')
            if year: years_set.add(str(year))
        for year in sorted(years_set, reverse=True):
            li = xbmcgui.ListItem(label=year)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_anime_movies'), 'mode': 'year_filter', 'year': year}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    xbmcplugin.setContent(handle, 'movies')
    
    if mode == 'title_filter':
        letter = params.get('letter', 'A')
        movies = [m for m in movies if m.get('title', '').upper().startswith(letter)]
        movies = sorted(movies, key=lambda x: x.get('title', ''))
    elif mode == 'year_filter':
        year = params.get('year', '')
        movies = [m for m in movies if str(m.get('year', '')) == year]
        movies = sorted(movies, key=lambda x: x.get('title', ''))
    else:
        movies.sort(key=lambda x: x.get('title') or '')
        movies.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
        li = xbmcgui.ListItem(label=movie['title'])
        
        genres_raw = movie.get('genres')
        if isinstance(genres_raw, str):
            try: genres = json.loads(genres_raw)
            except: genres = []
        else: genres = genres_raw or []
        
        cast_raw = movie.get('cast')
        if isinstance(cast_raw, str):
            try: cast = json.loads(cast_raw)
            except: cast = []
        else: cast = cast_raw or []
        
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {'poster': movie.get('poster'), 'fanart': movie.get('fanart'), 'clearlogo': movie.get('clearlogo')}
        li.setArt({k: v for k, v in art.items() if v})
        li.setProperty('IsPlayable', 'true')
        
        url_params = {'action': 'play', 'title': movie['title'], 'key': movie.get('key')}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_anime_tvshows(base_url, handle, params):
    """Muestra solo series de la carpeta Anime."""
    mode = params.get('mode')
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    if not mode:
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        categories = [
            ('Todas', {'action': params.get('action', 'list_anime_tvshows'), 'mode': 'all'}),
            ('Por Título', {'action': params.get('action', 'list_anime_tvshows'), 'mode': 'title'}),
            ('Por Año', {'action': params.get('action', 'list_anime_tvshows'), 'mode': 'year'}),
        ]
        for title, query_params in categories:
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url = build_url(base_url, query_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    items = get_tv_shows()
    items = [i for i in items if _is_anime(i)]
    
    if mode == 'title':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        groups = {}
        for item in items:
            title = item.get('title', '')
            if not title: continue
            first_letter = title[0].upper()
            if first_letter not in groups: groups[first_letter] = []
            groups[first_letter].append(item)
        for letter in sorted(groups.keys()):
            li = xbmcgui.ListItem(label=f"{letter}")
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_anime_tvshows'), 'mode': 'title_filter', 'letter': letter}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return
        
    elif mode == 'year':
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'anime.png')
        xbmcplugin.setContent(handle, 'files')
        years_set = set()
        for item in items:
            year = item.get('year')
            if year: years_set.add(str(year))
        for year in sorted(years_set, reverse=True):
            li = xbmcgui.ListItem(label=year)
            li.setArt({'icon': icon_path, 'fanart': FANART})
            url_params = {'action': params.get('action', 'list_anime_tvshows'), 'mode': 'year_filter', 'year': year}
            url = build_url(base_url, url_params)
            xbmcplugin.addDirectoryItem(handle, url, li, True)
        xbmcplugin.setPluginFanart(handle, FANART)
        xbmcplugin.endOfDirectory(handle)
        return

    if mode == 'title_filter':
        letter = params.get('letter', 'A')
        items = [i for i in items if i.get('title', '').upper().startswith(letter)]
        items = sorted(items, key=lambda x: x.get('title', ''))
    elif mode == 'year_filter':
        year = params.get('year', '')
        items = [i for i in items if str(i.get('year', '')) == year]
        items = sorted(items, key=lambda x: x.get('title', ''))
    else:
        items.sort(key=lambda x: x.get('title') or '')
        items.sort(key=lambda x: (x.get('date_added') or '')[:10], reverse=True)

    xbmcplugin.setContent(handle, 'tvshows')

    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
        li = xbmcgui.ListItem(label=item['title'])
        
        genres_raw = item.get('genres')
        if isinstance(genres_raw, str):
            try: genres = json.loads(genres_raw)
            except: genres = []
        else: genres = genres_raw or []
        
        cast_raw = item.get('cast')
        if isinstance(cast_raw, str):
            try: cast = json.loads(cast_raw)
            except: cast = []
        else: cast = cast_raw or []
        
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {'poster': item.get('poster'), 'fanart': item.get('fanart'), 'clearlogo': item.get('clearlogo')}
        li.setArt({k: v for k, v in art.items() if v})
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)

def list_sagas(base_url, handle, params):
    """Lista las sagas (colecciones) disponibles."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    genre = params.get('genre')
    folder_id = params.get('folder_id')
    # Si no hay género específico ni carpeta, excluimos Animación para que no salgan mezcladas
    exclude_genre = 'Animación' if not genre and not folder_id else None
    collections = get_collections(genre=genre, exclude_genre=exclude_genre, folder_id=folder_id)
    
    for col in collections:
        li = xbmcgui.ListItem(label=col['collection_name'])
        art = {'fanart': FANART}
        if col.get('collection_poster'):
            art['poster'] = col['collection_poster']
            art['thumb'] = col['collection_poster']
            art['icon'] = col['collection_poster']
        if col.get('collection_fanart'):
            art['fanart'] = col['collection_fanart']
        if col.get('collection_clearlogo'):
            art['clearlogo'] = col['collection_clearlogo']
            art['clearart'] = col['collection_clearlogo']
            art['logo'] = col['collection_clearlogo']
        
        # Añadir info básica para que la vista de póster funcione mejor
        info = {
            'title': col['collection_name'],
            'plot': col['collection_name'],
            'mediatype': 'set'
        }
        _apply_meta(li, info)
        
        li.setArt(art)
        
        url_params = {'action': 'list_saga_items', 'collection_id': col['collection_id'], 'title': col['collection_name']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
        
    xbmcplugin.endOfDirectory(handle)

def list_saga_items(base_url, handle, params):
    """Lista los items de una saga específica."""
    collection_id = params.get('collection_id')
    
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    items = get_items_by_collection(collection_id)
    
    for item in items:
        li = xbmcgui.ListItem(label=item['title'])
        
        # Reutilizamos lógica de info básica
        info = {
            'title': item.get('title'),
            'year': int(item['year']) if item.get('year') and str(item['year']).isdigit() else 0,
            'plot': item.get('overview'),
            'mediatype': 'tvshow' if item.get('type') == 'tv' else 'movie',
            'rating': item.get('rating'),
            'tmdb_id': item.get('tmdb_id')
        }
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
            'clearlogo': item.get('clearlogo')
        }
        li.setArt({k: v for k, v in art.items() if v})

        li.setProperty('IsPlayable', 'true')
        url = build_url(base_url, {'action': 'play', 'title': item['title'], 'key': item.get('key')})
        xbmcplugin.addDirectoryItem(handle, url, li, False)

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
        ('Cine Quinqui', '19205939,19740845'),
        ('Clásicas Español', '19205942,19740842'),
        ('Lina Morgan', '19205937,19740843'),
        ('Pajares y Esteso', '19205934,19740844'),
        ('Grandes Clásicos del Cine', '19235310,19740839')
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
    
    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
            'mediatype': 'tvshow' if item.get('type') == 'tv' else 'movie',
            'genre': genres,
            'rating': item.get('rating'),
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
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
             url_params = {
                'action': 'play',
                'title': item['title'],
                'key': item.get('key')
             }
             is_folder = False

        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, is_folder)

    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.endOfDirectory(handle)

def show_search(base_url, handle, params):
    """Muestra diálogo de búsqueda y resultados mezclados (películas y series juntas)."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    search_term = params.get('search_term') or params.get('q') or params.get('query')
    
    # Si no hay término de búsqueda, pedir al usuario
    if not search_term:
        dialog = xbmcgui.Dialog()
        search_term = dialog.input('Buscar contenido')
        if not search_term:
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
            
        # Redirigir para que Kodi recuerde el término si refresca la vista
        import xbmc
        new_params = params.copy()
        new_params['q'] = search_term
        search_url = build_url(base_url, new_params)
        xbmc.executebuiltin(f'Container.Update({search_url})')
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    xbmcplugin.setContent(handle, 'movies')  # Mostrar como contenido de video para ver posters
    
    # Normalizar búsqueda: quitar acentos, minúsculas y dividir en palabras
    search_norm = _normalize_title_for_match(search_term)
    search_words = search_norm.split()
    
    found_total = 0
    all_results = []
    
    # Si tras normalizar no queda nada (ej. solo símbolos), no buscar
    if not search_words:
        xbmcplugin.endOfDirectory(handle)
        return

    # Paginación
    page = int(params.get('page', 1))
    
    all_results = search_items_sql(search_term, limit=ITEMS_PER_PAGE + 1, offset=(page - 1) * ITEMS_PER_PAGE)
    has_next = len(all_results) > ITEMS_PER_PAGE
    all_results = all_results[:ITEMS_PER_PAGE]
    
    for item in all_results:
        found_total += 1
        itype = 'tvshow' if item.get('type') == 'tv' else 'movie'
        
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
            'mediatype': itype,
            'genre': genres,
            'cast': cast,
            'tmdb_id': item.get('tmdb_id')
        }
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {
            'poster': item.get('poster'), 
            'fanart': item.get('fanart'),
        }
        li.setArt({k: v for k, v in art.items() if v})
        
        if itype == 'movie':
            li.setProperty('IsPlayable', 'true')
            url_params = {'action': 'play', 'title': item['title'], 'key': item.get('key')}
            is_folder = False
        else:
            url_params = {'action': 'list_seasons', 'title': item['title']}
            is_folder = True
            
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, is_folder)
    
    if found_total == 0:
        no_results = xbmcgui.ListItem('Sin resultados')
        no_results.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(handle, '', no_results, False)
    
    if has_next:
        _add_next_page(handle, base_url, params, page)

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
    """Muestra 'Seguir viendo' con lógica Up Next (siguiente capítulo directo)."""
    import sqlite3, xbmcvfs
    
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.setPluginFanart(handle, FANART)
    
    po = get_cached_progress()
    hidden_items = po.get('hidden', [])
    manual_items = po.get('manual', {})
    
    played_keys = _get_played_keys()
    resume_points = _get_resume_points()
    
    from resources.lib.database import get_connection
    conn = get_connection()
    c = conn.cursor()
    
    display_items = []
    json_changed = False
    
    def _parse_sort_time(t_str):
        if not t_str: return 0.0
        try: return float(t_str)
        except: pass
        try:
            import time
            return time.mktime(time.strptime(str(t_str), "%Y-%m-%d %H:%M:%S"))
        except: return 0.0
    
    try:
        # --- 1. SERIES EN CURSO (Lógica Next Up) ---
        c.execute('SELECT "key", title, season, episode, tmdb_id, poster, fanart, clearlogo, overview, episode_title, episode_overview, still_path, links FROM items WHERE type="tv"')
        tv_rows = c.fetchall()
        
        series_data = {}
        for r in tv_rows:
            t = r['title']
            if not t: continue
            tn = _normalize_title_for_match(t)
            if tn in hidden_items: continue
            if tn not in series_data:
                series_data[tn] = {'title': t, 'episodes': [], 'poster': r['poster'], 'fanart': r['fanart'], 'clearlogo': r['clearlogo'], 'overview': r['overview']}
            series_data[tn]['episodes'].append(dict(r))
            
        for tn, s_data in series_data.items():
            eps = sorted(s_data['episodes'], key=lambda x: (int(x['season'] or 0), int(x['episode'] or 0)))
            bookmarked = []
            watched = []
            for ep in eps:
                ident = f"tv_{tn}_{ep['season']}_{ep['episode']}"
                if ident in resume_points: 
                    bookmarked.append(ep)
                elif ident in played_keys: 
                    watched.append(ep)
            
            target_ep = None
            if bookmarked:
                target_ep = bookmarked[-1]
            elif watched:
                last_watched = watched[-1]
                try:
                    idx = eps.index(last_watched)
                    if idx + 1 < len(eps): target_ep = eps[idx + 1]
                except: pass
            elif tn in manual_items:
                target_ep = eps[0] if eps else None
                
            if target_ep is None and tn in manual_items and watched:
                del po['manual'][tn]
                json_changed = True
                
            if target_ep:
                ident = f"tv_{tn}_{target_ep['season']}_{target_ep['episode']}"
                sort_time = "0.0"
                if ident in resume_points: sort_time = played_keys.get(ident, str(time.time()))
                elif watched:
                    last_ident = f"tv_{tn}_{watched[-1]['season']}_{watched[-1]['episode']}"
                    sort_time = played_keys.get(last_ident, str(time.time()))
                elif tn in manual_items: sort_time = str(manual_items[tn].get('added', 0))
                    
                display_items.append({
                    'type': 'episode',
                    'item': target_ep,
                    'series_info': s_data,
                    'tn': tn,
                    'sort_time': sort_time
                })
    except Exception as e:
        log(f"Choloretro: Error procesando Up Next series: {e}")

    try:
        # --- 2. PELÍCULAS ---
        c.execute('SELECT "key", title, year, poster, fanart, clearlogo, overview, links FROM items WHERE type="movie"')
        for r in c.fetchall():
            t = r['title']
            if not t: continue
            tn = _normalize_title_for_match(t)
            ident = f"movie_{tn}"
            
            if ident in hidden_items: continue
            is_manual = ident in manual_items
            is_resumed = ident in resume_points
            
            # FIX DEFINITIVO: Si está vista y no está a medias, se oculta ignorando el JSON corrupto.
            if ident in played_keys and not is_resumed: continue
            # Auto-limpieza del JSON: si está vista y no a medias, la eliminamos de Seguir Viendo.
            if ident in played_keys and not is_resumed:
                if is_manual:
                    del po['manual'][ident]
                    json_changed = True
                continue
            
            if is_manual or is_resumed:
                sort_time = played_keys.get(ident, str(time.time())) if is_resumed else str(manual_items[ident].get('added', 0))
                display_items.append({
                    'type': 'movie',
                    'item': dict(r),
                    'tn': tn,
                    'ident': ident,
                    'sort_time': sort_time
                })
    except Exception as e:
        log(f"Choloretro: Error procesando Up Next movies: {e}")
        
    conn.close()
    
    if json_changed:
        save_progress_override(po)
    
    display_items.sort(key=lambda x: _parse_sort_time(x['sort_time']), reverse=True)
    
    if not display_items:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        li.setProperty('IsPlayable', 'false')
        li.setArt({'icon': ADDON_ICON, 'fanart': FANART})
        xbmcplugin.addDirectoryItem(handle, '', li, False)
        xbmcplugin.endOfDirectory(handle)
        return
        
    for di in display_items:
        if di['type'] == 'episode':
            ep = di['item']
            series = di['series_info']
            tn = di['tn']
            season = ep['season']
            episode = ep['episode']
            
            ep_title = ep.get('episode_title') or ep.get('title') or f"Episodio {episode}"
            display_title = f"{series['title']} S{str(season).zfill(2)}E{str(episode).zfill(2)}"
            
            li = xbmcgui.ListItem(label=display_title)
            info = {
                'title': ep_title,
                'tvshowtitle': series['title'],
                'season': int(season) if str(season).isdigit() else None,
                'episode': int(episode) if str(episode).isdigit() else None,
                'plot': ep.get('episode_overview') or ep.get('overview') or series.get('overview', ''),
                'mediatype': 'episode'
            }
            
            ident = f"tv_{tn}_{season}_{episode}"
            is_watched = False
            if ident in played_keys:
                info['playcount'] = 1
                is_watched = True
            if ident in resume_points:
                info['resume_time'] = resume_points[ident]['time']
                info['resume_total'] = resume_points[ident]['total']
                try:
                    import xbmc
                    if int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0]) < 20:
                        li.setProperty('ResumeTime', str(info['resume_time']))
                        li.setProperty('TotalTime', str(info['resume_total']))
                except: pass
                
            _apply_meta(li, info)
            
            art = {'icon': ADDON_ICON, 'fanart': FANART}
            poster = ep.get('still_path') or ep.get('poster') or series.get('poster')
            if poster: art['poster'] = poster; art['thumb'] = poster
            fanart = ep.get('fanart') or series.get('fanart')
            if fanart: art['fanart'] = fanart
            clearlogo = ep.get('clearlogo') or series.get('clearlogo')
            if clearlogo: art['clearlogo'] = clearlogo; art['logo'] = clearlogo
            li.setArt(art)
            li.setProperty('IsPlayable', 'true')
            
            cm = generate_context_menu(base_url, 'tv', tn, series['title'], is_watched, watched_eps=1, total_eps=2)
            if cm: li.addContextMenuItems(cm)
            
            url = build_url(base_url, {'action': 'play', 'title': display_title, 'key': ep.get('key'), 'tvshowtitle': series['title'], 'season': season, 'episode': episode, 'tmdb': ep.get('tmdb_id')})
            
            xbmcplugin.addDirectoryItem(handle, url, li, False)
            
        else:
            m = di['item']
            tn = di['tn']
            ident = di['ident']
            
            li = xbmcgui.ListItem(label=m['title'])
            info = {
                'title': m['title'],
                'year': int(m['year']) if str(m.get('year', '')).isdigit() else 0,
                'plot': m['overview'],
                'mediatype': 'movie'
            }
            
            is_watched = False
            if ident in played_keys:
                info['playcount'] = 1
                is_watched = True
            if ident in resume_points:
                info['resume_time'] = resume_points[ident]['time']
                info['resume_total'] = resume_points[ident]['total']
                try:
                    import xbmc
                    if int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0]) < 20:
                        li.setProperty('ResumeTime', str(info['resume_time']))
                        li.setProperty('TotalTime', str(info['resume_total']))
                except: pass
                
            _apply_meta(li, info)
            
            art = {'icon': ADDON_ICON, 'fanart': FANART}
            if m.get('poster'): art['poster'] = m['poster']; art['thumb'] = m['poster']
            if m.get('fanart'): art['fanart'] = m['fanart']
            if m.get('clearlogo'): art['clearlogo'] = m['clearlogo']; art['logo'] = m['clearlogo']
            li.setArt(art)
            li.setProperty('IsPlayable', 'true')
            
            cm = generate_context_menu(base_url, 'movie', ident, m['title'], is_watched, item_key=ident)
            if cm: li.addContextMenuItems(cm)
            
            url = build_url(base_url, {'action': 'play', 'title': m['title'], 'key': m.get('key')})
            
            xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    xbmcplugin.endOfDirectory(handle)

def show_movies_by_title(base_url, handle, params):
    """Muestra películas agrupadas alfabéticamente por título."""
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    icon_path = os.path.join(ADDON_PATH, 'resources', 'media', 'peliculas.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    movies = get_all_items('movie')
    movies = [m for m in movies if not _is_animated_movie(m) and not _is_anime(m)]
    
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
    movies = [m for m in movies if not _is_animated_movie(m) and not _is_anime(m)]
    movies = [m for m in movies if m.get('title', '').upper().startswith(letter)]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        url_params = {'action': 'play', 'title': movie['title'], 'key': movie.get('key')}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    movies = [m for m in movies if not _is_animated_movie(m) and not _is_anime(m)]
    
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
    movies = [m for m in movies if not _is_animated_movie(m) and _has_genre(m, genre) and not _is_anime(m)]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        url_params = {'action': 'play', 'title': movie['title'], 'key': movie.get('key')}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    movies = [m for m in movies if not _is_animated_movie(m) and not _is_anime(m)]
    
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
    movies = [m for m in movies if not _is_animated_movie(m) and str(m.get('year', '')) == year and not _is_anime(m)]
    movies = sorted(movies, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(movies)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for movie in movies[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': movie.get('poster'), 'fanart': movie.get('fanart')}.items() if v}
        li.setArt(art)
        li.setProperty('IsPlayable', 'true')
        
        url_params = {'action': 'play', 'title': movie['title'], 'key': movie.get('key')}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, False)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    items = [i for i in items if not _is_animated_tvshow(i) and not _is_anime(i)]
    
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
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    
    xbmcplugin.setContent(handle, 'tvshows')
    letter = params.get('letter', 'A')
    
    items = get_tv_shows()
    items = [i for i in items if not _is_animated_tvshow(i) and not _is_anime(i)]
    items = [i for i in items if i.get('title', '').upper().startswith(letter)]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    items = [i for i in items if not _is_animated_tvshow(i) and not _is_anime(i)]
    
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
    items = [i for i in items if not _is_animated_tvshow(i) and _has_genre(i, genre) and not _is_anime(i)]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

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
    items = [i for i in items if not _is_animated_tvshow(i) and not _is_anime(i)]
    
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
    items = [i for i in items if not _is_animated_tvshow(i) and str(i.get('year', '')) == year and not _is_anime(i)]
    items = sorted(items, key=lambda x: x.get('title', ''))
    
    page = int(params.get('page', 1))
    total_items = len(items)
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE

    for item in items[start:end]:
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
        is_watched, watched_eps, total_eps = _inject_playback_state(info, li)
        _apply_meta(li, info)
        _apply_context_menu(base_url, li, info, is_watched, watched_eps, total_eps)
        
        art = {k: v for k, v in {'poster': item.get('poster'), 'fanart': item.get('fanart')}.items() if v}
        li.setArt(art)
        
        url_params = {'action': 'list_seasons', 'title': item['title']}
        url = build_url(base_url, url_params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)
    
    if end < total_items:
        _add_next_page(handle, base_url, params, page)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)