# -*- coding: utf-8 -*-
import sys, xbmc, xbmcgui, xbmcplugin, xbmcaddon, urllib.parse, xbmcvfs
import json
import unicodedata, re, os, threading, time
from resources.lib.player import is_elementum_installed, play_with_elementum, play_with_alldebrid, play_1fichier_with_alldebrid, play_with_realdebrid
from resources.lib.db import load_items_by_keys

ADDON = xbmcaddon.Addon()
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
# Resolver icono del addon (usar icon.png en la raíz o resources/media/icon.png si existe)
try:
    ADDON_PATH = ADDON.getAddonInfo('path')
    ADDON_FANART = os.path.join(ADDON_PATH, 'resources', 'media', 'fanart.jpeg')
    ADDON_ICON_DEFAULT = os.path.join(ADDON_PATH, 'resources', 'media', 'icon.png')
    if os.path.exists(os.path.join(ADDON_PATH, 'icon.png')):
        ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')
    elif os.path.exists(ADDON_ICON_DEFAULT):
        ADDON_ICON = ADDON_ICON_DEFAULT
    else:
        ADDON_ICON = ''
except Exception:
    ADDON_ICON = ''

SECTION_PLOTS = {
    'peliculas': 'Prepara las palomitas. Descubre desde los últimos taquillazos de Hollywood hasta clásicos inolvidables para una sesión de cine perfecta.',
    'series_tv': 'Maratones que atrapan. Sumérgete en temporadas repletas de intriga, comedia y acción con las series más aclamadas del momento.',
    'documentales': 'La realidad supera a la ficción. Explora los misterios de la naturaleza, crímenes reales y los secretos más profundos de nuestra historia.',
    'series_documental': 'La realidad supera a la ficción. Explora los misterios de la naturaleza, crímenes reales y los secretos más profundos de nuestra historia.',
    'anime': '¡Kame Hame Ha! Viaja a universos épicos y llenos de poder con nuestra brutal selección de animación japonesa.',
    'dibujos': 'Risas y aventuras para los peques (y no tan peques). Un espacio mágico repleto de color y animación para toda la familia.',
    'retro': '¡Directo a la nostalgia! Saca a pasear tu espíritu ochentero y noventero y revive esas joyas míticas.',
    'novedades': 'Lo último de lo último. Mantente al día con los estrenos más frescos que acaban de aterrizar en el catálogo.',
    'seguir_viendo': '¿Por dónde íbamos? Retoma tus capítulos y películas exactamente en el segundo que las dejaste.',
    'favoritos': 'Tu cámara acorazada personal. Todo el contenido que te ha robado el corazón, guardado a buen recaudo.'
}

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
                cur.execute("SELECT strFilename, lastPlayed FROM files WHERE strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND (playCount > 0 OR idFile IN (SELECT idFile FROM bookmark WHERE type=1))")
            except Exception:
                cur.execute("SELECT strFilename, NULL FROM files WHERE strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND (playCount > 0 OR idFile IN (SELECT idFile FROM bookmark WHERE type=1))")
            for row in cur.fetchall():
                try:
                    url_str = row[0]
                    if 'key=' in url_str:
                        key_val = url_str.split('key=')[1].split('&')[0]
                        key_val = urllib.parse.unquote(key_val)
                        val = row[1] if len(row) > 1 and row[1] else ""
                        if val: _PLAYED_KEYS[key_val] = val
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
                    time_sec = float(row[1])
                    total_sec = float(row[2])
                    if total_sec > 0 and (time_sec / total_sec) >= 0.90:
                        continue
                    url_str = row[0]
                    if 'key=' in url_str:
                        key_val = url_str.split('key=')[1].split('&')[0]
                        key_val = urllib.parse.unquote(key_val)
                        _RESUME_POINTS[key_val] = {'time': time_sec, 'total': total_sec}
                except Exception:
                    pass
            conn.close()
    except Exception as e:
        xbmc.log(f"RusterWolf: Error _get_resume_points: {e}", xbmc.LOGWARNING)
    return _RESUME_POINTS

def build_url(query):
    import xbmc
    url = BASE_URL + '?' + urllib.parse.urlencode(query)
    xbmc.log(f"RusterWolf: build_url query={query} url={url}", xbmc.LOGDEBUG)
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
        base_path = os.path.join(ADDON_PATH, 'resources', 'media')
        for suffix in ['_logo_v2.png', '_logo.png', 'logo.png']:
            logo_path = os.path.join(base_path, f"{section_key}{suffix}")
            if os.path.exists(logo_path):
                return logo_path
    except Exception:
        pass
    return None

def _get_section_icon(section_key):
    """Retorna el path del icono para una sección si existe."""
    if not section_key:
        return None
    try:
        base_path = os.path.join(ADDON_PATH, 'resources', 'media')
        for suffix in ['_v2.png', '.png']:
            icon_path = os.path.join(base_path, f"{section_key}{suffix}")
            if os.path.exists(icon_path):
                return icon_path
    except Exception:
        pass
    return None

def _get_current_section_safe_id(filter_type, genre_filter):
    """Determina la ID segura de la sección en función del género y filtro actual."""
    if genre_filter:
        g_lower = genre_filter.lower()
        if 'dibujo' in g_lower: return 'dibujos'
        if 'anime' in g_lower: return 'anime'
        if 'retro' in g_lower: return 'retro'
        if 'documental' in g_lower: return 'series_documental' if filter_type in ('tv', 'series_documentary') else 'documentales'
    if filter_type == 'series_documentary': return 'series_documental'
    if filter_type == 'documentary': return 'documentales'
    if filter_type == 'tv': return 'series_tv'
    if filter_type in ('movie', 'pelicula'): return 'peliculas'
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
        # Aplicar addon_fanart como fallback si el item no tiene fanart
        if 'fanart' not in art and addon_fanart:
            art['fanart'] = addon_fanart
        # Aplicar arte al ListItem si existe
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
    t = str(t).lower().strip() if t else ''
    if t in ('series', 'serie', 'tvshow', 'tv'):
        return 'tv'
    elif t in ('movie', 'pelicula', 'película'):
        return 'movie'
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

    total_eps = 0
    watched_eps = 0
    # OPTIMIZACIÓN EXTREMA: El cálculo de episodios visualizados se omite aquí 
    # para multiplicar la velocidad de los menús x10. Se calcula al entrar en Temporadas.

    _apply_info_tag(li, info)
    try:
        safe_info = {k: v for k, v in info.items() if k not in ('cast', 'resume_time', 'resume_total') and v is not None}
        li.setInfo('video', safe_info)
    except Exception: pass

    try: _apply_art(li, it, addon_fanart)
    except Exception: pass
    
    _set_unique_ids(li, it)
    if mediatype_item in ('tv', 'series_documentary'):
        url_params = {'action': 'list_seasons', 'series': title}
        if quality_filter: url_params['target_quality'] = quality_filter
        url = build_url(url_params)
        is_folder = True
        
        is_watched = info.get('playcount', 0) > 0
        tn = normalize_title(title)
        cm = generate_context_menu('tv', tn, title, is_watched, watched_eps=watched_eps, total_eps=total_eps, item_key=it.get('key'))
    else:
        li.setProperty('IsPlayable', 'true')
        li.setMimeType('application/x-bittorrent')
        item_key = it.get('key') # La clave del item, no de la fuente
        q_params = {'action': 'select', 'key': item_key}
        if quality_filter: q_params['target_quality'] = quality_filter
        url = build_url(q_params)
        is_folder = False
        
        is_watched = info.get('playcount', 0) > 0
        cm = generate_context_menu('movie', item_key, title, is_watched, item_key=item_key)
            
    if cm: li.addContextMenuItems(cm)
    return li, url, is_folder

def generate_context_menu(item_type, val, title, is_watched, watched_eps=0, total_eps=0, item_key=None):
    """
    Genera dinámicamente los botones del menú contextual dependiendo del estado del ítem.
    item_type: 'movie', 'tv', 'season', 'episode'
    val: El ID del elemento (item_key para pelis, título para series)
    """
    cm = []
    if item_type in ('movie', 'tv'):
        wl = get_cached_watchlist()
        po = get_cached_progress()
        
        is_fav = f"{item_type}_{val}" in wl
        is_manual = val in po.get('manual', {})
        is_hidden = val in po.get('hidden', [])
        
        has_progress = False
        if item_type == 'tv' and 0 < watched_eps < total_eps:
            has_progress = True
        elif item_type == 'movie' and item_key and item_key in _get_resume_points():
            has_progress = True
            
        is_in_seguir_viendo = (is_manual or has_progress) and not is_hidden
        
        if is_fav:
            rm_url = build_url({'action': 'remove_watchlist', 'uid': f"{item_type}_{val}"})
            cm.append(('Quitar de Favoritos R77', f'RunPlugin({rm_url})'))
        else:
            add_url = build_url({'action': 'add_watchlist', 'wtype': item_type, 'val': val, 'title': title})
            cm.append(('Añadir a Favoritos R77', f'RunPlugin({add_url})'))
            
        if is_in_seguir_viendo:
            rm_prog = build_url({'action': 'remove_progress', 'wtype': item_type, 'val': val, 'title': title})
            cm.append(('Quitar de Seguir Viendo R77', f'RunPlugin({rm_prog})'))
        else:
            add_prog = build_url({'action': 'add_progress', 'wtype': item_type, 'val': val, 'title': title, 'key': item_key})
            cm.append(('Añadir a Seguir Viendo R77', f'RunPlugin({add_prog})'))
            
    # Dejamos que Kodi gestione "Marcar como visto" de forma nativa para episodios y películas.
    # Solo lo añadimos manualmente para TV y Seasons, ya que Kodi a veces no lo pone en carpetas de plugins.
    if item_type in ('tv', 'season'):
        if is_watched:
            cm.append(('Marcar como no visto', 'Action(ToggleWatched)'))
        else:
            cm.append(('Marcar como visto', 'Action(ToggleWatched)'))
        
    return cm

# --- Funciones para Watchlist (Seguir Viendo Manual) ---
_WATCHLIST_CACHE = None
_PROGRESS_CACHE = None

def get_cached_watchlist():
    global _WATCHLIST_CACHE
    if _WATCHLIST_CACHE is None:
        _WATCHLIST_CACHE = load_watchlist()
    return _WATCHLIST_CACHE

def get_cached_progress():
    global _PROGRESS_CACHE
    if _PROGRESS_CACHE is None:
        _PROGRESS_CACHE = load_progress_override()
    return _PROGRESS_CACHE

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
        except Exception:
            try:
                vf = xbmcvfs.File(wf, 'w')
                vf.write(json.dumps(data, ensure_ascii=False, indent=2))
                vf.close()
            except Exception: pass

def action_add_watchlist(params):
    global _WATCHLIST_CACHE
    _WATCHLIST_CACHE = None
    wtype = params.get('wtype')
    val = params.get('val')
    title = params.get('title')
    if not wtype or not val: return
    wl = load_watchlist()
    uid = f"{wtype}_{val}"
    wl[uid] = {'wtype': wtype, 'val': val, 'title': title, 'added': time.time()}
    save_watchlist(wl)
    xbmcgui.Dialog().notification('RusterWolf', f'{title} añadido a Favoritos R77', ADDON_ICON)

def action_remove_watchlist(params):
    global _WATCHLIST_CACHE
    _WATCHLIST_CACHE = None
    uid = params.get('uid')
    wl = load_watchlist()
    if uid in wl:
        del wl[uid]
        save_watchlist(wl)
        xbmcgui.Dialog().notification('RusterWolf', 'Eliminado de Favoritos R77', ADDON_ICON)
        xbmc.executebuiltin('Container.Refresh')

# --- Funciones para Seguir Viendo Manual ---
def get_progress_file():
    try:
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        if not os.path.exists(profile_dir): os.makedirs(profile_dir)
        return os.path.join(profile_dir, 'progress_override.json')
    except: return ''

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
        except Exception:
            try:
                vf = xbmcvfs.File(pf, 'w')
                vf.write(json.dumps(data, ensure_ascii=False, indent=2))
                vf.close()
            except Exception: pass

def action_add_progress(params):
    global _PROGRESS_CACHE
    _PROGRESS_CACHE = None
    po = load_progress_override()
    val = params.get('val')
    if not val: return
    if val in po['hidden']: po['hidden'].remove(val)
    po['manual'][val] = {'wtype': params.get('wtype'), 'title': params.get('title'), 'key': params.get('key'), 'added': time.time()}
    save_progress_override(po)
    xbmcgui.Dialog().notification('RusterWolf', f'{params.get("title", "")} añadido a Seguir Viendo', ADDON_ICON)

def action_remove_progress(params):
    global _PROGRESS_CACHE
    _PROGRESS_CACHE = None
    po = load_progress_override()
    val = params.get('val')
    if not val: return
    if val in po['manual']: del po['manual'][val]
    if val not in po['hidden']: po['hidden'].append(val)
    save_progress_override(po)
    xbmcgui.Dialog().notification('RusterWolf', f'{params.get("title", "Elemento")} quitado de Seguir Viendo', ADDON_ICON)
    xbmc.executebuiltin('Container.Refresh')
# --------------------------------------------------------


def list_root():
    from resources.lib.menus import build_root_menu
    build_root_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url)

def _generic_main_menu(title, genre_name, safe_id):
    from resources.lib.menus import build_generic_main_menu
    build_generic_main_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, title, genre_name, safe_id)

def genre_sub_menu(filter_type, genre_name, safe_id):
    from resources.lib.menus import build_genre_sub_menu
    build_genre_sub_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, filter_type, genre_name, safe_id)

def novedades_menu():
    from resources.lib.menus import build_standard_menu
    icon = _get_section_icon('novedades') or ADDON_ICON_DEFAULT
    logo = _get_section_logo('novedades')
    entries = [('Novedades (Películas)', {'action': 'novedades', 'sub': 'movies', 'sort_by': 'novedades'}), ('Novedades (Series)', {'action': 'novedades', 'sub': 'series', 'sort_by': 'novedades'})]
    xbmcplugin.setContent(HANDLE, 'files')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info = li.getVideoInfoTag()
            info.setTitle(label)
            info.setPlot(SECTION_PLOTS.get('novedades', ''))
        except: pass
        art = {'fanart': ADDON_FANART, 'icon': icon, 'thumb': icon}
        if logo: art.update({'clearlogo': logo, 'logo': logo})
        try: li.setArt(art)
        except: pass
        xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)


def continue_watching():
    icon_path = _get_section_icon('seguir_viendo') or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo('seguir_viendo')
    
    from resources.lib.user_lists import render_continue_watching
    render_continue_watching(
        HANDLE, ADDON_FANART, icon_path, section_logo,
        get_cached_progress(), _get_played_keys(), _get_resume_points(),
        build_url, _apply_info_tag, _apply_art, generate_context_menu,
        _get_item_type, _get_item_title, normalize_title
    )

def favorites_menu():
    icon_path = _get_section_icon('favoritos') or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo('favoritos')
    
    from resources.lib.user_lists import render_favorites
    render_favorites(
        HANDLE, ADDON_FANART, icon_path, section_logo,
        get_cached_watchlist(), _get_played_keys(), 
        build_url, _apply_info_tag, _apply_art, generate_context_menu
    )
    
def movie_menu():
    from resources.lib.menus import build_standard_menu
    build_standard_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, 'movie', '(Películas)', 'peliculas', show_collections=True)

def tv_menu():
    from resources.lib.menus import build_standard_menu
    build_standard_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, 'tv', '(Series)', 'series_tv', show_collections=False)

def documentary_menu():
    from resources.lib.menus import build_standard_menu
    build_standard_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, 'documentary', '', 'documentales', show_collections=False, show_genres=False, show_years=True)

def series_documentary_menu():
    from resources.lib.menus import build_standard_menu
    build_standard_menu(HANDLE, ADDON, ADDON_FANART, _get_section_icon, _get_section_logo, build_url, 'series_documentary', '', 'series_documental', show_collections=False, show_genres=False, show_years=True)

def documentary_main_menu():
    entries = [('Documentales', {'action':'documentary_menu'}, 'documentales'), ('Series Documental', {'action':'series_documentary_menu'}, 'series_documental')]
    xbmcplugin.setContent(HANDLE, 'files')
    for label, params, safe_id in entries:
        li = xbmcgui.ListItem(label)
        try:
            info = li.getVideoInfoTag()
            info.setTitle(label)
            info.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except: pass
        icon = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
        logo = _get_section_logo(safe_id)
        art = {'fanart': ADDON_FANART, 'icon': icon, 'thumb': icon}
        if logo: art.update({'clearlogo': logo, 'logo': logo})
        li.setArt(art)
        xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)


def list_genres(filter_type=None, original_params=None):
    """Lista géneros usando una lista estática para no saturar memoria RAM."""
    is_premium_req = False
    genre_filter = original_params.get('genre', '') if original_params else ''
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or genre_filter.lower() == 'premium'):
        is_premium_req = True
        
    # Usar géneros de TMDB fijos para carga instantánea
    genres_list = ['Acción', 'Animación', 'Aventura', 'Bélica', 'Ciencia ficción', 'Comedia', 'Crimen', 'Documental', 'Drama', 'Familia', 'Fantasía', 'Historia', 'Misterio', 'Música', 'Romance', 'Suspense', 'Terror', 'Western']

    if not filter_type:
        filter_type = 'movie'
    
    safe_id = _get_current_section_safe_id(filter_type, genre_filter)
    icon_path = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo(safe_id)

    xbmcplugin.setContent(HANDLE, 'files')
    for gname in sorted(genres_list):
        li = xbmcgui.ListItem(label=gname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(gname)
            info_tag.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': ADDON_FANART}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        # pass the real genre name so matching can be done by substring on the DB side
        combined_genre = gname
        if genre_filter in ('Retro', 'Dibujo', 'Anime'):
            combined_genre = f"{genre_filter}|{gname}"
            
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'genre': combined_genre}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        url = build_url(url_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)


def list_years(filter_type=None, genre_filter=None, original_params=None):
    """Listar años consultando eficientemente la DB."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    if not filter_type:
        filter_type = 'movie'
        
    from resources.lib.db import get_years
    years = get_years(filter_type, genre=genre_filter)

    safe_id = _get_current_section_safe_id(filter_type, genre_filter)
    icon_path = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo(safe_id)

    xbmcplugin.setContent(HANDLE, 'files')
    for y in years:
        li = xbmcgui.ListItem(label=f'Año {y}')
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(f'Año {y}')
            info_tag.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': ADDON_FANART}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try:
            li.setArt(art_dict)
        except Exception:
            pass
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'year': y}
        if genre_filter and genre_filter.lower() != 'premium': url_params['genre'] = genre_filter
        if is_premium_req: url_params['base_genre'] = 'Premium'
        url = build_url(url_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)

def list_qualities(filter_type=None, genre_filter=None, original_params=None):
    """Lista estática de calidades para no saturar memoria RAM."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    qualities = ['4K', '1080p', '720p', 'MicroHD', 'BluRay', 'HDTV']

    safe_id = _get_current_section_safe_id(filter_type, genre_filter)
    icon_path = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo(safe_id)

    xbmcplugin.setContent(HANDLE, 'files')
    for qname in qualities:
        li = xbmcgui.ListItem(label=qname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(qname)
            info_tag.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except Exception:
            pass
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': ADDON_FANART}
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
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)

def list_letters(filter_type=None, genre_filter=None, original_params=None):
    """Lista letras iniciales consultando la DB eficientemente."""
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    from resources.lib.db import get_letters
    letters = get_letters(filter_type, genre=genre_filter)

    safe_id = _get_current_section_safe_id(filter_type, genre_filter)
    icon_path = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo(safe_id)

    xbmcplugin.setContent(HANDLE, 'files')
    for letter in letters:
        li = xbmcgui.ListItem(label=letter)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(letter)
            info_tag.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except Exception: pass
        art_dict = {'icon': icon_path, 'thumb': icon_path, 'fanart': ADDON_FANART}
        if section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
        try: li.setArt(art_dict)
        except Exception: pass
        
        q_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'letter': letter}
        if genre_filter and genre_filter.lower() != 'premium': q_params['genre'] = genre_filter
        if is_premium_req: q_params['base_genre'] = 'Premium'
        xbmcplugin.addDirectoryItem(HANDLE, build_url(q_params), li, True)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)

def list_collections(filter_type=None, original_params=None, page=1):
    """Lista colecciones usando consulta SQL paginada."""
    is_premium_req = False
    genre_filter = None
    if original_params:
        genre_filter = original_params.get('genre')
        if original_params.get('base_genre', '').lower() == 'premium' or str(genre_filter).lower() == 'premium':
            is_premium_req = True
        
    from resources.lib.db import get_collections_paginated
    per_page = _read_items_per_page()
    offset = (page - 1) * per_page
    
    safe_id = _get_current_section_safe_id(filter_type, genre_filter)
    icon_path = _get_section_icon(safe_id) or ADDON_ICON_DEFAULT
    section_logo = _get_section_logo(safe_id)

    xbmcplugin.setContent(HANDLE, 'movies')
    
    collections = get_collections_paginated(filter_type, limit=per_page + 1, offset=offset, genre=genre_filter, is_premium_req=is_premium_req)
    has_next_page = len(collections) > per_page
    page_cols = collections[:per_page]
    
    for col_data in page_cols:
        c_name = col_data['name']
        li = xbmcgui.ListItem(label=c_name)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(c_name)
            info_tag.setPlot(SECTION_PLOTS.get(safe_id, ''))
        except Exception: pass
        
        art_dict = {'fanart': col_data['fanart'] or ADDON_FANART, 'icon': icon_path}
        if col_data['poster']:
            art_dict['thumb'] = col_data['poster']
            art_dict['poster'] = col_data['poster']
        else: art_dict['thumb'] = icon_path
            
        if col_data['clearlogo']:
            art_dict['clearlogo'] = col_data['clearlogo']
            art_dict['logo'] = col_data['clearlogo']
        elif section_logo:
            art_dict['clearlogo'] = section_logo
            art_dict['logo'] = section_logo
            
        try: li.setArt(art_dict)
        except Exception: pass
        
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'collection': c_name}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        if genre_filter and str(genre_filter).lower() != 'premium': url_params['genre'] = genre_filter
        dir_items.append((build_url(url_params), li, True))
        
    q_base = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'group': 'collection'}
    if is_premium_req: q_base['base_genre'] = 'Premium'
    if genre_filter and str(genre_filter).lower() != 'premium': q_base['genre'] = genre_filter

    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = q_base.copy()
        q_prev['page'] = page - 1
        dir_items.append((build_url(q_prev), li_prev, True))

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = q_base.copy()
        q_next['page'] = page + 1
        dir_items.append((build_url(q_next), li_next, True))
        
    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
    xbmcplugin.setPluginFanart(HANDLE, ADDON_FANART)
    xbmcplugin.endOfDirectory(HANDLE)

def list_items(filter_type=None, page=1, action_name=None, group_by=None, genre_filter=None, year_filter=None, quality_filter=None, letter_filter=None, collection_filter=None, original_params=None):
    xbmc.log(f"RusterWolf: list_items call (filter={filter_type}, page={page})", xbmc.LOGDEBUG)
    
    is_premium_req = False
    if genre_filter and genre_filter.lower() == 'premium':
        is_premium_req = True
    try:
        if original_params and original_params.get('base_genre', '').lower() == 'premium':
            is_premium_req = True
    except Exception: pass
    
    if not filter_type and (group_by in ('genre', 'year', 'quality', 'letter', 'collection') or genre_filter or year_filter or quality_filter or letter_filter):
        try:
            li_movie = xbmcgui.ListItem('Películas')
            art_m = {'fanart': ADDON_FANART}
            logo_m = _get_section_logo('peliculas')
            if logo_m: art_m['clearlogo'] = logo_m; art_m['logo'] = logo_m
            li_movie.setArt(art_m)
            try:
                li_movie.getVideoInfoTag().setPlot(SECTION_PLOTS.get('peliculas', ''))
            except Exception:
                pass
            
            base_params_m = {'action': 'list', 'filter': 'movie'}
            if group_by: base_params_m['group'] = group_by
            if genre_filter: base_params_m['genre'] = genre_filter
            if year_filter: base_params_m['year'] = year_filter
            if quality_filter: base_params_m['quality'] = quality_filter
            if letter_filter: base_params_m['letter'] = letter_filter
            
            xbmcplugin.addDirectoryItem(HANDLE, build_url(base_params_m), li_movie, True)

            li_tv = xbmcgui.ListItem('Series')
            art_t = {'fanart': ADDON_FANART}
            logo_t = _get_section_logo('series_tv')
            if logo_t: art_t['clearlogo'] = logo_t; art_t['logo'] = logo_t
            li_tv.setArt(art_t)
            try:
                li_tv.getVideoInfoTag().setPlot(SECTION_PLOTS.get('series_tv', ''))
            except Exception:
                pass
            
            base_params_t = base_params_m.copy()
            base_params_t['filter'] = 'tv'
            
            xbmcplugin.addDirectoryItem(HANDLE, build_url(base_params_t), li_tv, True)
            xbmcplugin.endOfDirectory(HANDLE)
            return
        except Exception: pass

    used_filter = filter_type
    try:
        if not used_filter and isinstance(original_params, dict):
            used_filter = original_params.get('filter') or original_params.get('origin')
    except Exception: pass

    if group_by == 'genre': return list_genres(filter_type=used_filter, original_params=original_params)
    if group_by == 'year': return list_years(filter_type=used_filter, genre_filter=genre_filter, original_params=original_params)
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

    ft = used_filter.strip().lower() if used_filter else ''
    if ft in ('tv', 'series', 'serie', 'series_documentary'):
        try: xbmcplugin.setContent(HANDLE, 'tvshows')
        except: pass
    elif ft in ('movie', 'pelicula', 'documentary'):
        try: xbmcplugin.setContent(HANDLE, 'movies')
        except: pass

    dir_items = []
    for it in page_items:
        li, url, is_folder = _create_item_and_url(it, ADDON_FANART, quality_filter)
        dir_items.append((url, li, is_folder))

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
        dir_items.append((build_url(q_prev), li_prev, True))

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = q_base.copy()
        q_next['page'] = page + 1
        dir_items.append((build_url(q_next), li_next, True))

    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
    xbmcplugin.endOfDirectory(HANDLE)

def novedades(page=1, sub=None, genre_filter=None, original_params=None):
    used_filter = None
    if sub in ('movies', 'movie', 'pelicula'): used_filter = 'movie'
    elif sub in ('series', 'tv', 'serie'): used_filter = 'tv'
    elif sub == 'documentary': used_filter = 'documentary'
    elif sub == 'series_documentary': used_filter = 'series_documentary'

    # Red de seguridad extrema por si 'sub' no llega pero 'filter' sí
    if not used_filter and isinstance(original_params, dict):
        used_filter = original_params.get('filter') or original_params.get('origin')

    is_premium_req = False
    if original_params and original_params.get('base_genre', '').lower() == 'premium':
        is_premium_req = True
        
    sort_by = original_params.get('sort_by', 'date_added') if original_params else 'date_added'

    from resources.lib.db import get_filtered_items
    per_page = _read_items_per_page()
    offset = (page - 1) * per_page
    limit = per_page + 1

    results = get_filtered_items(
        filter_type=used_filter,
        is_premium_req=is_premium_req,
        genre=genre_filter,
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )

    has_next_page = len(results) > per_page
    page_items = results[:per_page]

    ft = used_filter.strip().lower() if used_filter else ''
    if ft in ('tv', 'series', 'serie', 'series_documentary'):
        try: xbmcplugin.setContent(HANDLE, 'tvshows')
        except: pass
    elif ft in ('movie', 'pelicula', 'documentary'):
        try: xbmcplugin.setContent(HANDLE, 'movies')
        except: pass

    dir_items = []
    for it in page_items:
        li, url, is_folder = _create_item_and_url(it, ADDON_FANART)
        dir_items.append((url, li, is_folder))

    base_q = {'action': 'novedades'}
    if sub: base_q['sub'] = sub
    if genre_filter: base_q['genre'] = genre_filter
    if is_premium_req: base_q['base_genre'] = 'Premium'
    if sort_by != 'date_added': base_q['sort_by'] = sort_by

    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = base_q.copy()
        q_prev['page'] = page - 1
        dir_items.append((build_url(q_prev), li_prev, True))

    if has_next_page:
        li_next = xbmcgui.ListItem(label='Siguiente página')
        q_next = base_q.copy()
        q_next['page'] = page + 1
        dir_items.append((build_url(q_next), li_next, True))

    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
    xbmcplugin.endOfDirectory(HANDLE)

def list_seasons(series, target_quality=None):
    """Lista las temporadas disponibles para una serie (por título de serie)."""
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
    
    dir_items = []
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
                _apply_art(li, rep, ADDON_FANART)
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
            
        is_watched = info.get('playcount', 0) > 0
        cm = generate_context_menu('season', None, None, is_watched)
        if cm: li.addContextMenuItems(cm)
        
        q_params = {'action': 'list_episodes', 'series': series, 'season': season}
        if target_quality:
            q_params['target_quality'] = target_quality
        url = build_url(q_params)
        dir_items.append((url, li, True))
    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
    xbmcplugin.endOfDirectory(HANDLE)

def list_episodes(series, season, target_quality=None):
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
    
    dir_items = []
    for it in sorted(episodes, key=lambda x: int(x.get('episode') or 0)):
        try:
            ep_num = int(it.get('episode') or 0)
        except Exception:
            ep_num = 0

        ep_title = it.get('episode_title') or it.get('title') or f"Episodio {ep_num}"

        li = xbmcgui.ListItem(label=ep_title)
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
                _apply_art(li, it if isinstance(it, dict) else {'poster': poster, 'fanart': it.get('fanart') or ''}, ADDON_FANART)
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
        
        is_watched = info.get('playcount', 0) > 0
        cm = generate_context_menu('episode', None, None, is_watched)
        if cm: li.addContextMenuItems(cm)
        
        q_params = {'action': 'select'}
        if item_key:
            q_params['key'] = item_key
        else:
            q_params['index'] = str(catalog.index(it))
        if target_quality:
            q_params['target_quality'] = target_quality
        url = build_url(q_params)
        dir_items.append((url, li, False))
    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
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
    
    try:
        # Búsqueda optimizada por SQL
        from resources.lib.db import search_items_sql
        results = search_items_sql(q, limit=150) # Límite ampliado, rendimiento mejorado
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
    
    dir_items = []
    # Mostrar series agrupadas
    for key, items_group in sorted(series_map.items(), key=lambda x: x[0]):
        # Elegir representante con mejor metadata
        rep = sorted(items_group, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
        li, url, is_folder = _create_item_and_url(rep, ADDON_FANART)
        dir_items.append((url, li, is_folder))
    
    # Mostrar películas
    for it in movies:
        li, url, is_folder = _create_item_and_url(it, ADDON_FANART)
        dir_items.append((url, li, is_folder))
    
    xbmcplugin.addDirectoryItems(HANDLE, dir_items)
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

    # Filtro de calidad máxima según ajustes
    try:
        max_q_setting = ADDON.getSetting('max_quality')
        if max_q_setting == '1': # 1080p
            sources = [s for s in sources if _q_rank(s) <= 9]
        elif max_q_setting == '2': # 720p
            sources = [s for s in sources if _q_rank(s) <= 8]
        elif max_q_setting == '3': # SD
            sources = [s for s in sources if _q_rank(s) < 8]
    except Exception: pass

    if not sources:
        xbmcgui.Dialog().notification('RusterWolf 77', 'No hay fuentes para la calidad elegida en Ajustes', xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

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
        try:
            auto_play = ADDON.getSettingBool('auto_play')
        except Exception:
            auto_play = False
            
        if len(sources) == 1 or auto_play:
            sel = 0
        else:
            choices = []
            for s in sources:
                source_type = s.get('source', 'magnet')
                q_str = str(s.get('quality', 'SD')).upper()
                
                # Colores identificativos por calidad
                if '4K' in q_str or '2160' in q_str: color = 'gold'
                elif '1080' in q_str: color = 'lawngreen'
                elif '720' in q_str: color = 'deepskyblue'
                elif 'MICROHD' in q_str: color = 'orchid'
                else: color = 'tomato'
                        
                if source_type == "1fichier_palantir":
                            choices.append(f"[ALLDEBRID] [COLOR {color}][B]{q_str}[/B][/COLOR] | {s.get('audio', '')} | {s.get('info', '')}")
                else:
                            choices.append(f"[TORRENT] [COLOR {color}][B]{q_str}[/B][/COLOR]")

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

    # 3. Decidir qué reproductor usar
    if source_type == '1fichier_palantir':
        if not alldebrid_api_key:
            xbmcgui.Dialog().ok("Acceso Requerido", "Esta fuente requiere una cuenta de AllDebrid.\nPor favor, introduce tu API Key en los ajustes del addon.")
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        final_url = play_1fichier_with_alldebrid(url, alldebrid_api_key)
    
    elif source_type == 'magnet':
        magnet_url = url
        used_debrid = False
        
        def _get_elementum_url(magnet):
            trackers = ["udp://tracker.opentrackr.org:1337/announce", "udp://open.demonii.com:1337/announce"]
            for tr in trackers:
                if tr not in magnet: magnet += f"&tr={urllib.parse.quote(tr)}"
            return f'plugin://plugin.video.elementum/play?uri={urllib.parse.quote_plus(magnet)}'
        
        # Prioridad Automática: AllDebrid -> Real-Debrid -> Elementum
        if alldebrid_api_key:
            used_debrid = True
            final_url = play_with_alldebrid(magnet_url, alldebrid_api_key)
        elif realdebrid_api_key:
            used_debrid = True
            final_url = play_with_realdebrid(magnet_url, realdebrid_api_key)
        else: # Elementum
            if not is_elementum_installed():
                xbmcgui.Dialog().ok('Instalar Elementum', 'Para ver contenido gratuito (P2P) necesitas tener instalado el motor torrent "Elementum" en tu Kodi.\n\nPuedes descargarlo desde:\n[COLOR yellow]https://elementumorg.github.io[/COLOR]\n\nO si lo prefieres, configura una cuenta Premium (Debrid) en Ajustes.')
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return
            final_url = _get_elementum_url(magnet_url)

        # Fallback a Elementum si usamos Debrid pero el enlace no está cacheado
        if not final_url and used_debrid:
            if is_elementum_installed():
                if xbmcgui.Dialog().yesno('No en caché', 'Este archivo no está en la caché de tu Debrid.\n\n¿Deseas descargarlo y reproducirlo en tiempo real usando el motor gratuito Elementum?'):
                    final_url = _get_elementum_url(magnet_url)
            else:
                xbmcgui.Dialog().ok('Enlace no cacheado', 'El archivo no está en caché de tu Debrid.\n\nPara reproducir este tipo de enlaces en tiempo real de forma gratuita, instala el motor torrent Elementum:\n[COLOR yellow]https://elementumorg.github.io[/COLOR]')
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return

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
        flag_file = os.path.join(userdata_dir, 'v3_db_migration.flag') # Nombre de flag específico
        
        if not xbmcvfs.exists(flag_file):
            xbmc.log("RusterWolf: Ejecutando limpieza/migración única post-actualización...", xbmc.LOGINFO)
            
            old_db_path = os.path.join(userdata_dir, 'cache.db')
            if xbmcvfs.exists(old_db_path):
                if xbmcvfs.delete(old_db_path):
                    xbmc.log("RusterWolf: Antigua 'cache.db' eliminada con éxito.", xbmc.LOGINFO)
                    
            old_bin_path = os.path.join(userdata_dir, 'archivos.bin')
            if xbmcvfs.exists(old_bin_path):
                xbmcvfs.delete(old_bin_path)
                xbmc.log("RusterWolf: Antiguo 'archivos.bin' eliminado del userdata con éxito.", xbmc.LOGINFO)
            
            # Migración de historial antiguo a JSON
            try:
                import glob, sqlite3, time
                from urllib.parse import urlparse, parse_qsl
                
                po = load_progress_override()
                kodi_db_dir = os.path.join(xbmcvfs.translatePath('special://profile/'), 'Database')
                kodi_dbs = glob.glob(os.path.join(kodi_db_dir, 'MyVideos*.db'))
                if kodi_dbs:
                    kodi_db = sorted(kodi_dbs, key=lambda p: os.path.getmtime(p), reverse=True)[0]
                    conn = sqlite3.connect(kodi_db)
                    cur = conn.cursor()
                    cur.execute("SELECT strFilename FROM files WHERE strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND (playCount > 0 OR idFile IN (SELECT idFile FROM bookmark WHERE type=1))")
                    changed = False
                    for row in cur.fetchall():
                        qs = dict(parse_qsl(urlparse(row[0]).query))
                        if 'key' in qs:
                            key_val = qs['key']
                            wtype = 'tv' if key_val.startswith('tv_') else 'movie'
                            
                            if wtype == 'tv':
                                parts = key_val.split('_')
                                if len(parts) >= 4:
                                    val = "_".join(parts[1:-2])
                                else: continue
                            else:
                                val = key_val
                                
                            if val not in po['manual'] and val not in po['hidden']:
                                po['manual'][val] = {'wtype': wtype, 'title': val.replace('_', ' ').title(), 'added': time.time()}
                                changed = True
                    conn.close()
                    if changed: save_progress_override(po)
            except Exception as e:
                xbmc.log(f"RusterWolf: Error migrando bookmarks a JSON: {e}", xbmc.LOGERROR)
            
            with xbmcvfs.File(flag_file, 'w') as f: f.write('done')
            xbmc.log("RusterWolf: Flag de migración creado.", xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f"RusterWolf: Error durante la limpieza única: {e}", xbmc.LOGERROR)

def router(params):
    import xbmc
    action = params.get('action')
    try:
        page = int(params.get('page') or 1)
    except Exception:
        page = 1
    xbmc.log(f"RusterWolf: router params={params}", xbmc.LOGDEBUG)
    # Detectar si la petición incluye una búsqueda por URL (query/name/q) o
    # el caso malformado action='search=texto' y, en ese caso, invocar
    # do_search(prefill) para evitar abrir el teclado.
    if action == 'add_watchlist':
        action_add_watchlist(params)
        return
    if action == 'remove_watchlist':
        action_remove_watchlist(params)
        return
    if action == 'add_progress':
        action_add_progress(params)
        return
    if action == 'remove_progress':
        action_remove_progress(params)
        return
    try:
        q_param = None
        if isinstance(params, dict):
            q_param = params.get('query') or params.get('name') or params.get('q')
        # Manejar acción malformada (ej. action='search=texto')
        if not q_param and isinstance(action, str) and action.startswith('search='):
            try:
                q_param = action.split('=', 1)[1]
                # Normalizar action para no romper el flujo
                action = 'search'
            except Exception:
                q_param = None
        if q_param:
            xbmc.log(f"RusterWolf: router detected query param in URL -> '{q_param}'", xbmc.LOGDEBUG)
            do_search(q_param, original_params=params)
            return
    except Exception:
        pass
        
    if action == 'force_sync':
        try:
            import xbmcvfs, os
            os.remove(os.path.join(xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}"), 'last_update.txt'))
        except Exception: pass
        from resources.lib.db import maybe_update_db_from_remote
        xbmcgui.Dialog().notification('RusterWolf', 'Descargando nueva BD...', xbmcgui.NOTIFICATION_INFO)
        maybe_update_db_from_remote(force=True)
        xbmc.executebuiltin('Container.Refresh')
        return

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
        xbmc.log(f"RusterWolf: router mapped action={action} to filter_type={filter_type}", xbmc.LOGDEBUG)
        list_items(filter_type=filter_type, page=page, action_name=action,
                   group_by=params.get('group'), genre_filter=params.get('genre'), year_filter=params.get('year'), quality_filter=params.get('quality'), letter_filter=params.get('letter'), collection_filter=params.get('collection'), original_params=params)
        return
    elif action == 'list':
        # Si se solicitó agrupación (por género/año) pero no se indicó filter (movie/tv),
        # intentar usar 'origin' como fallback cuando 'filter' no venga.
        flt = params.get('filter') or params.get('origin')
        
        # Fallback en RAM: si una Skin recarga el contenedor y pierde los parámetros,
        # leemos la URL original directamente de la memoria activa de Kodi sin usar el disco.
        if not flt:
            try:
                parent_path = xbmc.getInfoLabel('Container.FolderPath')
                if parent_path:
                    parent_q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(parent_path).query))
                    flt = parent_q.get('filter') or parent_q.get('origin')
            except Exception:
                pass
                
        xbmc.log(f"RusterWolf: router llama a list_items con filter_type={flt} page={page}", xbmc.LOGDEBUG)
        
        def cln(v): return None if str(v) == 'None' else v
        
        list_items(filter_type=cln(flt), page=page, action_name='list',
                   group_by=cln(params.get('group')), genre_filter=cln(params.get('genre')), 
                   year_filter=cln(params.get('year')), quality_filter=cln(params.get('quality')), 
                   letter_filter=cln(params.get('letter')), collection_filter=cln(params.get('collection')), 
                   original_params=params)
        return
    elif action == 'dibujos_main_menu': _generic_main_menu('Dibujos', 'Dibujo', 'dibujos')
    elif action == 'anime_main_menu': _generic_main_menu('Anime', 'Anime', 'anime')
    elif action == 'retro_main_menu': _generic_main_menu('Retro', 'Retro', 'retro')
    elif action == 'genre_movie_menu': genre_sub_menu('movie', params.get('genre'), params.get('safe_id'))
    elif action == 'genre_tv_menu': genre_sub_menu('tv', params.get('genre'), params.get('safe_id'))
    elif action == 'novedades':
        novedades(page=page, sub=params.get('sub'), genre_filter=params.get('genre'), original_params=params)
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
    xbmc.log(f"RusterWolf: __main__ params={params}", xbmc.LOGDEBUG)

    # Limpieza única post-actualización (borrado de caché antigua)
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
            from resources.lib.db import ensure_session_db, _is_db_valid, maybe_update_db_from_remote
            ensure_session_db()
            # Si la BD no existe en Temp (ej. Android TV limpió la caché al reiniciar), la descargamos para los widgets
            if not _is_db_valid():
                maybe_update_db_from_remote(force=False)
        except Exception: pass
    router(params)
