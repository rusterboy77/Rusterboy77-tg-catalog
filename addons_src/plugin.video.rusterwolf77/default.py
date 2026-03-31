# -*- coding: utf-8 -*-
import sys, xbmc, xbmcgui, xbmcplugin, xbmcaddon, urllib.parse, xbmcvfs
import json
import unicodedata, re, os, threading, time, base64
from resources.lib.player import is_elementum_installed, play_with_elementum, play_with_alldebrid, play_1fichier_with_alldebrid, play_with_realdebrid
from resources.lib.db import load_items_by_keys

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
# Resolver icono del addon (usar icon.png en la raíz o resources/media/icon.png si existe)
try:
    _addon_path = ADDON.getAddonInfo('path')
    if os.path.exists(os.path.join(_addon_path, 'icon.png')):
        ADDON_ICON = os.path.join(_addon_path, 'icon.png')
    elif os.path.exists(os.path.join(_addon_path, 'resources', 'media', 'icon.png')):
        ADDON_ICON = os.path.join(_addon_path, 'resources', 'media', 'icon.png')
    else:
        ADDON_ICON = ''
except Exception:
    ADDON_ICON = ''
# Prioritization features removed: addon will only load from cache.db

_PLAYED_KEYS = None

def _get_played_keys():
    global _PLAYED_KEYS
    if _PLAYED_KEYS is not None:
        return _PLAYED_KEYS
    
    _PLAYED_KEYS = {}
    import xbmc, xbmcvfs, os, glob, sqlite3, urllib.parse
    try:
        profile = xbmcvfs.translatePath('special://profile/')
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if db_candidates:
            db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            try:
                cur.execute("SELECT strFilename, lastPlayed FROM files WHERE strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND playCount > 0")
            except Exception:
                cur.execute("SELECT strFilename, NULL FROM files WHERE strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND playCount > 0")
            for row in cur.fetchall():
                try:
                    parsed = urllib.parse.urlparse(row[0])
                    qs = dict(urllib.parse.parse_qsl(parsed.query))
                    if 'key' in qs:
                        _PLAYED_KEYS[qs['key']] = row[1] if len(row) > 1 and row[1] else ""
                except Exception:
                    pass
            conn.close()
    except Exception as e:
        xbmc.log(f"RusterWolf: Error _get_played_keys: {e}", xbmc.LOGWARNING)
    return _PLAYED_KEYS

_RESUME_POINTS = None

def _get_resume_points():
    global _RESUME_POINTS
    if _RESUME_POINTS is not None:
        return _RESUME_POINTS
    
    _RESUME_POINTS = {}
    import xbmc, xbmcvfs, os, glob, sqlite3, urllib.parse
    try:
        profile = xbmcvfs.translatePath('special://profile/')
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if db_candidates:
            db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0]
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT f.strFilename, b.timeInSeconds, b.totalTimeInSeconds FROM bookmark b JOIN files f ON b.idFile = f.idFile WHERE f.strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND b.type = 1")
            for row in cur.fetchall():
                try:
                    parsed = urllib.parse.urlparse(row[0])
                    qs = dict(urllib.parse.parse_qsl(parsed.query))
                    if 'key' in qs:
                        _RESUME_POINTS[qs['key']] = {'time': float(row[1]), 'total': float(row[2])}
                except Exception:
                    pass
            conn.close()
    except Exception as e:
        xbmc.log(f"RusterWolf: Error _get_resume_points: {e}", xbmc.LOGWARNING)
    return _RESUME_POINTS

def build_url(query):
    import xbmc
    url = BASE_URL + '?' + urllib.parse.urlencode(query)
    try:
        debug = ADDON.getSettingBool('debug_logging')
    except Exception:
        debug = False
    if debug:
        xbmc.log(f"RusterWolf: build_url query={query} url={url}", xbmc.LOGWARNING)
    else:
        xbmc.log(f"RusterWolf: build_url query={query} url={url}", xbmc.LOGDEBUG)
    # Si es una URL de paginación (lista) intentar guardarla en el cache para
    # que router pueda recuperar los parámetros si Kodi luego invoca la
    # subcarpeta pasando sólo 'page'. Guardamos también '__last_filters' por acción.
    try:
        if isinstance(query, dict) and query.get('action') == 'list' and 'page' in query:
            try:
                profile_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}")
            except Exception:
                profile_dir = os.path.join(ADDON.getAddonInfo('path'), 'cache')
            # Para pagination cache usamos un directorio temporal para evitar persistir datos locales
            try:
                import os as _os
                temp_dir = _os.path.join(_os.environ.get('TMP', _os.environ.get('TEMP', _os.path.expanduser('~'))), f"rusterwolf_{ADDON.getAddonInfo('id')}")
                os.makedirs(temp_dir, exist_ok=True)
                profile_dir = temp_dir
            except Exception:
                pass
            try:
                os.makedirs(profile_dir, exist_ok=True)
            except Exception:
                pass
            cache_file = os.path.join(profile_dir, 'pagination_cache.json')
            data = {'entries': {}, '__last_filters': {}}
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as cf:
                        data = json.load(cf) or data
                except Exception:
                    data = {'entries': {}, '__last_filters': {}}
            entries = data.get('entries') or {}
            last_filters = data.get('__last_filters') or {}
            # Guardar esta URL -> query
            entries[url] = query
            # Mantener tamaño limitado
            if len(entries) > 200:
                keys = list(entries.keys())[-200:]
                entries = {k: entries[k] for k in keys}
            # actualizar last_filters
            try:
                act = query.get('action')
                flt = query.get('filter') or query.get('origin')
                if act and flt:
                    last_filters[act] = flt
            except Exception:
                pass
            data = {'entries': entries, '__last_filters': last_filters}
            try:
                with open(cache_file, 'w', encoding='utf-8') as cf:
                    json.dump(data, cf)
            except Exception:
                pass
    except Exception:
        pass
    return url



def normalize_title(s):
    """Normaliza títulos para comparación (sin acentos, minúsculas, sin puntuación)."""
    if not s:
        return ''
    s2 = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII')
    s2 = s2.lower()
    s2 = re.sub(r"^(the |la |el |los |las |un |una |el\s)", '', s2)
    s2 = re.sub(r"[^a-z0-9 ]+", ' ', s2)
    s2 = re.sub(r"\s+", ' ', s2).strip()
    return s2


def _read_items_per_page():
    try:
        v = ADDON.getSettingInt('items_per_page')
        if not v or v <= 0:
            return 24
        return int(v)
    except Exception:
        return 24

def _get_section_logo(section_key):
    """Retorna el path del clearlogo para una sección si existe."""
    if not section_key:
        return None
    try:
        logo_path = os.path.join(ADDON.getAddonInfo('path'), 'resources', 'media', f"{section_key}_logo_v2.png")
        if os.path.exists(logo_path):
            return logo_path
    except Exception:
        pass
    return None

def _is_valid_art_url(url):
    """Valida que la URL de imagen no sea solo la base de TMDB (evita error 404 en logs)."""
    if not url: return False
    if url.endswith('/original') or url.endswith('/w500') or url.endswith('/w185') or url.endswith('/w300'):
        return False
    return True

def _apply_art(li, item_dict, addon_fanart=None):
    """Helper mínimo para añadir arte extra si está disponible en el item.
    Añade keys: poster/thumb, fanart, clearlogo, banner, clearart.
    """
    try:
        art = {}
        if not isinstance(item_dict, dict):
            # Si no hay item_dict válido, al menos aplicar el fanart del addon
            if addon_fanart: art['fanart'] = addon_fanart
            if art:
                try: li.setArt(art)
                except Exception: pass
            return
        poster = item_dict.get('poster') or item_dict.get('poster_path') or ''
        if _is_valid_art_url(poster):
            art['poster'] = poster
            art['thumb'] = poster
        fanart = item_dict.get('fanart') or item_dict.get('backdrop_path') or ''
        if _is_valid_art_url(fanart):
            art['fanart'] = fanart
        # extra art metadata commonly used
        for k in ('clearlogo', 'banner', 'clearart'):
            v = item_dict.get(k)
            if _is_valid_art_url(v):
                art[k] = v
                # also expose common alias keys so skins that check 'logo' or 'icon' find them
                if k == 'clearlogo':
                    art['logo'] = v
                    art['icon'] = v
                if k == 'clearart' and 'icon' not in art:
                    art['icon'] = v
        # CAMBIO IMPORTANTE: Solo aplicar addon_fanart si NO hay fanart del item
        if 'fanart' not in art and addon_fanart:
            art['fanart'] = addon_fanart
        # CAMBIO: Asegurar que siempre se aplique el arte si hay algo que mostrar
        if art:
            try:
                li.setArt(art)
            except Exception:
                pass
    except Exception:
        # En caso de error, intentar al menos aplicar el fanart del addon
        art_fallback = {}
        if addon_fanart:
            art_fallback['fanart'] = addon_fanart
        if art_fallback:
            try: li.setArt(art_fallback)
            except Exception: pass
        pass

def _set_unique_ids(li, item_dict):
    """Configura los IDs únicos (TMDB) en el ListItem para que skins/helpers los detecten."""
    if not isinstance(item_dict, dict):
        return
    tmdb_id = item_dict.get('tmdb_id')
    if tmdb_id:
        sid = str(tmdb_id)
        try:
            li.getVideoInfoTag().setUniqueIDs({'tmdb': sid})
        except Exception:
            pass
        li.setProperty('tmdb_id', sid)

def _normalize_str(s):
    import unicodedata, re
    if not s:
        return ''
    s2 = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII')
    s2 = s2.lower().strip()
    s2 = re.sub(r'[^a-z0-9 ]+', ' ', s2)
    s2 = re.sub(r'\s+', ' ', s2).strip()
    return s2


def _get_item_type(it):
    # try top-level then parsed, normalize aliases (map 'series' -> 'tv')
    t = ''
    try:
        t = (it.get('type') or (it.get('parsed') or {}).get('type') or '')
    except Exception:
        t = ''
    t = str(t).lower() if t else ''
    if t == 'series':
        return 'tv'
    return t


def _get_item_title(it):
    try:
        return it.get('title') or (it.get('parsed') or {}).get('series') or (it.get('parsed') or {}).get('title') or ''
    except Exception:
        return ''


def _get_item_genres(it):
    try:
        g = it.get('genres') or (it.get('tmdb_top') and it.get('tmdb_top').get('genre_ids')) or []
        # Normalize: always return a list of dicts with 'id' and 'name' when possible
        out = []
        if not isinstance(g, list):
            return []
        for x in g:
            if isinstance(x, dict):
                # keep as-is if it has a name
                if 'name' in x:
                    out.append(x)
                elif 'id' in x:
                    gid = x.get('id')
                    name = TMDB_GENRE_MAP.get(int(gid), str(gid)) if gid is not None else str(x)
                    out.append({'id': gid, 'name': name})
            elif isinstance(x, int):
                name = TMDB_GENRE_MAP.get(int(x), str(x))
                out.append({'id': x, 'name': name})
            else:
                # string name
                out.append({'id': None, 'name': str(x)})
        return out
    except Exception:
        return []

def _is_item_premium(it):
    """Detecta si un item tiene la etiqueta de género 'Premium'."""
    for g in (_get_item_genres(it) or []):
        gname = (g.get('name') if isinstance(g, dict) and 'name' in g else str(g)).strip().lower()
        if gname == 'premium':
            return True
    return False

# Minimal TMDB genre id -> Spanish name mapping for common genres.
TMDB_GENRE_MAP = {
    28: 'Acción', 12: 'Aventura', 16: 'Animación', 35: 'Comedia', 80: 'Crimen',
    99: 'Documental', 18: 'Drama', 10751: 'Familiar', 14: 'Fantasía', 36: 'Histórico',
    27: 'Terror', 10402: 'Música', 9648: 'Misterio', 10749: 'Romance', 878: 'Ciencia ficción',
    10770: 'TV Movie', 53: 'Suspense', 10752: 'Bélica', 37: 'Western', 10759: 'Acción y Aventura',
    10765: 'Ciencia ficción y fantasía', 10766: 'Soap', 10767: 'Talk', 10768: 'Kids'
}


def _get_item_year(it):
    try:
        y = it.get('year') or (it.get('parsed') or {}).get('year') or ''
        if not y:
            # try tmdb_top first_air_date or release_date
            tm = it.get('tmdb_top') or {}
            y = (tm.get('first_air_date') or tm.get('release_date') or '')
            if isinstance(y, str) and len(y) >= 4:
                y = y[:4]
        return str(y)
    except Exception:
        return ''

def _apply_info_tag(li, info):
    try:
        tag = li.getVideoInfoTag()
        if info.get('title'):
            tag.setTitle(info.get('title'))
        if info.get('plot'):
            tag.setPlot(info.get('plot'))
        if info.get('year'):
            try:
                tag.setYear(int(info.get('year')))
            except Exception:
                pass
        if info.get('rating'):
            try:
                tag.setRating(float(info.get('rating')))
            except Exception:
                pass
        if info.get('mediatype'):
            try:
                tag.setMediaType(info.get('mediatype'))
            except Exception:
                pass
        if info.get('tvshowtitle'):
            try:
                tag.setTvShowTitle(info.get('tvshowtitle'))
            except Exception:
                pass
        if 'playcount' in info:
            try:
                tag.setPlaycount(int(info.get('playcount')))
            except Exception:
                pass
        if 'resume_time' in info and 'resume_total' in info:
            try:
                tag.setResumePoint(float(info['resume_time']), float(info['resume_total']))
            except Exception:
                pass
    except Exception as e:
        xbmc.log(f"RusterWolf: error aplicando InfoTagVideo: {e}", xbmc.LOGERROR)

def _create_item_and_url(it, addon_fanart, quality_filter=None):
    """Helper unificado para construir el ListItem, su metadata, su arte y su URL."""
    title = _get_item_title(it)
    mediatype_item = _get_item_type(it)
    m_type = 'tvshow' if mediatype_item in ('tv', 'series_documentary') else ('movie' if mediatype_item in ('movie', 'documentary') else None)

    info = {
        'title': title,
        'plot': it.get('overview') or '',
        'year': int(it.get('year')) if it.get('year') and str(it.get('year')).isdigit() else None,
        'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (_get_item_genres(it) or [])]),
        'rating': float(it.get('rating')) if it.get('rating') else None,
        'cast': it.get('cast') or [],
        'mediatype': m_type
    }

    if m_type == 'tvshow':
        info['tvshowtitle'] = title

    played_keys = _get_played_keys()
    resume_points = _get_resume_points()
    item_key = it.get('key')

    li = xbmcgui.ListItem(label=title)

    if m_type == 'movie' and item_key in played_keys:
        info['playcount'] = 1

    if item_key and item_key in resume_points:
        info['resume_time'] = resume_points[item_key]['time']
        info['resume_total'] = resume_points[item_key]['total']
        li.setProperty('ResumeTime', str(info['resume_time']))
        li.setProperty('TotalTime', str(info['resume_total']))

    if m_type == 'tvshow':
        try:
            from resources.lib.db import get_series_episodes
            eps = get_series_episodes(title)
            total_eps = len(eps)
            if total_eps > 0:
                watched_eps = sum(1 for e in eps if e.get('key') in played_keys)
                li.setProperty('TotalEpisodes', str(total_eps))
                li.setProperty('WatchedEpisodes', str(watched_eps))
                li.setProperty('UnWatchedEpisodes', str(total_eps - watched_eps))
                if watched_eps == total_eps:
                    info['playcount'] = 1
        except Exception:
            pass

    _apply_info_tag(li, info)
    try:
        safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
        li.setInfo('video', safe_info)
    except Exception: pass

    try: _apply_art(li, it, addon_fanart)
    except Exception: pass
    
    _set_unique_ids(li, it)
    cm = []

    if mediatype_item in ('tv', 'series_documentary'):
        url_params = {'action': 'list_seasons', 'series': title}
        if quality_filter: url_params['target_quality'] = quality_filter
        url = build_url(url_params)
        is_folder = True
        add_url = build_url({'action': 'add_watchlist', 'wtype': 'tv', 'val': title, 'title': title})
        cm.append(('Añadir a Favoritos', f'RunPlugin({add_url})'))
    else:
        li.setProperty('IsPlayable', 'true')
        li.setMimeType('application/x-bittorrent')
        item_key = it.get('key') # La clave del item, no de la fuente
        q_params = {'action': 'select', 'key': item_key}
        if quality_filter: q_params['target_quality'] = quality_filter
        url = build_url(q_params)
        is_folder = False
        if item_key:
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'movie', 'val': item_key, 'title': title})
            cm.append(('Añadir a Favoritos', f'RunPlugin({add_url})'))
            
    if cm: li.addContextMenuItems(cm)
    return li, url, is_folder

# --- Funciones para Watchlist (Seguir Viendo Manual) ---
def get_watchlist_file():
    try:
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        if not os.path.exists(profile_dir): os.makedirs(profile_dir)
        return os.path.join(profile_dir, 'watchlist.json')
    except: return ''

def load_watchlist():
    wf = get_watchlist_file()
    if os.path.exists(wf):
        try:
            with open(wf, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_watchlist(data):
    wf = get_watchlist_file()
    if wf:
        try:
            with open(wf, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

def action_add_watchlist(params):
    wtype = params.get('wtype')
    val = params.get('val')
    title = params.get('title')
    if not wtype or not val: return
    wl = load_watchlist()
    uid = f"{wtype}_{val}"
    wl[uid] = {'wtype': wtype, 'val': val, 'title': title, 'added': time.time()}
    save_watchlist(wl)
    xbmcgui.Dialog().notification('RusterWolf', f'{title} añadido a Favoritos')

def action_remove_watchlist(params):
    uid = params.get('uid')
    wl = load_watchlist()
    if uid in wl:
        del wl[uid]
        save_watchlist(wl)
        xbmcgui.Dialog().notification('RusterWolf', 'Eliminado de Favoritos')
        xbmc.executebuiltin('Container.Refresh')
# --------------------------------------------------------


def list_root():
    items = [
        ('Novedades', {'action':'novedades_menu'}),
        ('Favoritos', {'action':'favorites'}),
        ('Seguir Viendo...', {'action':'continue_watching'}), 
        ('Películas', {'action':'movie_menu'}),
        ('Series TV', {'action':'tv_menu'}),
        ('Documentales', {'action':'documentary_main_menu'}),
        ('Buscar', {'action':'search'}),
        ('Ajustes', {'action':'settings'}),
    ]
    import xbmc
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    default_icon = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    
    # CAMBIO: Establecer el tipo de contenido para que Kodi muestre el fanart
    xbmcplugin.setContent(HANDLE, 'files')
    
    for label, params in items:
        li = xbmcgui.ListItem(label)
        # CAMBIO: Usar InfoTagVideo para establecer metadata completa
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        
        # Lógica de iconos personalizados
        # Normalizar etiqueta: minúsculas, sin acentos, espacios a guiones bajos
        safe_label = ''.join(c for c in unicodedata.normalize('NFD', label) if unicodedata.category(c) != 'Mn')
        safe_label = safe_label.lower().replace('...', '').strip().replace(' ', '_')
        if safe_label == 'zona_premium':
            icon_name = "zona_premium_v3.png"
        else:
            icon_name = f"{safe_label}_v2.png"
        custom_icon_path = os.path.join(addon_path, 'resources', 'media', icon_name)
        icon_to_use = custom_icon_path if os.path.exists(custom_icon_path) else default_icon

        art_dict = {'fanart': addon_fanart, 'icon': icon_to_use, 'thumb': icon_to_use}
        section_logo = _get_section_logo(safe_label)
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo

        try:
            li.setArt(art_dict)
        except Exception:
            pass
        
        url = build_url(params)
        xbmc.log(f"RusterWolf: list_root label={label} params={params} url={url}", xbmc.LOGWARNING)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    
    # CAMBIO: Establecer el fanart del plugin también
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def premium_menu():
    """Submenú para la Zona Premium."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
        
    entries = [
        ('Películas Premium', {'action': 'premium_movie_menu'}),
        ('Series Premium', {'action': 'premium_tv_menu'})
    ]
    
    xbmcplugin.setContent(HANDLE, 'files')
    section_logo = _get_section_logo('zona_premium')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        
        if 'Películas' in label:
            icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas_v2.png')
        else:
            icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv_v2.png')
            
        if not os.path.exists(icon_path):
            icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
            
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def premium_movie_menu():
    """Submenú para Películas Premium."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Novedades (Premium)', {'action': 'novedades', 'sub': 'movies', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Título', {'action': 'list', 'filter': 'movie', 'group': 'letter', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Colecciones', {'action': 'list', 'filter': 'movie', 'group': 'collection', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Género', {'action': 'list', 'filter': 'movie', 'group': 'genre', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'group': 'quality', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Año', {'action': 'list', 'filter': 'movie', 'group': 'year', 'base_genre': 'Premium', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('peliculas')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle(label)
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def premium_tv_menu():
    """Submenú para Series Premium."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Novedades (Premium)', {'action': 'novedades', 'sub': 'series', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Título', {'action': 'list', 'filter': 'tv', 'group': 'letter', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Género', {'action': 'list', 'filter': 'tv', 'group': 'genre', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'group': 'quality', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Año', {'action': 'list', 'filter': 'tv', 'group': 'year', 'base_genre': 'Premium', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('series_tv')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle(label)
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def novedades_menu():
    """Submenú para Novedades: accesos directos a películas y series recientes."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'novedades_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    
    # Usar 'action': 'novedades' con el parámetro 'sub' correcto
    entries = [
        ('Novedades (Películas)', {
            'action': 'novedades',  # ← Usar la acción que ya existe
            'sub': 'movies',        # ← Parámetro que espera la función novedades()
            'page': 1
        }),
        ('Novedades (Series)', {
            'action': 'novedades',
            'sub': 'series',        # ← Parámetro que espera la función novedades()
            'page': 1
        })
    ]
    
    xbmcplugin.setContent(HANDLE, 'files')
    section_logo = _get_section_logo('novedades')
    
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)
    


def continue_watching():
    """Lista items a medio reproducir usando bookmarks de Kodi (MyVideos*.db).

    Implementación mínima y segura:
    - Lee la tabla `bookmark` y `files.strFilename` de la DB de Kodi más reciente.
    - Si `strFilename` es una URL del plugin (plugin://...), la usa como objetivo de reproducción.
    - Presenta hasta 50 entradas. Manejo conservador de errores.
    """
    import xbmc, xbmcgui
    import sqlite3, glob, urllib.parse

    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'seguir_viendo_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')

    xbmcplugin.setContent(HANDLE, 'movies')

    section_logo = _get_section_logo('seguir_viendo')

    # 1.5. Series en progreso (vistas parcialmente pero no completadas)
    played_keys = _get_played_keys()
    
    try:
        played_items = load_items_by_keys(list(played_keys.keys()))
    except Exception:
        played_items = []

    series_progress = {}
    for it in played_items:
        if _get_item_type(it) in ('tv', 'series_documentary'):
            raw_title = _get_item_title(it)
            title_norm = normalize_title(raw_title)
            if not title_norm: continue
            
            if title_norm not in series_progress:
                series_progress[title_norm] = {'total': 0, 'watched': 0, 'raw_title': raw_title, 'rep': it, 'last_played': ''}
            
            series_progress[title_norm]['total'] += 1
            item_key = it.get('key')
            if item_key and item_key in played_keys:
                series_progress[title_norm]['watched'] += 1
                lp = played_keys[item_key]
                if lp and lp > series_progress[title_norm]['last_played']:
                    series_progress[title_norm]['last_played'] = lp
                
            if bool(it.get('poster')) and not bool(series_progress[title_norm]['rep'].get('poster')):
                series_progress[title_norm]['rep'] = it

    from resources.lib.db import count_episodes_for_series
    in_progress_series = []
    for data in series_progress.values():
        total_eps = count_episodes_for_series(data['raw_title'])
        if 0 < data['watched'] < total_eps:
            data['total'] = total_eps
            in_progress_series.append(data)
    
    in_progress_series.sort(key=lambda x: x['raw_title'])
    in_progress_series.sort(key=lambda x: x['last_played'] or '', reverse=True)
    for data in in_progress_series:
        rep = data['rep']
        raw_title = data['raw_title']
        
        li = xbmcgui.ListItem(label=raw_title)
        _apply_art(li, rep, addon_fanart)
        
        info = {'title': raw_title, 'plot': rep.get('overview'), 'mediatype': 'tvshow'}
        li.setProperty('TotalEpisodes', str(data['total']))
        li.setProperty('WatchedEpisodes', str(data['watched']))
        li.setProperty('UnWatchedEpisodes', str(data['total'] - data['watched']))
        _apply_info_tag(li, info)
        
        url = build_url({'action': 'list_seasons', 'series': raw_title})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)

    # localizar la DB de Kodi (MyVideos*.db) dentro de special://profile/Database
    try:
        try:
            profile = xbmcvfs.translatePath('special://profile/')
        except Exception:
            profile = ''
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if not db_candidates:
            db_candidates = glob.glob(os.path.join(db_dir, '*.db'))
        db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0] if db_candidates else None
    except Exception as e:
        xbmc.log(f"RusterWolf: error localizando Database de Kodi: {e}", xbmc.LOGERROR)
        db_path = None

    bookmarks = []
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT b.idBookmark, b.idFile, b.timeInSeconds, b.totalTimeInSeconds, f.strFilename FROM bookmark b JOIN files f ON b.idFile = f.idFile WHERE f.strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND b.type = 1 ORDER BY b.idBookmark DESC LIMIT 200")
            rows = cur.fetchall()
            for row in rows:
                try:
                    idBookmark, idFile, timeInSeconds, totalTimeInSeconds, strFilename = row
                    bookmarks.append({'idBookmark': idBookmark, 'idFile': idFile, 'time': timeInSeconds, 'total': totalTimeInSeconds, 'filename': strFilename})
                except Exception:
                    continue
            conn.close()
        except Exception as e:
            xbmc.log(f"RusterWolf: error leyendo bookmarks de {db_path}: {e}", xbmc.LOGERROR)

    # Si no hay bookmarks ni series en progreso, informar y cerrar el contenedor
    if not bookmarks and not in_progress_series:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        try:
            info_tag = li.getVideoInfoTag(); info_tag.setTitle('No hay contenido en progreso')
        except Exception:
            pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        xbmcplugin.addDirectoryItem(HANDLE, '', li, isFolder=False)
        xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, updateListing=False, cacheToDisc=False)
        return

    shown = 0
    for bm in bookmarks[:50]:
        try:
            filename = bm.get('filename') or ''
            display_title = filename
            catalog_item = None

            # intentar resolver item desde URL plugin (key o index)
            try:
                parsed = urllib.parse.urlparse(filename)
                if parsed.scheme == 'plugin' or (parsed.scheme in ('http', 'https') and 'plugin.video.rusterwolf77' in filename):
                    qs = urllib.parse.parse_qs(parsed.query)
                    # priorizar key
                    try:
                        if 'key' in qs:
                            k = qs.get('key')[0]
                            # intentar carga rápida por key
                            try:
                                items = load_items_by_keys([k]) or []
                                catalog_item = items[0] if items else None
                            except Exception:
                                catalog_item = None
                    except Exception:
                        catalog_item = None
            except Exception:
                catalog_item = None

            if catalog_item:
                display_title = catalog_item.get('title') or display_title
                try:
                    xbmc.log(f"RusterWolf: continue_watching matched catalog item key={catalog_item.get('key')} title={catalog_item.get('title')}", xbmc.LOGDEBUG)
                except Exception:
                    pass
            else:
                continue # Omitir si el archivo ya no existe en nuestra BD local

            li = xbmcgui.ListItem(label=display_title)
            try:
                # aplicar arte directamente
                art = {'fanart': addon_fanart}
                if isinstance(catalog_item, dict):
                    poster = catalog_item.get('poster') or catalog_item.get('poster_path') or ''
                    if poster:
                        art['poster'] = poster
                        art['thumb'] = poster
                    fanart = catalog_item.get('fanart') or catalog_item.get('backdrop_path') or ''
                    if fanart:
                        art['fanart'] = fanart
                    clearlogo = catalog_item.get('clearlogo') or catalog_item.get('logo') or ''
                    if clearlogo:
                        art['clearlogo'] = clearlogo
                        art['logo'] = clearlogo
                try:
                    li.setArt(art)
                except Exception:
                    pass
            except Exception:
                try: li.setArt(art)
                except Exception: pass

            # aplicar info tag enriquecido si hay item
            try:
                if isinstance(catalog_item, dict):
                    tag = li.getVideoInfoTag()
                    if catalog_item.get('title'):
                        tag.setTitle(catalog_item.get('title'))
                    plot = catalog_item.get('overview') or catalog_item.get('episode_overview')
                    if plot:
                        tag.setPlot(plot)
                    try:
                        year = catalog_item.get('year')
                        if year:
                            tag.setYear(int(year))
                    except Exception:
                        pass
                    try:
                        if catalog_item.get('rating'):
                            tag.setRating(float(catalog_item.get('rating')))
                    except Exception:
                        pass
                    try:
                        xbmc.log(f"RusterWolf: continue_watching applied info for key={catalog_item.get('key')}", xbmc.LOGDEBUG)
                    except Exception:
                        pass
            except Exception:
                pass
            li.setProperty('IsPlayable', 'true')

            play_url = filename or ''
            if play_url:
                xbmcplugin.addDirectoryItem(HANDLE, play_url, li, False)
            else:
                xbmcplugin.addDirectoryItem(HANDLE, '', li, False)

            shown += 1
            if shown >= 50:
                break
        except Exception as e:
            xbmc.log(f"RusterWolf: error mostrando bookmark: {e}", xbmc.LOGERROR)

    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True, updateListing=False, cacheToDisc=True)
    return

def favorites_menu():
    """Muestra los ítems añadidos a Favoritos manualmente."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'favoritos_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')

    xbmcplugin.setContent(HANDLE, 'movies')
    section_logo = _get_section_logo('favoritos')

    wl = load_watchlist()
    if not wl:
        li = xbmcgui.ListItem(label='No hay elementos en Favoritos')
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle('No hay elementos en Favoritos')
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo: art_dict['clearlogo'] = section_logo; art_dict['logo'] = section_logo
        try: li.setArt(art_dict)
        except Exception: pass
        xbmcplugin.addDirectoryItem(HANDLE, '', li, isFolder=False)
        xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, updateListing=False, cacheToDisc=False)
        return

    for uid, witem in sorted(wl.items(), key=lambda x: x[1].get('added', 0), reverse=True):
        try:
            wtype = witem.get('wtype')
            val = witem.get('val')
            wtitle = witem.get('title')
            
            li = None
            url = None
            isFolder = True
            
            if wtype == 'tv':
                from resources.lib.db import get_series_representative
                rep = get_series_representative(val)
                if not rep: 
                    li = xbmcgui.ListItem(label=wtitle)
                    _apply_info_tag(li, {'title': wtitle, 'mediatype': 'tvshow'})
                else:
                    li = xbmcgui.ListItem(label=rep.get('title') or wtitle)
                    _apply_art(li, rep, addon_fanart)
                    _apply_info_tag(li, {'title': rep.get('title'), 'plot': rep.get('overview'), 'mediatype': 'tvshow'})
                url = build_url({'action': 'list_seasons', 'series': val})
            
            elif wtype == 'movie':
                found = load_items_by_keys([val])
                if found:
                    it = found[0]
                    li = xbmcgui.ListItem(label=it.get('title'))
                    _apply_art(li, it, addon_fanart)
                    _apply_info_tag(li, {'title': it.get('title'), 'plot': it.get('overview'), 'mediatype': 'movie'})
                    url = build_url({'action': 'select', 'key': val})
                    isFolder = False
                else:
                    li = xbmcgui.ListItem(label=wtitle)
                    url = build_url({'action': 'select', 'key': val})
                    isFolder = False
            
            if li and url:
                cm = []
                rm_url = build_url({'action': 'remove_watchlist', 'uid': uid})
                cm.append(('Quitar de Favoritos', f'RunPlugin({rm_url})'))
                li.addContextMenuItems(cm)
                xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder)
        except Exception as e:
            xbmc.log(f"RusterWolf: error en favoritos item: {e}", xbmc.LOGERROR)
            
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)
    

def movie_menu():
    """Submenú para Películas: por título, por género, por año, novedades."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'movie', 'group': 'letter', 'origin': 'movie'}),
        ('Colecciones', {'action': 'list', 'filter': 'movie', 'group': 'collection', 'origin': 'movie'}),
        ('Género', {'action': 'list', 'filter': 'movie', 'group': 'genre', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'group': 'quality', 'origin': 'movie'}),
        ('Año', {'action': 'list', 'filter': 'movie', 'group': 'year', 'origin': 'movie'}),
        ('Novedades (Películas)', {'action': 'novedades', 'sub': 'movies', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('peliculas')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)


def tv_menu():
    """Submenú para Series: por título, por género, por año, novedades."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'tv', 'group': 'letter', 'origin': 'tv'}),
        ('Género', {'action': 'list', 'filter': 'tv', 'group': 'genre', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'group': 'quality', 'origin': 'tv'}),
        ('Año', {'action': 'list', 'filter': 'tv', 'group': 'year', 'origin': 'tv'}),
        ('Novedades (Series)', {'action': 'novedades', 'sub': 'series', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('series_tv')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def documentary_main_menu():
    """Submenú principal para Documentales (agrupa Películas Documentales y Series Documentales)."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Documentales', {'action':'documentary_menu'}),
        ('Series Documental', {'action':'series_documentary_menu'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle(label)
        except Exception: pass
        
        if label == 'Series Documental':
            icon_path = os.path.join(addon_path, 'resources', 'media', 'series_documental_v2.png')
            section_logo = _get_section_logo('series_documental')
        else:
            icon_path = os.path.join(addon_path, 'resources', 'media', 'documentales_v2.png')
            section_logo = _get_section_logo('documentales')
            
        if not os.path.exists(icon_path):
            icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
            
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo: art_dict['clearlogo'] = section_logo; art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def documentary_menu():
    """Submenú para Documentales."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'movie', 'genre': 'Documental', 'group': 'letter', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'genre': 'Documental', 'group': 'quality', 'origin': 'movie'}),
        ('Novedades', {'action': 'novedades', 'sub': 'documentary', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'documentales_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('documentales')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def series_documentary_menu():
    """Submenú para Series Documental."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'tv', 'genre': 'Documental', 'group': 'letter', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'genre': 'Documental', 'group': 'quality', 'origin': 'tv'}),
        ('Novedades', {'action': 'novedades', 'sub': 'series_documentary', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_documental_v2.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    section_logo = _get_section_logo('series_documental')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        li.setArt(art_dict)
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)


def list_genres(filter_type=None, original_params=None):
    """Lista géneros usando una lista estática para no saturar memoria RAM."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    # Usar géneros de TMDB fijos para carga instantánea
    genres_list = ['Acción', 'Animación', 'Aventura', 'Bélica', 'Ciencia ficción', 'Comedia', 'Crimen', 'Documental', 'Drama', 'Familia', 'Fantasía', 'Historia', 'Misterio', 'Música', 'Romance', 'Suspense', 'Terror', 'Western']

    if not filter_type:
        filter_type = 'movie'
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    icon_map = {
        'movie': 'peliculas_v2.png',
        'tv': 'series_tv_v2.png',
        'documentary': 'documentales_v2.png',
        'series_documentary': 'series_documental_v2.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    logo_map = {
        'movie': 'peliculas', 'tv': 'series_tv',
        'documentary': 'documentales', 'series_documentary': 'series_documental'
    }
    section_logo = _get_section_logo(logo_map.get(filter_type, ''))

    xbmcplugin.setContent(HANDLE, 'files')
    for gname in sorted(genres_list):
        li = xbmcgui.ListItem(label=gname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(gname)
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        # pass the real genre name so matching can be done by substring on the DB side
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'genre': gname}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        url = build_url(url_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)


def list_years(filter_type=None, original_params=None):
    """Listar años consultando eficientemente la DB."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    if not filter_type:
        filter_type = 'movie'
        
    from resources.lib.db import get_years
    years = get_years(filter_type)
    
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')

    icon_map = {
        'movie': 'peliculas_v2.png',
        'tv': 'series_tv_v2.png',
        'documentary': 'documentales_v2.png',
        'series_documentary': 'series_documental_v2.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    logo_map = {
        'movie': 'peliculas', 'tv': 'series_tv',
        'documentary': 'documentales', 'series_documentary': 'series_documental'
    }
    section_logo = _get_section_logo(logo_map.get(filter_type, ''))

    xbmcplugin.setContent(HANDLE, 'files')
    for y in years:
        li = xbmcgui.ListItem(label=f'Año {y}')
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(f'Año {y}')
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'year': y}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        url = build_url(url_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def list_qualities(filter_type=None, genre_filter=None, original_params=None):
    """Lista estática de calidades para no saturar memoria RAM."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    qualities = ['4K', '1080p', '720p', 'MicroHD', 'BluRay', 'HDTV']

    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    # Usar icono por defecto o mapeado
    icon_map = {
        'movie': 'peliculas_v2.png',
        'tv': 'series_tv_v2.png',
        'documentary': 'documentales_v2.png',
        'series_documentary': 'series_documental_v2.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    
    logo_map = {
        'movie': 'peliculas', 'tv': 'series_tv',
        'documentary': 'documentales', 'series_documentary': 'series_documental'
    }
    section_logo = _get_section_logo(logo_map.get(filter_type, ''))

    xbmcplugin.setContent(HANDLE, 'files')
    for qname in qualities:
        li = xbmcgui.ListItem(label=qname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(qname)
        except Exception:
            pass
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        # Construir URL con el filtro de calidad
        q_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'quality': qname}
        if genre_filter and genre_filter.lower() != 'premium':
            q_params['genre'] = genre_filter
        if is_premium_req:
            q_params['base_genre'] = 'Premium'
        url = build_url(q_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def list_letters(filter_type=None, genre_filter=None, original_params=None):
    """Lista letras iniciales consultando la DB eficientemente."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    from resources.lib.db import get_letters
    letters = get_letters(filter_type)

    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    icon_map = {
        'movie': 'peliculas_v2.png',
        'tv': 'series_tv_v2.png',
        'documentary': 'documentales_v2.png',
        'series_documentary': 'series_documental_v2.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    
    logo_map = {
        'movie': 'peliculas', 'tv': 'series_tv',
        'documentary': 'documentales', 'series_documentary': 'series_documental'
    }
    section_logo = _get_section_logo(logo_map.get(filter_type, ''))

    xbmcplugin.setContent(HANDLE, 'files')
    for letter in letters:
        li = xbmcgui.ListItem(label=letter)
        try: li.getVideoInfoTag().setTitle(letter)
        except Exception: pass
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try: li.setArt(art_dict)
        except Exception: pass
        
        q_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'letter': letter}
        if genre_filter and genre_filter.lower() != 'premium': q_params['genre'] = genre_filter
        if is_premium_req: q_params['base_genre'] = 'Premium'
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_params), li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def list_collections(filter_type=None, original_params=None, page=1):
    """Lista colecciones usando consulta SQL paginada."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    from resources.lib.db import get_collections_paginated
    per_page = _read_items_per_page()
    offset = (page - 1) * per_page
    
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas_v2.png')
    if not os.path.exists(icon_path): icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')

    xbmcplugin.setContent(HANDLE, 'movies')
    
    collections = get_collections_paginated(filter_type, limit=per_page + 1, offset=offset)
    has_next_page = len(collections) > per_page
    page_cols = collections[:per_page]
    
    for col_data in page_cols:
        c_name = col_data['name']
        li = xbmcgui.ListItem(label=c_name)
        try: li.getVideoInfoTag().setTitle(c_name)
        except Exception: pass
        
        art_dict = {'fanart': col_data['fanart'] or addon_fanart, 'icon': icon_path}
        if col_data['poster']:
            art_dict['thumb'] = col_data['poster']
            art_dict['poster'] = col_data['poster']
        else: art_dict['thumb'] = icon_path
            
        if col_data['clearlogo']:
            art_dict['clearlogo'] = col_data['clearlogo']
            art_dict['logo'] = col_data['clearlogo']
            
        try: li.setArt(art_dict)
        except Exception: pass
        
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'collection': c_name}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        xbmcplugin.addDirectoryItem(HANDLE, build_url(url_params), li, True)
        
    q_base = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'group': 'collection'}
    if is_premium_req: q_base['base_genre'] = 'Premium'

    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = q_base.copy()
        q_prev['page'] = page - 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_prev), li_prev, True)

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = q_base.copy()
        q_next['page'] = page + 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_next), li_next, True)
        
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def list_items(filter_type=None, page=1, action_name=None, group_by=None, genre_filter=None, year_filter=None, quality_filter=None, letter_filter=None, collection_filter=None, original_params=None):
    xbmc.log(f"RusterWolf DEBUG: === list_items CALL === filter={filter_type} page={page}", xbmc.LOGWARNING)
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    is_premium_req = False
    if genre_filter and genre_filter.lower() == 'premium':
        is_premium_req = True
    try:
        if original_params and original_params.get('base_genre', '').lower() == 'premium':
            is_premium_req = True
    except Exception: pass
    
    if not filter_type and group_by in ('genre', 'year', 'quality', 'letter', 'collection'):
        try:
            li_movie = xbmcgui.ListItem('Películas')
            art_m = {'fanart': addon_fanart}
            logo_m = _get_section_logo('peliculas')
            if logo_m: art_m['clearlogo'] = logo_m; art_m['logo'] = logo_m
            li_movie.setArt(art_m)
            url_movie = build_url({'action': 'list', 'filter': 'movie', 'group': group_by})
            xbmcplugin.addDirectoryItem(HANDLE, url_movie, li_movie, True)

            li_tv = xbmcgui.ListItem('Series')
            art_t = {'fanart': addon_fanart}
            logo_t = _get_section_logo('series_tv')
            if logo_t: art_t['clearlogo'] = logo_t; art_t['logo'] = logo_t
            li_tv.setArt(art_t)
            url_tv = build_url({'action': 'list', 'filter': 'tv', 'group': group_by})
            xbmcplugin.addDirectoryItem(HANDLE, url_tv, li_tv, True)
            xbmcplugin.endOfDirectory(HANDLE)
            return
        except Exception: pass

    if filter_type is None and (genre_filter or year_filter or quality_filter or letter_filter):
        try:
            li_movie = xbmcgui.ListItem('Películas')
            art_m = {'fanart': addon_fanart}
            logo_m = _get_section_logo('peliculas')
            if logo_m: art_m['clearlogo'] = logo_m; art_m['logo'] = logo_m
            li_movie.setArt(art_m)
            url_movie = build_url({'action': 'list', 'filter': 'movie', 'genre': genre_filter, 'year': year_filter, 'quality': quality_filter, 'letter': letter_filter})
            xbmcplugin.addDirectoryItem(HANDLE, url_movie, li_movie, True)

            li_tv = xbmcgui.ListItem('Series')
            art_t = {'fanart': addon_fanart}
            logo_t = _get_section_logo('series_tv')
            if logo_t: art_t['clearlogo'] = logo_t; art_t['logo'] = logo_t
            li_tv.setArt(art_t)
            url_tv = build_url({'action': 'list', 'filter': 'tv', 'genre': genre_filter, 'year': year_filter, 'quality': quality_filter, 'letter': letter_filter})
            xbmcplugin.addDirectoryItem(HANDLE, url_tv, li_tv, True)
            xbmcplugin.endOfDirectory(HANDLE)
            return
        except Exception: pass

    used_filter = filter_type
    try:
        if not used_filter and isinstance(original_params, dict):
            used_filter = original_params.get('filter') or original_params.get('origin')
    except Exception: pass

    if group_by == 'genre': return list_genres(filter_type=used_filter, original_params=original_params)
    if group_by == 'year': return list_years(filter_type=used_filter, original_params=original_params)
    if group_by == 'quality': return list_qualities(filter_type=used_filter, genre_filter=genre_filter, original_params=original_params)
    if group_by == 'letter': return list_letters(filter_type=used_filter, genre_filter=genre_filter, original_params=original_params)
    if group_by == 'collection': return list_collections(filter_type=used_filter, original_params=original_params, page=page)

    from resources.lib.db import get_filtered_items
    per_page = _read_items_per_page()
    offset = (page - 1) * per_page
    limit = per_page + 1 # +1 para saber si hay página siguiente

    results = get_filtered_items(
        filter_type=used_filter,
        is_premium_req=is_premium_req,
        genre=genre_filter,
        year=year_filter,
        quality=quality_filter,
        letter=letter_filter,
        collection=collection_filter,
        sort_by='title',
        limit=limit,
        offset=offset
    )

    has_next_page = len(results) > per_page
    page_items = results[:per_page]

    if used_filter in ('tv', 'series_documentary'):
        try: xbmcplugin.setContent(HANDLE, 'tvshows')
        except: pass
    elif used_filter in ('movie', 'documentary'):
        try: xbmcplugin.setContent(HANDLE, 'movies')
        except: pass

    for it in page_items:
        li, url, is_folder = _create_item_and_url(it, addon_fanart, quality_filter)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)

    base_action = action_name or 'list'
    q_base = {'action': base_action}
    if used_filter: q_base['filter'] = used_filter
    if group_by: q_base['group'] = group_by
    if genre_filter: q_base['genre'] = genre_filter
    if year_filter: q_base['year'] = year_filter
    if quality_filter: q_base['quality'] = quality_filter
    if is_premium_req: q_base['base_genre'] = 'Premium'
    if letter_filter: q_base['letter'] = letter_filter
    if collection_filter: q_base['collection'] = collection_filter

    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = q_base.copy()
        q_prev['page'] = page - 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_prev), li_prev, True)

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = q_base.copy()
        q_next['page'] = page + 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_next), li_next, True)

    xbmcplugin.endOfDirectory(HANDLE)

def novedades(page=1, sub=None, original_params=None):
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')

    used_filter = None
    if sub == 'movies': used_filter = 'movie'
    elif sub == 'series': used_filter = 'tv'
    elif sub == 'documentary': used_filter = 'documentary'
    elif sub == 'series_documentary': used_filter = 'series_documentary'

    is_premium_req = False
    if original_params and original_params.get('base_genre', '').lower() == 'premium':
        is_premium_req = True

    from resources.lib.db import get_filtered_items
    per_page = _read_items_per_page()
    offset = (page - 1) * per_page
    limit = per_page + 1

    results = get_filtered_items(
        filter_type=used_filter,
        is_premium_req=is_premium_req,
        sort_by='date_added',
        limit=limit,
        offset=offset
    )

    has_next_page = len(results) > per_page
    page_items = results[:per_page]

    if used_filter in ('tv', 'series_documentary'):
        try: xbmcplugin.setContent(HANDLE, 'tvshows')
        except: pass
    elif used_filter in ('movie', 'documentary'):
        try: xbmcplugin.setContent(HANDLE, 'movies')
        except: pass

    for it in page_items:
        li, url, is_folder = _create_item_and_url(it, addon_fanart)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)

    base_q = {'action': 'novedades'}
    if sub: base_q['sub'] = sub
    if is_premium_req: base_q['base_genre'] = 'Premium'

    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = base_q.copy()
        q_prev['page'] = page - 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_prev), li_prev, True)

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = base_q.copy()
        q_next['page'] = page + 1
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_next), li_next, True)

    xbmcplugin.endOfDirectory(HANDLE)

def list_seasons(series, target_quality=None):
    """Lista las temporadas disponibles para una serie (por título de serie)."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    try:
        from resources.lib.db import get_series_episodes
        catalog = get_series_episodes(series)
    except Exception:
        catalog = []
    seasons = {}
    for it in catalog:
        season = str(it.get('season') or '')
        seasons.setdefault(season, []).append(it)
    try:
        xbmcplugin.setContent(HANDLE, 'seasons')
    except Exception:
        pass
        
    played_keys = _get_played_keys()
    
    season_keys = sorted(k for k in seasons.keys() if k)
    for season in season_keys:
        li = xbmcgui.ListItem(label=f"Temporada {season}")
        # Añadir metadata útil para que Kodi reconozca la relación con la serie
        try:
            info = {
                'tvshowtitle': series,
                'title': series,
                'season': int(season) if str(season).isdigit() else None,
                'mediatype': 'season'
            }
            
            season_eps = seasons.get(season, [])
            total_eps = len(season_eps)
            if total_eps > 0:
                watched_eps = sum(1 for e in season_eps if e.get('key') in played_keys)
                li.setProperty('TotalEpisodes', str(total_eps))
                li.setProperty('WatchedEpisodes', str(watched_eps))
                li.setProperty('UnWatchedEpisodes', str(total_eps - watched_eps))
                if watched_eps == total_eps:
                    info['playcount'] = 1
                    
            li.setInfo('video', info)
            tag = li.getVideoInfoTag()
            tag.setTitle(f"Temporada {season}")
            tag.setTvShowTitle(series)
            tag.setMediaType('season')
            if info['season'] is not None:
                tag.setSeason(info['season'])
            if 'playcount' in info:
                tag.setPlaycount(info['playcount'])
        except Exception:
            pass
        # Intentar poner una imagen representativa si existe en alguno de los items
        try:
            rep = sorted(seasons.get(season, []), key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
            try:
                _apply_art(li, rep, addon_fanart)
            except Exception:
                # fallback setArt on poster only
                poster = rep.get('poster') or rep.get('fanart') or ''
                if poster:
                    try:
                        li.setArt({'thumb': poster, 'poster': poster})
                    except Exception:
                        pass
        except Exception:
            pass
        if 'rep' in locals() and rep:
            _set_unique_ids(li, rep)
        q_params = {'action': 'list_episodes', 'series': series, 'season': season}
        if target_quality:
            q_params['target_quality'] = target_quality
        url = build_url(q_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_episodes(series, season, target_quality=None):
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    try:
        from resources.lib.db import get_series_episodes
        catalog = get_series_episodes(series)
    except Exception:
        catalog = []
    episodes = []
    for it in catalog:
        if str(it.get('season') or (it.get('parsed') or {}).get('season') or '') != str(season):
            continue
        episodes.append(it)
        
    try:
        xbmcplugin.setContent(HANDLE, 'episodes')
    except Exception:
        pass
        
    played_keys = _get_played_keys()
    resume_points = _get_resume_points()
    
    for it in sorted(episodes, key=lambda x: int(x.get('episode') or 0)):
        try:
            ep_num = int(it.get('episode') or 0)
        except Exception:
            ep_num = 0

        ep_title = it.get('episode_title') or it.get('title') or f"Episodio {ep_num}"
        label = f"S{str(int(season)).zfill(2)}E{str(ep_num).zfill(2)} - {ep_title}"
        li = xbmcgui.ListItem(label=label)
        # Metadata para que Kodi lo trate como episodio perteneciente a la serie
        # Preferir overview del episodio si existe, sino overview general
        ep_plot = it.get('episode_overview') or it.get('overview') or it.get('plot') or ''
        info = {
            'title': ep_title,
            'tvshowtitle': series,
            'season': int(season) if str(season).isdigit() else None,
            'episode': ep_num,
            'plot': ep_plot,
            'premiered': it.get('air_date') or it.get('date_added') or None,
            'mediatype': 'episode'
        }
        
        item_key = it.get('key') if isinstance(it, dict) else None
        if item_key and item_key in played_keys:
            info['playcount'] = 1
            
        if item_key and item_key in resume_points:
            info['resume_time'] = resume_points[item_key]['time']
            info['resume_total'] = resume_points[item_key]['total']
            li.setProperty('ResumeTime', str(info['resume_time']))
            li.setProperty('TotalTime', str(info['resume_total']))
            
        try:
            li.setInfo('video', info)
        except Exception:
            pass
            
        # Siempre aplicar InfoTagVideo para Kodi 20+ y skins como Arctic Fuse
        try:
            tag = li.getVideoInfoTag()
            tag.setTitle(info.get('title', ''))
            if info.get('plot'): tag.setPlot(info.get('plot'))
            if info.get('tvshowtitle'): tag.setTvShowTitle(info.get('tvshowtitle'))
            tag.setMediaType('episode')
            if info.get('season') is not None:
                tag.setSeason(int(info.get('season')))
            if info.get('episode') is not None:
                tag.setEpisode(int(info.get('episode')))
            if info.get('premiered'):
                tag.setFirstAired(info.get('premiered'))
            if 'playcount' in info:
                tag.setPlaycount(info['playcount'])
            if 'resume_time' in info and 'resume_total' in info:
                tag.setResumePoint(float(info['resume_time']), float(info['resume_total']))
        except Exception:
            pass
        # Arte si está disponible
        try:
            # Preferir imagen fija del episodio (still) si está disponible
            poster = it.get('still_path') or it.get('poster') or it.get('fanart') or ''
            try:
                _apply_art(li, it if isinstance(it, dict) else {'poster': poster, 'fanart': it.get('fanart') or ''}, addon_fanart)
            except Exception:
                if poster:
                    try:
                        li.setArt({'thumb': poster, 'poster': poster, 'fanart': it.get('fanart') or ''})
                    except Exception:
                        pass
        except Exception:
            pass
        _set_unique_ids(li, it)
        li.setProperty('IsPlayable', 'true')
        item_key = it.get('key') if isinstance(it, dict) else None
        q_params = {'action': 'select'}
        if item_key:
            q_params['key'] = item_key
        else:
            q_params['index'] = str(catalog.index(it))
        if target_quality:
            q_params['target_quality'] = target_quality
        url = build_url(q_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)


def do_search(q=None, original_params=None):
    """Buscar contenido en el catálogo con resultados agrupados y vista mejorada.

    Si se pasa `q` (string), la búsqueda se realiza sin abrir el teclado. Si
    `q` es None, se muestra el teclado como hasta ahora.
    """
    # Si se nos pasó una query por URL, usarla; sino abrir teclado
    if q is None:
        kb = xbmc.Keyboard('', 'Buscar...')
        kb.doModal()
        if not kb.isConfirmed():
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
        q = kb.getText().strip()
        if not q:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
            
        # Evitar doble teclado redirigiendo a la ruta con el parámetro
        url = build_url({'action': 'search', 'q': q})
        xbmc.executebuiltin(f'Container.Update({url})')
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    else:
        try:
            q = str(q).strip()
        except Exception:
            q = None
        if not q:
            return
    
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    try:
        # MEJORA DE RENDIMIENTO: Usar búsqueda SQL directa en lugar de cargar todo
        from resources.lib.db import search_items_sql
        results = search_items_sql(q, limit=100) # Límite para no saturar UI
    except Exception:
        results = []

    if not results:
        xbmcgui.Dialog().notification('RusterWolf', 'Sin resultados', xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.endOfDirectory(HANDLE)
        return
    
    # Separar películas y series
    movies = []
    series_map = {}
    
    for it in results:
        item_type = _get_item_type(it)
        if item_type == 'movie':
            movies.append(it)
        elif item_type in ('tv', 'series_documentary'):
            # Agrupar series por título normalizado
            title = _get_item_title(it)
            if title:
                key = normalize_title(title)
                series_map.setdefault(key, []).append(it)
    
    # Establecer tipo de contenido mixto (movies si hay más películas, tvshows si hay más series)
    try:
        if len(series_map) > len(movies):
            xbmcplugin.setContent(HANDLE, 'tvshows')
        else:
            xbmcplugin.setContent(HANDLE, 'movies')
    except Exception:
        pass
    
    # Mostrar series agrupadas
    for key, items_group in sorted(series_map.items(), key=lambda x: x[0]):
        # Elegir representante con mejor metadata
        rep = sorted(items_group, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
        li, url, is_folder = _create_item_and_url(rep, addon_fanart)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)
    
    # Mostrar películas
    for it in movies:
        li, url, is_folder = _create_item_and_url(it, addon_fanart)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    
    xbmcplugin.endOfDirectory(HANDLE)

def select_source(key=None, target_quality=None):
    """Muestra un diálogo con las fuentes disponibles y reproduce la seleccionada."""
    it = None
    if key:
        try:
            from resources.lib.db import load_items_by_keys
            items = load_items_by_keys([key]) or []
            it = items[0] if items else None
        except Exception: it = None

    if not it:
        xbmcgui.Dialog().notification('RusterWolf 77', 'Elemento no encontrado', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    title = it.get('title')
    sources = it.get('torrents') or [] # La columna 'torrents' ahora contiene todas las fuentes
    
    if not sources:
        xbmcgui.Dialog().notification('RusterWolf 77', 'No hay fuentes disponibles', xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    # Ordenar por calidad: 4K > 1080p > 720p > etc.
    def _q_rank(t):
        q = str(t.get('quality') or '').lower()
        if '4k' in q or '2160' in q: return 10
        if '1080' in q: return 9
        if '720' in q: return 8
        return 0
    sources = sorted(sources, key=_q_rank, reverse=True)

    sel = -1
    if target_quality:
        tq = target_quality.strip().lower()
        target_qualities = {tq}
        if tq == '4k': target_qualities.add('2160p')
        for i, s in enumerate(sources):
            if str(s.get('quality') or '').strip().lower() in target_qualities:
                sel = i
                break

    if sel == -1:
        if len(sources) == 1:
            sel = 0
        else:
            choices = []
            for s in sources:
                source_type = s.get('source', 'magnet')
                if source_type == "1fichier_palantir":
                    choices.append(f"[ALLDEBRID] {s.get('quality', '')} | {s.get('audio', '')} | {s.get('info', '')}")
                else:
                    choices.append(f"[TORRENT] {s.get('quality', 'SD')}")

            sel = xbmcgui.Dialog().select(f'Selecciona fuente: {title}', choices)
            if sel < 0:
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return

    selected_source = sources[sel]
    source_type = selected_source.get('source', 'magnet')
    url = selected_source.get('url') or selected_source.get('magnet')

    if not url:
        xbmcgui.Dialog().notification('RusterWolf 77', 'Enlace no válido', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    play_item(url, source_type, key)

def play_item(url, source_type, item_key):
    """Función 'router' que decide qué reproductor usar y resuelve el enlace para Kodi."""
    final_url = None
    
    # 1. Cargar la metadata completa del item para pasársela al reproductor
    it = None
    if item_key:
        try:
            from resources.lib.db import load_items_by_keys
            items = load_items_by_keys([item_key]) or []
            it = items[0] if items else None
        except Exception: pass

    # 2. Obtener las API keys de los ajustes
    alldebrid_api_key = ADDON.getSetting('alldebrid_api_key')
    realdebrid_api_key = ADDON.getSetting('realdebrid_api_key')
    debrid_provider = ADDON.getSetting('debrid_provider') or "0"
    debrid_cloud_fallback = ADDON.getSettingBool('debrid_cloud_fallback')

    # 3. Decidir qué reproductor usar
    if source_type == '1fichier_palantir':
        if not alldebrid_api_key:
            xbmcgui.Dialog().ok("Acceso Requerido", "Esta fuente requiere una cuenta de AllDebrid.\nPor favor, introduce tu API Key en los ajustes del addon.")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        final_url = play_1fichier_with_alldebrid(url, alldebrid_api_key)
    
    elif source_type == 'magnet':
        magnet_url = url
        if debrid_provider == "1": # AllDebrid
            if not alldebrid_api_key:
                xbmcgui.Dialog().ok('AllDebrid', 'Falta la API Key en los ajustes.')
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return
            final_url = play_with_alldebrid(magnet_url, alldebrid_api_key, debrid_cloud_fallback)
        elif debrid_provider == "2": # RealDebrid
            if not realdebrid_api_key:
                xbmcgui.Dialog().ok('Real-Debrid', 'Falta la API Key en los ajustes.')
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return
            final_url = play_with_realdebrid(magnet_url, realdebrid_api_key, debrid_cloud_fallback)
        else: # Elementum
            if not is_elementum_installed():
                xbmcgui.Dialog().ok('Elementum no instalado', 'Instala Elementum desde:\nhttps://elementumorg.github.io/')
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return
            # Inyectar trackers para Elementum
            public_trackers = ["udp://tracker.opentrackr.org:1337/announce", "udp://open.demonii.com:1337/announce"]
            for tr in public_trackers:
                if tr not in magnet_url: magnet_url += f"&tr={urllib.parse.quote(tr)}"
            final_url = f'plugin://plugin.video.elementum/play?uri={urllib.parse.quote_plus(magnet_url)}'

        # Fallback a Elementum si Debrid falla
        if not final_url and debrid_provider in ("1", "2"):
            if is_elementum_installed():
                if xbmcgui.Dialog().yesno('No en caché', 'Este archivo no está en la caché de tu Debrid.\n¿Desea comprobar la disponibilidad con Elementum?'):
                    public_trackers = ["udp://tracker.opentrackr.org:1337/announce", "udp://open.demonii.com:1337/announce"]
                    for tr in public_trackers:
                        if tr not in magnet_url: magnet_url += f"&tr={urllib.parse.quote(tr)}"
                    final_url = f'plugin://plugin.video.elementum/play?uri={urllib.parse.quote_plus(magnet_url)}'

    # 4. Guardar historial y resolver la URL para Kodi
    if final_url:
        # Guardar historial para el sistema Up Next
        try:
            history_thread = threading.Thread(target=play_with_elementum, args=(url, it), daemon=True)
            history_thread.start()
        except Exception as e:
            xbmc.log(f"RusterWolf: No se pudo iniciar el hilo de historial: {e}", xbmc.LOGERROR)

        li = xbmcgui.ListItem(path=final_url)
        if it:
            try:
                tag = li.getVideoInfoTag()
                title = it.get('title')
                if title:
                    tag.setTitle(it.get('episode_title') or title)
                    tag.setTvShowTitle(title)
                if it.get('season'): tag.setSeason(int(it['season']))
                if it.get('episode'): tag.setEpisode(int(it['episode']))
                plot = it.get('episode_overview') or it.get('overview') or it.get('plot')
                if plot: tag.setPlot(plot)
                media_type = it.get('type')
                if media_type == 'tv': tag.setMediaType('episode')
                elif media_type == 'movie': tag.setMediaType('movie')
                _apply_art(li, it)
            except Exception as e:
                xbmc.log(f"RusterWolf: error transfiriendo metadata al player: {e}", xbmc.LOGWARNING)
        
        xbmcgui.Window(10000).setProperty('Rusterwolf_Playing', 'true')
        xbmcplugin.setResolvedUrl(HANDLE, True, li)
    else:
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())

def open_settings():
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % ADDON.getAddonInfo('id'))

def run_one_time_cleanup():
    """
    Borra la antigua base de datos 'cache.db' del directorio de userdata
    para liberar espacio tras la actualización al sistema de DB temporal.
    Solo se ejecuta una vez.
    """
    try:
        addon_id = ADDON.getAddonInfo('id')
        userdata_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")
        flag_file = os.path.join(userdata_dir, 'v2_db_cleanup.flag') # Nombre de flag específico
        
        if not xbmcvfs.exists(flag_file):
            xbmc.log("RusterWolf: Ejecutando limpieza única post-actualización...", xbmc.LOGINFO)
            
            old_db_path = os.path.join(userdata_dir, 'cache.db')
            if xbmcvfs.exists(old_db_path):
                if xbmcvfs.delete(old_db_path):
                    xbmc.log("RusterWolf: Antigua 'cache.db' eliminada con éxito.", xbmc.LOGINFO)
                    
            old_bin_path = os.path.join(userdata_dir, 'archivos.bin')
            if xbmcvfs.exists(old_bin_path):
                xbmcvfs.delete(old_bin_path)
                xbmc.log("RusterWolf: Antiguo 'archivos.bin' eliminado del userdata con éxito.", xbmc.LOGINFO)
            
            with xbmcvfs.File(flag_file, 'w') as f: f.write('done')
            xbmc.log("RusterWolf: Flag de limpieza creado. No se volverá a ejecutar.", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"RusterWolf: Error durante la limpieza única: {e}", xbmc.LOGERROR)

def router(params):
    import xbmc
    import threading as _threading
    try:
        ths = [(t.name, getattr(t, 'ident', None), t.daemon) for t in _threading.enumerate()]
        xbmc.log(f"RusterWolf: router threads active={ths}", xbmc.LOGDEBUG)
    except Exception:
        pass
    action = params.get('action')
    try:
        page = int(params.get('page') or 1)
    except Exception:
        page = 1
    xbmc.log(f"RusterWolf: router params={params}", xbmc.LOGWARNING)
    # Detectar si la petición incluye una búsqueda por URL (query/name/q) o
    # el caso malformado action='search=texto' y, en ese caso, invocar
    # do_search(prefill) para evitar abrir el teclado.
    if action == 'add_watchlist':
        action_add_watchlist(params)
        return
    if action == 'remove_watchlist':
        action_remove_watchlist(params)
        return
    try:
        q_param = None
        if isinstance(params, dict):
            q_param = params.get('query') or params.get('name') or params.get('q')
        # manejar acción malformada: action='search=algo'
        if not q_param and isinstance(action, str) and action.startswith('search='):
            try:
                q_param = action.split('=', 1)[1]
                # normalizar action para no romper el flujo si se revisa más abajo
                action = 'search'
            except Exception:
                q_param = None
        if q_param:
            try:
                xbmc.log(f"RusterWolf: router detected query param in URL -> '{q_param}'", xbmc.LOGDEBUG)
            except Exception:
                pass
            do_search(q_param, original_params=params)
            return
    except Exception:
        pass
    # Soportar acciones explícitas para evitar depender de parámetros 'filter' que no siempre llegan
    if action in ('movie_menu', 'tv_menu', 'novedades_menu', 'continue_watching', 'favorites', 'documentary_main_menu', 'documentary_menu', 'series_documentary_menu', 'premium_menu', 'premium_movie_menu', 'premium_tv_menu'):
        # acciones que muestran submenús para Películas/Series o pantallas especiales
        if action == 'movie_menu':
            movie_menu()
            return
        if action == 'premium_menu':
            premium_menu()
            return
        if action == 'premium_movie_menu':
            premium_movie_menu()
            return
        if action == 'premium_tv_menu':
            premium_tv_menu()
            return
        if action == 'tv_menu':
            tv_menu()
            return
        if action == 'novedades_menu':
            novedades_menu()
            return
        if action == 'continue_watching':
            continue_watching()
            return
        if action == 'favorites':
            favorites_menu()
            return
        if action == 'documentary_main_menu':
            documentary_main_menu()
            return
        if action == 'documentary_menu':
            documentary_menu()
            return
        if action == 'series_documentary_menu':
            series_documentary_menu()
            return
    if action in ('list_movie', 'list_tv', 'list_documentary', 'list_series_documentary'):
        # mapear acciones explícitas a un filter_type antes de llamar a list_items
        map_action = {
            'list_movie': 'movie',
            'list_tv': 'tv',
            'list_documentary': 'documentary',
            'list_series_documentary': 'series_documentary'
        }
        filter_type = map_action.get(action)
        xbmc.log(f"RusterWolf: router mapped action={action} to filter_type={filter_type}", xbmc.LOGWARNING)
        list_items(filter_type=filter_type, page=page, action_name=action,
                   group_by=params.get('group'), genre_filter=params.get('genre'), year_filter=params.get('year'), quality_filter=params.get('quality'), letter_filter=params.get('letter'), collection_filter=params.get('collection'), original_params=params)
        return
    elif action == 'list':
        # Si se solicitó agrupación (por género/año) pero no se indicó filter (movie/tv),
        # intentar usar 'origin' como fallback cuando 'filter' no venga.
        flt = params.get('filter') or params.get('origin')
        # if original query used 'origin' but not 'filter', copy it so pagination links include filter
        if not params.get('filter') and params.get('origin'):
            params['filter'] = params.get('origin')
        # Additional fallback: sometimes Kodi will invoke the plugin for a child
        # directory passing only the changed params (e.g. page=2) and omit the
        # original filter/origin. In that case try to recover the parent container
        # path (which Kodi logs as ParentPath) via Container.FolderPath and parse
        # its querystring to extract filter/origin.
        if not flt:
            try:
                parent_path = xbmc.getInfoLabel('Container.FolderPath') or ''
                xbmc.log(f"RusterWolf: router Container.FolderPath={parent_path}", xbmc.LOGDEBUG)
                if parent_path:
                    parsed = urllib.parse.urlparse(parent_path)
                    parent_q = dict(urllib.parse.parse_qsl(parsed.query))
                    recovered = parent_q.get('filter') or parent_q.get('origin')
                    if recovered:
                        flt = recovered
                        # also ensure params contains filter so pagination building sees it
                        if not params.get('filter'):
                            params['filter'] = recovered
                        xbmc.log(f"RusterWolf: router recovered filter from Container.FolderPath={recovered}", xbmc.LOGDEBUG)
                    else:
                        # Si la query del ParentPath no tiene filter/origin, intentar recuperar desde el cache local
                        try:
                            try:
                                profile_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}")
                            except Exception:
                                profile_dir = os.path.join(ADDON.getAddonInfo('path'), 'cache')
                            cache_file = os.path.join(profile_dir, 'pagination_cache.json')
                            if os.path.exists(cache_file):
                                with open(cache_file, 'r', encoding='utf-8') as cf:
                                    cache = json.load(cf) or {}
                                # Normalize parent_path key (strip trailing slash)
                                parent_key = parent_path.rstrip('/')
                                # probar clave exacta y también sin el query ordenado
                                candidate = None
                                if parent_key in cache:
                                    candidate = cache[parent_key]
                                else:
                                    # tratar de coincidir por querystring ignorando el orden
                                    parsed_parent = urllib.parse.urlparse(parent_key)
                                    parent_q_sorted = dict(urllib.parse.parse_qsl(parsed_parent.query))
                                    # First try exact query match (ignoring trailing slash)
                                    for k, v in cache.items():
                                        try:
                                            pk = urllib.parse.urlparse(k)
                                            kq = dict(urllib.parse.parse_qsl(pk.query))
                                            if kq == parent_q_sorted:
                                                candidate = v
                                                break
                                        except Exception:
                                            continue
                                    # If no exact match, try to find cached entry with same action+page that DOES include filter/origin
                                    if not candidate:
                                        for k, v in cache.items():
                                            try:
                                                pk = urllib.parse.urlparse(k)
                                                kq = dict(urllib.parse.parse_qsl(pk.query))
                                                if kq.get('action') == parent_q_sorted.get('action') and kq.get('page') == parent_q_sorted.get('page') and (kq.get('filter') or kq.get('origin')):
                                                    candidate = v
                                                    break
                                            except Exception:
                                                continue
                                if candidate:
                                    recovered = candidate.get('filter') or candidate.get('origin')
                                    if recovered:
                                        flt = recovered
                                        if not params.get('filter'):
                                            params['filter'] = recovered
                                        xbmc.log(f"RusterWolf: router recovered filter from pagination_cache for ParentPath={parent_path} -> {recovered}", xbmc.LOGDEBUG)
                                else:
                                    # intentar usar '__last_filters' para la acción si existe
                                    try:
                                        cache_file = os.path.join(profile_dir, 'pagination_cache.json')
                                        if os.path.exists(cache_file):
                                            with open(cache_file, 'r', encoding='utf-8') as cf:
                                                data = json.load(cf) or {}
                                            last_filters = data.get('__last_filters') or {}
                                            act = parent_q.get('action') or 'list'
                                            recovered = last_filters.get(act)
                                            if recovered:
                                                flt = recovered
                                                if not params.get('filter'):
                                                    params['filter'] = recovered
                                                xbmc.log(f"RusterWolf: router recovered filter from __last_filters for action={act} -> {recovered}", xbmc.LOGDEBUG)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass
        xbmc.log(f"RusterWolf: router llama a list_items con filter_type={flt} page={page}", xbmc.LOGWARNING)
        list_items(filter_type=flt, page=page, action_name='list',
                   group_by=params.get('group'), genre_filter=params.get('genre'), year_filter=params.get('year'), quality_filter=params.get('quality'), letter_filter=params.get('letter'), collection_filter=params.get('collection'), original_params=params)
        return
    elif action == 'novedades':
        novedades(page=page, sub=params.get('sub'), original_params=params)
    elif action == 'search':
        do_search(original_params=params)
    elif action == 'select':
        select_source(key=params.get('key'), target_quality=params.get('target_quality'))
    elif action == 'play':
        play_item(urllib.parse.unquote(params.get('url')), params.get('source_type'), params.get('item_key'))
    elif action == 'list_seasons':
        list_seasons(params.get('series'), params.get('target_quality'))
    elif action == 'list_episodes':
        list_episodes(params.get('series'), params.get('season'), params.get('target_quality'))
    elif action == 'auth_alldebrid':
        from resources.lib.alldebrid import auth
        auth()
    elif action == 'auth_realdebrid':
        from resources.lib.realdebrid import auth
        auth()
    elif action == 'settings':
        open_settings()
    else:
        list_root()



if __name__ == '__main__':
    import urllib.parse
    raw_params = sys.argv[2] if len(sys.argv) > 2 else ''
    if raw_params.startswith('?'):
        raw_params = raw_params[1:]
    params = dict(urllib.parse.parse_qsl(raw_params)) if raw_params else {}
    import xbmc
    xbmc.log(f"RusterWolf: __main__ params={params}", xbmc.LOGWARNING)

    # --- LIMPIEZA ÚNICA POST-ACTUALIZACIÓN ---
    # Borra la antigua cache.db del userdata para liberar espacio.
    run_one_time_cleanup()

    # Si se abre el addon sin parámetros (entrada principal), actualizar DB desde remote
    is_entry = not params or not params.get('action')
    if is_entry:
        try:
            from resources.lib.db import maybe_update_db_from_remote, init_db
            if init_db:
                init_db()
                
            if maybe_update_db_from_remote:
                # Ejecución síncrona. No usamos hilos porque Kodi los mata al dibujar el menú.
                maybe_update_db_from_remote(force=False)
        except Exception as e:
            xbmc.log(f'RusterWolf: Error en inicio de addon: {e}', xbmc.LOGERROR)
    else:
        try:
            from resources.lib.db import ensure_session_db
            ensure_session_db()
        except Exception: pass
    router(params)
