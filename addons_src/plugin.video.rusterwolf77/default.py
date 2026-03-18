# -*- coding: utf-8 -*-
import sys, xbmc, xbmcgui, xbmcplugin, xbmcaddon, urllib.parse, xbmcvfs
import json
import unicodedata, re, os, threading, time
from resources.lib.player import is_elementum_installed, play_with_elementum
from resources.lib.db import load_all_items, load_items_by_keys

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
            if addon_fanart:
                art['fanart'] = addon_fanart
                try:
                    li.setArt(art)
                except Exception:
                    pass
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
        if addon_fanart:
            try:
                li.setArt({'fanart': addon_fanart})
            except Exception:
                pass
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
    except Exception as e:
        xbmc.log(f"RusterWolf: error aplicando InfoTagVideo: {e}", xbmc.LOGERROR)

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
    xbmcgui.Dialog().notification('RusterWolf', f'{title} añadido a Seguir Viendo')

def action_remove_watchlist(params):
    uid = params.get('uid')
    wl = load_watchlist()
    if uid in wl:
        del wl[uid]
        save_watchlist(wl)
        xbmcgui.Dialog().notification('RusterWolf', 'Eliminado de Seguir Viendo')
        xbmc.executebuiltin('Container.Refresh')
# --------------------------------------------------------


def list_root():
    items = [
        ('Zona Premium', {'action':'premium_menu'}),
        ('Novedades', {'action':'novedades_menu'}),
        ('Seguir Viendo...', {'action':'continue_watching'}), 
        ('Películas', {'action':'movie_menu'}),
        ('Series TV', {'action':'tv_menu'}),
        ('Documentales', {'action':'documentary_menu'}),
        ('Series Documental', {'action':'series_documentary_menu'}),
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
        icon_name = f"{safe_label}.png"
        custom_icon_path = os.path.join(addon_path, 'resources', 'media', icon_name)
        icon_to_use = custom_icon_path if os.path.exists(custom_icon_path) else default_icon

        try:
            li.setArt({'fanart': addon_fanart, 'icon': icon_to_use, 'thumb': icon_to_use})
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
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        
        if 'Películas' in label:
            icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas.png')
        else:
            icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv.png')
            
        if not os.path.exists(icon_path):
            icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
            
        li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
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
        ('Título', {'action': 'list', 'filter': 'movie', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Género', {'action': 'list', 'filter': 'movie', 'group': 'genre', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'group': 'quality', 'base_genre': 'Premium', 'origin': 'movie'}),
        ('Año', {'action': 'list', 'filter': 'movie', 'group': 'year', 'base_genre': 'Premium', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle(label)
        except Exception: pass
        li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
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
        ('Título', {'action': 'list', 'filter': 'tv', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Género', {'action': 'list', 'filter': 'tv', 'group': 'genre', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'group': 'quality', 'base_genre': 'Premium', 'origin': 'tv'}),
        ('Año', {'action': 'list', 'filter': 'tv', 'group': 'year', 'base_genre': 'Premium', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try: info_tag = li.getVideoInfoTag(); info_tag.setTitle(label)
        except Exception: pass
        li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def novedades_menu():
    """Submenú para Novedades: accesos directos a películas y series recientes."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'novedades.png')
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
    
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        try:
            li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
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
    icon_path = os.path.join(addon_path, 'resources', 'media', 'seguir_viendo.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')

    xbmcplugin.setContent(HANDLE, 'movies')

    # Cargar catálogo local para poder enriquecer items si es posible
    try:
        from resources.lib.db import load_all_items, load_items_by_keys
        catalog = load_all_items() or []
    except Exception:
        catalog = []

    # 1. Cargar Watchlist manual
    wl = load_watchlist()
    if wl:
        # Ordenar por fecha de añadido descendente
        for uid, witem in sorted(wl.items(), key=lambda x: x[1].get('added', 0), reverse=True):
            try:
                wtype = witem.get('wtype')
                val = witem.get('val')
                wtitle = witem.get('title')
                
                li = None
                url = None
                isFolder = True
                
                if wtype == 'tv':
                    series_items = [i for i in catalog if _get_item_type(i) == 'tv' and normalize_title(_get_item_title(i)) == normalize_title(val)]
                    if not series_items: 
                        li = xbmcgui.ListItem(label=wtitle)
                    else:
                        rep = sorted(series_items, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
                        li = xbmcgui.ListItem(label=rep.get('title') or wtitle)
                        _apply_art(li, rep, addon_fanart)
                    _apply_info_tag(li, {'title': rep.get('title'), 'plot': rep.get('overview'), 'mediatype': 'tvshow'})
                    url = build_url({'action': 'list_seasons', 'series': val})
                
                elif wtype == 'movie':
                    found = [i for i in catalog if i.get('key') == val]
                    if found:
                        it = found[0]
                        li = xbmcgui.ListItem(label=it.get('title'))
                        _apply_art(li, it, addon_fanart)
                        _apply_info_tag(li, {'title': it.get('title'), 'plot': it.get('overview'), 'mediatype': 'movie'})
                        url = build_url({'action': 'select', 'key': val})
                        isFolder = False
                
                if li and url:
                    cm = []
                    rm_url = build_url({'action': 'remove_watchlist', 'uid': uid})
                    cm.append(('Quitar de Seguir Viendo', f'RunPlugin({rm_url})'))
                    li.addContextMenuItems(cm)
                    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder)
            except Exception as e:
                xbmc.log(f"RusterWolf: error en watchlist item: {e}", xbmc.LOGERROR)

    # índice simple por key para acceso rápido
    catalog_by_key = {}
    for it in catalog:
        try:
            k = it.get('key')
            if k:
                catalog_by_key[str(k)] = it
        except Exception:
            continue

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
            cur.execute("SELECT b.idBookmark, b.idFile, b.timeInSeconds, b.totalTimeInSeconds, f.strFilename FROM bookmark b JOIN files f ON b.idFile = f.idFile ORDER BY b.idBookmark DESC LIMIT 200")
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

    # Si no hay bookmarks ni watchlist, informar y cerrar el contenedor
    if not bookmarks and not wl:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        try:
            info_tag = li.getVideoInfoTag(); info_tag.setTitle('No hay contenido en progreso')
        except Exception:
            pass
        try:
            li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
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
                                catalog_item = items[0] if items else catalog_by_key.get(k)
                            except Exception:
                                catalog_item = catalog_by_key.get(k)
                        elif 'index' in qs:
                            try:
                                idx = int(qs.get('index')[0])
                                if 0 <= idx < len(catalog):
                                    catalog_item = catalog[idx]
                            except Exception:
                                catalog_item = None
                    except Exception:
                        catalog_item = None
            except Exception:
                catalog_item = None

            # si no hay catalog_item, intentar heurística por nombre de fichero
            if catalog_item is None and filename:
                nf = filename.lower()
                for it in catalog:
                    try:
                        t = (it.get('title') or '').lower()
                        pt = str(it.get('parsed', {}).get('title') or '').lower()
                        if t and t in nf:
                            catalog_item = it
                            break
                        if pt and pt in nf:
                            catalog_item = it
                            break
                    except Exception:
                        continue

            if catalog_item:
                display_title = catalog_item.get('title') or display_title
                try:
                    xbmc.log(f"RusterWolf: continue_watching matched catalog item key={catalog_item.get('key')} title={catalog_item.get('title')}", xbmc.LOGDEBUG)
                except Exception:
                    pass

            # si la filename es una URL a nuestro plugin, intentar extraer index/key
            try:
                parsed = urllib.parse.urlparse(filename)
                if parsed.scheme == 'plugin' or (parsed.scheme in ('http', 'https') and 'plugin.video.rusterwolf77' in filename):
                    qs = urllib.parse.parse_qs(parsed.query)
                    # mostrar la URL tal cual; el router resolverá 'select'
                    display_title = filename
            except Exception:
                pass

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
                try:
                    li.setArt(art)
                except Exception:
                    pass
            except Exception:
                try:
                    li.setArt({'fanart': addon_fanart})
                except Exception:
                    pass

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
    

def movie_menu():
    """Submenú para Películas: por título, por género, por año, novedades."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'movie', 'origin': 'movie'}),
        ('Género', {'action': 'list', 'filter': 'movie', 'group': 'genre', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'group': 'quality', 'origin': 'movie'}),
        ('Año', {'action': 'list', 'filter': 'movie', 'group': 'year', 'origin': 'movie'}),
        ('Novedades (Películas)', {'action': 'novedades', 'sub': 'movies', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'peliculas.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        try:
            li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
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
        ('Título', {'action': 'list', 'filter': 'tv', 'origin': 'tv'}),
        ('Género', {'action': 'list', 'filter': 'tv', 'group': 'genre', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'group': 'quality', 'origin': 'tv'}),
        ('Año', {'action': 'list', 'filter': 'tv', 'group': 'year', 'origin': 'tv'}),
        ('Novedades (Series)', {'action': 'novedades', 'sub': 'series', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_tv.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception:
            pass
        try:
            li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
        except Exception:
            pass
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def documentary_menu():
    """Submenú para Documentales."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'movie', 'genre': 'Documental', 'origin': 'movie'}),
        ('Calidad', {'action': 'list', 'filter': 'movie', 'genre': 'Documental', 'group': 'quality', 'origin': 'movie'}),
        ('Novedades', {'action': 'novedades', 'sub': 'documentary', 'origin': 'movie'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'documentales.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def series_documentary_menu():
    """Submenú para Series Documental."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    entries = [
        ('Título', {'action': 'list', 'filter': 'tv', 'genre': 'Documental', 'origin': 'tv'}),
        ('Calidad', {'action': 'list', 'filter': 'tv', 'genre': 'Documental', 'group': 'quality', 'origin': 'tv'}),
        ('Novedades', {'action': 'novedades', 'sub': 'series_documentary', 'origin': 'tv'})
    ]
    xbmcplugin.setContent(HANDLE, 'files')
    icon_path = os.path.join(addon_path, 'resources', 'media', 'series_documental.png')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    for label, params in entries:
        li = xbmcgui.ListItem(label)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(label)
        except Exception: pass
        li.setArt({'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path})
        url = build_url(params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)


def list_genres(filter_type=None, original_params=None):
    """Listar géneros presentes en la base (filtrando por tipo si se indica)."""
    # Prefer DB-backed items when possible (reflects cache.db used by Kodi)
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
        
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    genres = {}
    for it in catalog:
        if _is_item_premium(it) and not is_premium_req: continue
        if not _is_item_premium(it) and is_premium_req: continue
        
        t = _get_item_type(it)
        if filter_type and t != (filter_type or ''):
            continue
        for g in (_get_item_genres(it) or []):
            gname = g['name'] if isinstance(g, dict) and 'name' in g else str(g)
            if gname.strip().lower() == 'premium': continue
            genres.setdefault(gname, []).append(it)
    # default to movies when caller doesn't specify
    if not filter_type:
        filter_type = 'movie'
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    icon_map = {
        'movie': 'peliculas.png',
        'tv': 'series_tv.png',
        'documentary': 'documentales.png',
        'series_documentary': 'series_documental.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    xbmcplugin.setContent(HANDLE, 'files')
    for gname in sorted(genres.keys()):
        li = xbmcgui.ListItem(label=gname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(gname)
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        try:
            li.setArt({'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart})
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
    """Listar años presentes en la base (filtrando por tipo si se indica)."""
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
        
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    years = {}
    for it in catalog:
        if _is_item_premium(it) and not is_premium_req: continue
        if not _is_item_premium(it) and is_premium_req: continue
        
        t = _get_item_type(it)
        if filter_type and t != (filter_type or ''):
            continue
        y = str(_get_item_year(it) or '')
        years.setdefault(y, []).append(it)
    # default to movies when caller doesn't specify
    if not filter_type:
        filter_type = 'movie'
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')

    icon_map = {
        'movie': 'peliculas.png',
        'tv': 'series_tv.png',
        'documentary': 'documentales.png',
        'series_documentary': 'series_documental.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    xbmcplugin.setContent(HANDLE, 'files')
    for y in sorted([k for k in years.keys() if k], reverse=True):
        li = xbmcgui.ListItem(label=f'Año {y}')
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(f'Año {y}')
        except Exception:
            pass
        # use addon icon so skins render this list as square/icon like the main menu
        try:
            li.setArt({'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart})
        except Exception:
            pass
        url_params = {'action': 'list', 'filter': filter_type, 'origin': filter_type, 'year': y}
        if is_premium_req: url_params['base_genre'] = 'Premium'
        url = build_url(url_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.setPluginFanart(HANDLE, addon_fanart)
    xbmcplugin.endOfDirectory(HANDLE)

def list_qualities(filter_type=None, genre_filter=None, original_params=None):
    """Listar calidades presentes en la base (filtrando por tipo y opcionalmente género)."""
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
    
    is_premium_req = False
    if original_params and (original_params.get('base_genre', '').lower() == 'premium' or original_params.get('genre', '').lower() == 'premium'):
        is_premium_req = True
        
    qualities = set()
    gf = (genre_filter or '').strip().lower()
    if gf == 'premium': gf = ''

    for it in catalog:
        if _is_item_premium(it) and not is_premium_req: continue
        if not _is_item_premium(it) and is_premium_req: continue
        
        t = _get_item_type(it)
        if filter_type and t != (filter_type or ''):
            continue
        
        # Filtrado previo por género si es necesario (ej: Documentales)
        if gf:
            matched = False
            for g in (_get_item_genres(it) or []):
                gname = (g.get('name') if isinstance(g, dict) and 'name' in g else str(g)).strip()
                if gname and (gf in gname.lower() or gname.lower() in gf):
                    matched = True
                    break
            if not matched:
                continue

        for tor in (it.get('torrents') or []):
            q = tor.get('quality')
            if q:
                s = str(q).strip()
                if s.lower() == 'dvdrip':
                    s = '1080p'
                # Unificar 2160p y 4k en '4K'
                elif s.lower() in ('2160p', '4k'):
                    s = '4K'
                qualities.add(s)

    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    
    # Usar icono por defecto o mapeado
    icon_map = {
        'movie': 'peliculas.png',
        'tv': 'series_tv.png',
        'documentary': 'documentales.png',
        'series_documentary': 'series_documental.png'
    }
    use_icon = icon_map.get(filter_type, 'icon.png')
    icon_path = os.path.join(addon_path, 'resources', 'media', use_icon)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(addon_path, 'resources', 'media', 'icon.png')
    
    xbmcplugin.setContent(HANDLE, 'files')
    for qname in sorted(list(qualities)):
        li = xbmcgui.ListItem(label=qname)
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(qname)
        except Exception:
            pass
        try:
            li.setArt({'icon': icon_path, 'thumb': icon_path, 'fanart': addon_fanart})
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

def list_items(filter_type=None, page=1, action_name=None, group_by=None, genre_filter=None, year_filter=None, quality_filter=None, original_params=None):
    xbmc.log(f"RusterWolf DEBUG: === list_items CALL === filter={filter_type} page={page}", xbmc.LOGWARNING)
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    xbmc.log(f"RusterWolf DEBUG: loaded catalog size={len(catalog)}", xbmc.LOGWARNING)
    
    is_premium_req = False
    if genre_filter and genre_filter.lower() == 'premium':
        is_premium_req = True
    try:
        if original_params and original_params.get('base_genre', '').lower() == 'premium':
            is_premium_req = True
    except Exception: pass
    
    results = []
    for it in catalog:
        if _is_item_premium(it) and not is_premium_req: continue
        if not _is_item_premium(it) and is_premium_req: continue
        
        mediatype = _get_item_type(it)
        genres = _get_item_genres(it) or []
        if filter_type == 'movie' and mediatype == 'movie':
            results.append(it)
        elif filter_type == 'tv' and mediatype == 'tv':
            # Para TV no añadimos episodios individuales aquí; agruparemos por serie en la UI
            results.append(it)
        elif filter_type == 'documentary':
            genre_names = [g['name'].lower() if isinstance(g, dict) and 'name' in g else str(g).lower() for g in genres] if isinstance(genres, list) else [str(genres).lower()]
            if mediatype == 'movie' and any('documental' in g or 'documentary' in g for g in genre_names):
                results.append(it)
        elif filter_type == 'series_documentary':
            genre_names = [g['name'].lower() if isinstance(g, dict) and 'name' in g else str(g).lower() for g in genres] if isinstance(genres, list) else [str(genres).lower()]
            if mediatype == 'tv' and any('documental' in g or 'documentary' in g for g in genre_names):
                results.append(it)
        elif filter_type is None:
            results.append(it)

    # If caller asked to group (genre/year) but didn't specify movie/tv, present a small chooser
    if not filter_type and group_by in ('genre', 'year', 'quality'):
        try:
            # show two folders: Películas and Series that link back with explicit filter
            li_movie = xbmcgui.ListItem('Películas')
            li_movie.setArt({'fanart': addon_fanart})
            url_movie = build_url({'action': 'list', 'filter': 'movie', 'group': group_by})
            xbmcplugin.addDirectoryItem(HANDLE, url_movie, li_movie, True)
            li_tv = xbmcgui.ListItem('Series')
            li_tv.setArt({'fanart': addon_fanart})
            url_tv = build_url({'action': 'list', 'filter': 'tv', 'group': group_by})
            xbmcplugin.addDirectoryItem(HANDLE, url_tv, li_tv, True)
            xbmcplugin.endOfDirectory(HANDLE)
            return
        except Exception:
            pass

    # If caller passed a genre/year filter but didn't provide filter_type (movie/tv),
    # require explicit choice to avoid ambiguous inference between movie/tv.
    if filter_type is None and (genre_filter or year_filter or quality_filter):
        try:
            li_movie = xbmcgui.ListItem('Películas')
            li_movie.setArt({'fanart': addon_fanart})
            url_movie = build_url({'action': 'list', 'filter': 'movie', 'genre': genre_filter, 'year': year_filter, 'quality': quality_filter})
            xbmcplugin.addDirectoryItem(HANDLE, url_movie, li_movie, True)
            li_tv = xbmcgui.ListItem('Series')
            li_tv.setArt({'fanart': addon_fanart})
            url_tv = build_url({'action': 'list', 'filter': 'tv', 'genre': genre_filter, 'year': year_filter, 'quality': quality_filter})
            xbmcplugin.addDirectoryItem(HANDLE, url_tv, li_tv, True)
            xbmcplugin.endOfDirectory(HANDLE)
            return
        except Exception:
            pass
    # Compute a fallback filter from original_params (router query) when filter_type is None.
    used_filter = filter_type
    try:
        if not used_filter and isinstance(original_params, dict):
            used_filter = original_params.get('filter') or original_params.get('origin')
    except Exception:
        pass

    # ... cache write will be realizado más abajo después de inferir used_filter

    # Si aún no hay used_filter, intentar inferirlo a partir de los resultados (si son homogéneos)
    try:
        if not used_filter and isinstance(results, list) and results:
            tcounts = {'movie': 0, 'tv': 0}
            for it in results:
                tt = _get_item_type(it)
                if tt in tcounts:
                    tcounts[tt] += 1
            # si todos son TV o todas son películas, usamos ese filtro
            if tcounts['tv'] > 0 and tcounts['movie'] == 0:
                used_filter = 'tv'
            elif tcounts['movie'] > 0 and tcounts['tv'] == 0:
                used_filter = 'movie'
    except Exception:
        pass

    # Guardar la consulta actual en un cache local para recuperación posterior
    try:
        current_q = {'action': action_name or 'list', 'page': page}
        if used_filter:
            current_q['filter'] = used_filter
        if group_by:
            current_q['group'] = group_by
        if genre_filter:
            current_q['genre'] = genre_filter
        if year_filter:
            current_q['year'] = year_filter
        if quality_filter:
            current_q['quality'] = quality_filter
        try:
            current_url = build_url(current_q)
        except Exception:
            current_url = None
        if current_url:
            try:
                try:
                    profile_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}")
                except Exception:
                    profile_dir = os.path.join(ADDON.getAddonInfo('path'), 'cache')
                os.makedirs(profile_dir, exist_ok=True)
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
                # Mantener un tamaño limitado (últimas 200 entradas)
                entries[current_url] = current_q
                if len(entries) > 200:
                    keys = list(entries.keys())[-200:]
                    entries = {k: entries[k] for k in keys}
                # Update last_filters for action
                try:
                    act = current_q.get('action')
                    if act and current_q.get('filter'):
                        last_filters[act] = current_q.get('filter')
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
    except Exception:
        pass

    # aplicar filtrado adicional por género/año si se solicitó (utilizado por los menús "por género"/"por año")
    if genre_filter:
        gf = (genre_filter or '').strip().lower()
        if gf != 'premium':
            _f = []
            for it in results:
                matched = False
                for g in (_get_item_genres(it) or []):
                    gname = (g.get('name') if isinstance(g, dict) and 'name' in g else str(g)).strip()
                    if not gname:
                        continue
                    gn = gname.lower()
                    # match if the requested genre is a substring of the genre name or viceversa
                    if gf and (gf in gn or gn in gf):
                        matched = True
                        break
                if matched:
                    _f.append(it)
            results = _f
        try:
            xbmc.log(f"RusterWolf: after genre_filter={genre_filter} normalized={gf} remaining={len(results)}", xbmc.LOGDEBUG)
        except Exception:
            pass
    if year_filter:
        yf = str(year_filter)
        results = [it for it in results if str(_get_item_year(it) or '') == yf]
        try:
            xbmc.log(f"RusterWolf: after year_filter={year_filter} remaining={len(results)}", xbmc.LOGDEBUG)
        except Exception:
            pass

    # Filtrar por calidad si se solicita
    if quality_filter:
        qf = quality_filter.strip().lower()
        # Soporte para alias (ej: 4K incluye 2160p)
        target_qualities = {qf}
        if qf == '4k':
            target_qualities.add('2160p')

        _q = []
        for it in results:
            # Comprobar si alguno de los torrents tiene la calidad exacta solicitada
            has_quality = False
            for tor in (it.get('torrents') or []):
                tq = str(tor.get('quality') or '').strip().lower()
                if tq == 'dvdrip': tq = '1080p'
                if tq in target_qualities:
                    has_quality = True
                    break
            if has_quality:
                _q.append(it)
        results = _q

    # asegurar filtrado por tipo si filter_type está presente (evita mezclar tipos en vistas agrupadas)
    if filter_type:
        results = [it for it in results if _get_item_type(it) == filter_type]
    # paginación (page se pasa desde router)
    per_page = _read_items_per_page()
    start = (page - 1) * per_page
    end = start + per_page
    page_items = results[start:end]
    try:
        xbmc.log(f"RusterWolf: pagination DEBUG filter={filter_type} total_results={len(results)} page={page} per_page={per_page} start={start} end={end}", xbmc.LOGDEBUG)
    except Exception:
        pass
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
            # Some Kodi builds don't expose setGenre on InfoTagVideo; avoid calling it to prevent errors
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
        except Exception as e:
            xbmc.log(f"RusterWolf: error aplicando InfoTagVideo: {e}", xbmc.LOGERROR)

    def _apply_art(li, item_dict, addon_fanart=None):
        """Helper mínimo para añadir arte extra si está disponible en el item.
        Añade keys: poster/thumb, fanart, clearlogo, banner, clearart.
        """
        try:
            art = {}
            if not isinstance(item_dict, dict):
                return
            poster = item_dict.get('poster') or item_dict.get('poster_path') or ''
            if poster:
                art['poster'] = poster
                art['thumb'] = poster
            fanart = item_dict.get('fanart') or item_dict.get('backdrop_path') or ''
            if fanart:
                art['fanart'] = fanart
            # extra art metadata commonly used
            for k in ('clearlogo', 'banner', 'clearart'):
                v = item_dict.get(k)
                if v:
                    art[k] = v
                    # also expose common alias keys so skins that check 'logo' or 'icon' find them
                    if k == 'clearlogo':
                        art['logo'] = v
                        art['icon'] = v
                    if k == 'clearart' and 'icon' not in art:
                        art['icon'] = v
            # fallback to addon fanart
            if 'fanart' not in art and addon_fanart:
                art['fanart'] = addon_fanart
            if art:
                try:
                    li.setArt(art)
                except Exception:
                    pass
        except Exception:
            pass

    # quitar acentos
    def normalize_title(s):
        if not s:
            return ''
        s2 = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
        s2 = s2.lower()
        # quitar artículos comunes al inicio
        s2 = re.sub(r"^(the |la |el |los |las |un |una |el\s)", '', s2)
        # quitar puntuación y múltiples espacios
        s2 = re.sub(r"[^a-z0-9 ]+", ' ', s2)
        s2 = re.sub(r"\s+", ' ', s2).strip()
        return s2

    # tratar 'series_documentary' igual que 'tv' (misma estructura por series y temporadas)
    if filter_type in ('tv', 'series_documentary'):
        # Forzar vista 'tvshows' para listados de series (incluyendo filtros por género/año)
        # pero NO forzar cuando se está pidiendo una agrupación (group_by)
        try:
            if not group_by:
                try:
                    xbmcplugin.setContent(HANDLE, 'tvshows')
                except Exception:
                    pass
        except Exception:
            pass
        series_map = {}
        for it in results:
            title = _get_item_title(it)
            if not title:
                continue
            key = normalize_title(title)
            series_map.setdefault(key, []).append(it)

        # aplicar paginación en el listado de series normalizadas
        # si se pidió agrupar por año o por género en la vista de series, construir grupos distintos
        if group_by == 'genre':
            # si viene group_by sin genre_filter, mostrar carpeta con géneros
            return list_genres(filter_type='tv', original_params=original_params)
        if group_by == 'year':
            return list_years(filter_type='tv', original_params=original_params)
        if group_by == 'quality':
            return list_qualities(filter_type='tv', genre_filter=genre_filter, original_params=original_params)
        series_keys = sorted(series_map.items(), key=lambda x: x[0])
        total_pages = (len(series_keys) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paged_series = series_keys[start:end]
        for key, items_group in paged_series:
            # Elegir representante: preferir item con poster, luego con overview, si no el primero
            items_sorted = sorted(items_group, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)
            rep = items_sorted[0]
            display_title = rep.get('title') or (items_group[0].get('title') if items_group else key)
            li = xbmcgui.ListItem(label=display_title)
            # aplicar poster/overview si existen
            poster = rep.get('poster') or ''
            fanart = rep.get('fanart') or ''
            overview = rep.get('overview') or ''
            info = {'title': display_title, 'plot': overview, 'mediatype': 'tvshow', 'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (rep.get('genres') or [])]), 'cast': rep.get('cast') or []}
            _apply_info_tag(li, info)
            # Also set full video info so Kodi UI can show genres/cast where supported
            try:
                safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
                li.setInfo('video', safe_info)
            except Exception:
                pass
            try:
                _apply_art(li, rep if 'rep' in locals() and isinstance(rep, dict) else {'poster': poster, 'fanart': fanart}, addon_fanart)
            except Exception:
                pass
            _set_unique_ids(li, rep)
            url = build_url({'action': 'list_seasons', 'series': display_title})
            xbmc.log(f"RusterWolf: add series item {display_title} -> {url}", xbmc.LOGDEBUG)
            
            # CM: Añadir a Seguir Viendo
            cm = []
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'tv', 'val': display_title, 'title': display_title})
            cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
            li.addContextMenuItems(cm)
            
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)

        # añadir control de paginación: 'Anterior' y 'Siguiente' cuando proceda
        # usar número de series agrupadas para calcular páginas
        series_keys = sorted(series_map.items(), key=lambda x: x[0])
        total_pages = (len(series_keys) + per_page - 1) // per_page
        # construir base de query respetando action_name si fue provisto
        base_action = action_name or 'list'
        if page > 1:
            li_prev = xbmcgui.ListItem(label='Página anterior')
            q = {'action': base_action, 'page': page - 1}
            if used_filter:
                q['filter'] = used_filter
            if group_by:
                q['group'] = group_by
            if genre_filter:
                q['genre'] = genre_filter
            if year_filter:
                q['year'] = year_filter
            if quality_filter:
                q['quality'] = quality_filter
            if is_premium_req:
                q['base_genre'] = 'Premium'
            try:
                xbmc.log(f"RusterWolf: pagination link q={q}", xbmc.LOGDEBUG)
            except Exception:
                pass
            url_prev = build_url(q)
            xbmcplugin.addDirectoryItem(HANDLE, url_prev, li_prev, True)
        if page < total_pages or len(series_keys) > end:
            try:
                xbmc.log(f"RusterWolf: TV paginación: page={page} total_pages={total_pages} mostrará Siguiente página", xbmc.LOGDEBUG)
            except Exception:
                pass
            li = xbmcgui.ListItem(label='Siguiente página')
            q = {'action': base_action, 'page': page + 1}
            if used_filter:
                q['filter'] = used_filter
            if group_by:
                q['group'] = group_by
            if genre_filter:
                q['genre'] = genre_filter
            if year_filter:
                q['year'] = year_filter
            if quality_filter:
                q['quality'] = quality_filter
            if is_premium_req:
                q['base_genre'] = 'Premium'
            try:
                xbmc.log(f"RusterWolf: pagination link q={q}", xbmc.LOGDEBUG)
            except Exception:
                pass
            url = build_url(q)
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # Si pedimos 'movie', deduplicar por título normalizado y mostrar representante
    if filter_type == 'movie':
        # Forzar vista 'movies' para listados de películas (incluyendo filtros por género/año)
        # pero NO forzar cuando se está pidiendo una agrupación (group_by)
        try:
            if not group_by:
                xbmc.log("RusterWolf DEBUG: Setting content to 'movies'", xbmc.LOGWARNING)
                try:
                    xbmcplugin.setContent(HANDLE, 'movies')
                except Exception:
                    pass
        except Exception:
            pass
        movie_map = {}
        for it in results:
            title = _get_item_title(it)
            if not title:
                continue
            key = normalize_title(title)
            movie_map.setdefault(key, []).append(it)

        xbmc.log(f"RusterWolf DEBUG: Unique movie keys found={len(movie_map)}", xbmc.LOGWARNING)
        # soporte para agrupación por género/año en películas
        if group_by == 'genre':
            return list_genres(filter_type='movie', original_params=original_params)
        if group_by == 'year':
            return list_years(filter_type='movie', original_params=original_params)
        if group_by == 'quality':
            return list_qualities(filter_type='movie', genre_filter=genre_filter, original_params=original_params)
        movie_keys = sorted(movie_map.items(), key=lambda x: x[0])
        total_pages = (len(movie_keys) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        xbmc.log(f"RusterWolf DEBUG: Pagination start={start} end={end}", xbmc.LOGWARNING)
        paged_movies = movie_keys[start:end]
        for key, group in paged_movies:
            # elegir representante con poster/overview preferido
            rep = sorted(group, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
            title = rep.get('title')
            poster = rep.get('poster') or ''
            fanart = rep.get('fanart') or ''
            overview = rep.get('overview') or ''
            rating = rep.get('rating')
            info = {
                'title': title,
                'plot': overview,
                'year': int(rep.get('year')) if rep.get('year') and str(rep.get('year')).isdigit() else None,
                'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (rep.get('genres') or [])]),
                'rating': float(rating) if rating else None,
                'mediatype': 'movie',
                'cast': rep.get('cast') or []
            }
            li = xbmcgui.ListItem(label=title)
            _apply_info_tag(li, info)
            try:
                safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
                li.setInfo('video', safe_info)
            except Exception:
                pass
            try:
                _apply_art(li, rep if 'rep' in locals() and isinstance(rep, dict) else {'poster': poster, 'fanart': fanart}, addon_fanart)
            except Exception:
                pass
            _set_unique_ids(li, rep)
            li.setProperty('IsPlayable', 'true')
            li.setMimeType('application/x-bittorrent')
            # linkear al primer item del grupo
            # Prefer using a stable 'key' when linking to the select action so
            # that the target item can be resolved regardless of list ordering.
            # Fall back to the numeric index only if no key is available.
            rep_key = group[0].get('key') if isinstance(group[0], dict) else None
            if rep_key:
                url = build_url({'action': 'select', 'key': rep_key})
            else:
                first_index = str(catalog.index(group[0]))
                url = build_url({'action': 'select', 'index': first_index})
            
            if rep_key:
                cm = []
                add_url = build_url({'action': 'add_watchlist', 'wtype': 'movie', 'val': rep_key, 'title': title})
                cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
                li.addContextMenuItems(cm)
                
            xbmcplugin.addDirectoryItem(HANDLE, url, li, False)

        # usar número de películas agrupadas para calcular páginas
        movie_keys = sorted(movie_map.items(), key=lambda x: x[0])
        total_pages = (len(movie_keys) + per_page - 1) // per_page
        if page > 1:
            li_prev = xbmcgui.ListItem(label='Página anterior')
            q = {'action': action_name or 'list', 'page': page - 1}
            if used_filter:
                q['filter'] = used_filter
            if group_by:
                q['group'] = group_by
            if genre_filter:
                q['genre'] = genre_filter
            if year_filter:
                q['year'] = year_filter
            if quality_filter:
                q['quality'] = quality_filter
            if is_premium_req:
                q['base_genre'] = 'Premium'
            url_prev = build_url(q)
            xbmcplugin.addDirectoryItem(HANDLE, url_prev, li_prev, True)
        if page < total_pages or len(movie_keys) > end:
            try:
                xbmc.log(f"RusterWolf: MOVIE paginación: page={page} total_pages={total_pages} mostrará Siguiente página", xbmc.LOGDEBUG)
            except Exception:
                pass
            li = xbmcgui.ListItem(label='Siguiente página')
            q = {'action': action_name or 'list', 'page': page + 1}
            if used_filter:
                q['filter'] = used_filter
            if group_by:
                q['group'] = group_by
            if genre_filter:
                q['genre'] = genre_filter
            if year_filter:
                q['year'] = year_filter
            if quality_filter:
                q['quality'] = quality_filter
            if is_premium_req:
                q['base_genre'] = 'Premium'
            url = build_url(q)
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        xbmc.log("RusterWolf DEBUG: endOfDirectory(movies)", xbmc.LOGWARNING)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    for it in page_items:
        title = _get_item_title(it)
        year = _get_item_year(it)
        overview = it.get('overview') or ''
        poster = it.get('poster') or ''
        fanart = it.get('fanart') or ''
        rating = it.get('rating')
        genres = _get_item_genres(it) or []
        cast = it.get('cast') or []
        # Determinar mediatype por cada elemento (antes se usaba la variable del bucle anterior)
        mediatype_item = _get_item_type(it)
        m_type = 'tvshow' if mediatype_item == 'tv' else ('movie' if mediatype_item == 'movie' else None)
        info = {
            'title': title,
            'plot': overview,
            'year': int(year) if year and str(year).isdigit() else None,
            'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in genres]),
            'rating': float(rating) if rating else None,
            'cast': cast,
            'mediatype': m_type
        }
        xbmc.log(f"RusterWolf: creando ListItem -> title={title!r}, mediatype={m_type}", xbmc.LOGDEBUG)
        li = xbmcgui.ListItem(label=title)
        _apply_info_tag(li, info)
        try:
            safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
            li.setInfo('video', safe_info)
        except Exception:
            pass
        if m_type:
            try:
                li.setProperty('mediatype', m_type)
            except Exception:
                pass
        try:
            _apply_art(li, it if isinstance(it, dict) else {'poster': poster, 'fanart': fanart}, addon_fanart)
        except Exception:
            pass
        _set_unique_ids(li, it)
        li.setProperty('IsPlayable', 'true')
        li.setMimeType('application/x-bittorrent')
        # Prefer a stable key to identify the item rather than a list index
        item_key = it.get('key') if isinstance(it, dict) else None
        if item_key:
            url = build_url({'action': 'select', 'key': item_key})
        else:
            url = build_url({'action': 'select', 'index': str(catalog.index(it))})
        
        if mediatype_item == 'movie' and item_key:
            cm = []
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'movie', 'val': item_key, 'title': title})
            cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
            li.addContextMenuItems(cm)
            
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def novedades(page=1, sub=None, original_params=None):
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    # Preferir items desde DB (date_added) cuando esté disponible
    catalog = []
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items()
    except Exception:
        catalog = []

    # Asegurar ordenación por fecha (Sustituye sort_by_newest)
    catalog = sorted(catalog, key=lambda x: x.get("date_added",""), reverse=True)

    # el router pasa 'sub' como parámetro GET (movies o series)
    # paginar novedades (page se pasa desde router)
    per_page = _read_items_per_page()
    start = (page - 1) * per_page
    end = start + per_page
    # filtrar según sub-sección (movies o series) si fue solicitado vía query
    sub_param = sub
    
    is_premium_req = False
    if original_params and original_params.get('base_genre', '').lower() == 'premium':
        is_premium_req = True
        
    def _accept_by_sub(it):
        if _is_item_premium(it) and not is_premium_req: return False
        if not _is_item_premium(it) and is_premium_req: return False
        
        if not sub_param:
            return True
        t = _get_item_type(it)
        if sub_param == 'movies' and t == 'movie':
            return True
        if sub_param == 'series' and t == 'tv':
            return True
        
        # Lógica para documentales
        genres = _get_item_genres(it) or []
        genre_names = []
        for g in genres:
            name = (g.get('name') if isinstance(g, dict) and 'name' in g else str(g)).lower()
            genre_names.append(name)
        is_doc = any('documental' in gn or 'documentary' in gn for gn in genre_names)

        if sub_param == 'documentary' and t == 'movie' and is_doc:
            return True
        if sub_param == 'series_documentary' and t == 'tv' and is_doc:
            return True
        return False

    filtered = [it for it in catalog if _accept_by_sub(it)]
    # Forzar tipo de contenido para que los skins muestren la vista adecuada
    try:
        if sub_param in ('series', 'series_documentary'):
            try:
                xbmcplugin.setContent(HANDLE, 'tvshows')
            except Exception:
                pass
        elif sub_param in ('movies', 'documentary'):
            try:
                xbmcplugin.setContent(HANDLE, 'movies')
            except Exception:
                pass
    except Exception:
        pass
    # Para novedades de series: mostrar por serie (título) en lugar de mostrar episodios con 1x01
    if sub_param in ('series', 'series_documentary'):
        # agrupamos por serie y mostramos la serie como entrada; la navegación llevará a listar temporadas
        series_map = {}
        for it in filtered:
            if _get_item_type(it) != 'tv':
                continue
            title = _get_item_title(it)
            if not title:
                continue
            key = normalize_title(title)
            series_map.setdefault(key, []).append(it)
        # Ordenar series por la fecha más reciente (`date_added`) de sus episodios
        # para que las series recién añadidas aparezcan primero.
        def _max_date(items_group):
            dates = []
            for it in items_group:
                try:
                    d = it.get('date_added') or ''
                except Exception:
                    d = ''
                if d:
                    dates.append(d)
            if not dates:
                return ''
            # ISO-like string comparison funciona para formato YYYY-MM-DDTHH:MM:SS
            return max(dates)

        series_keys = sorted(series_map.items(), key=lambda x: _max_date(x[1]), reverse=True)
        paged = series_keys[start:end]
        for key, items_group in paged:
            rep = sorted(items_group, key=lambda x: (bool(x.get('poster')), bool(x.get('overview'))), reverse=True)[0]
            display_title = rep.get('title')
            li = xbmcgui.ListItem(label=display_title)
            info = {'title': display_title, 'plot': rep.get('overview') or '', 'mediatype': 'tvshow', 'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (rep.get('genres') or [])]), 'cast': rep.get('cast') or []}
            try:
                safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
                li.setInfo('video', safe_info)
            except Exception:
                pass
            # Aplicar InfoTagVideo explícitamente para Kodi 20+
            try:
                tag = li.getVideoInfoTag()
                tag.setTitle(info['title'])
                if info['plot']: tag.setPlot(info['plot'])
                tag.setMediaType('tvshow')
            except Exception:
                pass
            # aplicar clearlogo/banner si existen
            try:
                _apply_art(li, rep, addon_fanart)
            except Exception:
                pass
            _set_unique_ids(li, rep)
            url = build_url({'action': 'list_seasons', 'series': display_title})
            
            cm = []
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'tv', 'val': display_title, 'title': display_title})
            cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
            li.addContextMenuItems(cm)
            
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        # paginación
        total_pages = (len(series_keys) + per_page - 1) // per_page
        if page > 1:
            li_prev = xbmcgui.ListItem(label='Página anterior')
            url_prev = build_url({'action': 'novedades', 'page': page - 1, 'sub': sub_param})
            xbmcplugin.addDirectoryItem(HANDLE, url_prev, li_prev, True)
        if page < total_pages:
            li = xbmcgui.ListItem(label='Siguiente página')
            url = build_url({'action': 'novedades', 'page': page + 1, 'sub': sub_param})
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # default: mostrar items (películas u otros)
    for it in filtered[start:end]:
        title = it.get('title')
        year = it.get('year')
        overview = it.get('overview') or ''
        poster = it.get('poster') or ''
        fanart = it.get('fanart') or ''
        rating = it.get('rating')
        genres = it.get('genres') or []
        cast = it.get('cast') or []
        t_type = it.get('type', '').lower()
        m_type = 'tvshow' if t_type == 'tv' else ('movie' if t_type == 'movie' else None)
        info = {
            'title': title,
            'plot': overview,
            'year': int(year) if year and str(year).isdigit() else None,
            'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in genres]),
            'rating': float(rating) if rating else None,
            'cast': cast,
            'mediatype': m_type
        }
        li = xbmcgui.ListItem(label=title)
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
            # proteger setGenre: algunos builds no exponen ese setter
            if info.get('genre'):
                try:
                    if hasattr(tag, 'setGenre'):
                        tag.setGenre(info.get('genre'))
                except Exception:
                    pass
            if info.get('rating'):
                try:
                    tag.setRating(float(info.get('rating')))
                except Exception:
                    pass
        except Exception as e:
            xbmc.log(f"RusterWolf: error aplicando InfoTagVideo en novedades: {e}", xbmc.LOGERROR)
        # Also set full info (including cast) so Kodi UI elements that read setInfo get the values
        try:
            safe_info = {k: v for k, v in info.items() if k != 'cast' and v is not None}
            li.setInfo('video', safe_info)
        except Exception:
            pass
        if m_type:
            try:
                li.setProperty('mediatype', m_type)
            except Exception:
                pass
        try:
            # Pasar el item completo para que _apply_art pueda leer clearlogo, banner, clearart, etc.
            _apply_art(li, it if isinstance(it, dict) else {'poster': poster, 'fanart': fanart}, addon_fanart)
        except Exception:
            pass
        _set_unique_ids(li, it)
        li.setProperty('IsPlayable', 'true')
        li.setMimeType('application/x-bittorrent')
        item_key = it.get('key') if isinstance(it, dict) else None
        if item_key:
            url = build_url({'action': 'select', 'key': item_key})
        else:
            url = build_url({'action': 'select', 'index': str(catalog.index(it))})
        
        if t_type == 'movie' and item_key:
            cm = []
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'movie', 'val': item_key, 'title': title})
            cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
            li.addContextMenuItems(cm)
            
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    # paginación en novedades: usar conteo sobre 'filtered' y preservar sub (movies/series) en las urls
    total_pages = (len(filtered) + per_page - 1) // per_page
    base_q = {'action': 'novedades'}
    if sub_param:
        base_q['sub'] = sub_param
    if is_premium_req:
        base_q['base_genre'] = 'Premium'
    if page > 1:
        li_prev = xbmcgui.ListItem(label='Página anterior')
        q_prev = base_q.copy()
        q_prev['page'] = page - 1
        url_prev = build_url(q_prev)
        xbmcplugin.addDirectoryItem(HANDLE, url_prev, li_prev, True)
    if page < total_pages:
        li = xbmcgui.ListItem(label='Siguiente página')
        q_next = base_q.copy()
        q_next['page'] = page + 1
        url = build_url(q_next)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_seasons(series):
    """Lista las temporadas disponibles para una serie (por título de serie)."""
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
    seasons = {}
    for it in catalog:
        if _get_item_type(it) != 'tv':
            continue
        if normalize_title(_get_item_title(it)) != normalize_title(series):
            continue
        season = str(it.get('season') or '')
        seasons.setdefault(season, []).append(it)
    # Ordenar temporadas y presentar metadatos compatibles con Kodi
    try:
        xbmcplugin.setContent(HANDLE, 'seasons')
    except Exception:
        pass
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
            li.setInfo('video', info)
            tag = li.getVideoInfoTag()
            tag.setTitle(f"Temporada {season}")
            tag.setTvShowTitle(series)
            tag.setMediaType('season')
            if info['season'] is not None:
                tag.setSeason(info['season'])
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
        url = build_url({'action':'list_episodes', 'series': series, 'season': season})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_episodes(series, season):
    addon_path = ADDON.getAddonInfo('path')
    addon_fanart = os.path.join(addon_path, 'resources', 'media', 'fanart.jpeg')
    try:
        from resources.lib.db import load_all_items
        catalog = load_all_items() or []
    except Exception:
        catalog = []
    episodes = []
    for it in catalog:
        if _get_item_type(it) != 'tv':
            continue
        if normalize_title(_get_item_title(it)) != normalize_title(series):
            continue
        if str(it.get('season') or (it.get('parsed') or {}).get('season') or '') != str(season):
            continue
        episodes.append(it)
    # Ordenar por número de episodio y establecer metadata completa para Kodi
    try:
        xbmcplugin.setContent(HANDLE, 'episodes')
    except Exception:
        pass
    for it in sorted(episodes, key=lambda x: int(x.get('episode') or 0)):
        try:
            ep_num = int(it.get('episode') or 0)
        except Exception:
            ep_num = 0

        # Preferir título específico del episodio si existe
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
        if item_key:
            url = build_url({'action': 'select', 'key': item_key})
        else:
            url = build_url({'action': 'select', 'index': str(catalog.index(it))})
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
            return
        q = kb.getText().strip()
        if not q:
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
        display_title = rep.get('title') or items_group[0].get('title')
        
        li = xbmcgui.ListItem(label=display_title)
        
        # Aplicar metadata completa
        info = {
            'title': display_title,
            'plot': rep.get('overview') or '',
            'year': int(rep.get('year')) if rep.get('year') and str(rep.get('year')).isdigit() else None,
            'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (rep.get('genres') or [])]),
            'rating': float(rep.get('rating')) if rep.get('rating') else None,
            'cast': rep.get('cast') or [],
            'mediatype': 'tvshow'
        }
        
        try:
            li.setInfo('video', info)
        except Exception:
            pass
        
        try:
            _apply_info_tag(li, info)
        except Exception:
            pass
        
        # Aplicar arte (poster, fanart, clearlogo, etc.)
        try:
            _apply_art(li, rep, addon_fanart)
        except Exception:
            pass
        _set_unique_ids(li, rep)
        
        # Enlazar a la lista de temporadas
        url = build_url({'action': 'list_seasons', 'series': display_title})
        
        cm = []
        add_url = build_url({'action': 'add_watchlist', 'wtype': 'tv', 'val': display_title, 'title': display_title})
        cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
        li.addContextMenuItems(cm)
        
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    
    # Mostrar películas
    for it in movies:
        title = _get_item_title(it)
        
        li = xbmcgui.ListItem(label=title)
        
        # Aplicar metadata completa
        info = {
            'title': title,
            'plot': it.get('overview') or '',
            'year': int(it.get('year')) if it.get('year') and str(it.get('year')).isdigit() else None,
            'genre': ', '.join([g['name'] if isinstance(g, dict) and 'name' in g else str(g) for g in (it.get('genres') or [])]),
            'rating': float(it.get('rating')) if it.get('rating') else None,
            'cast': it.get('cast') or [],
            'mediatype': 'movie'
        }
        
        try:
            li.setInfo('video', info)
        except Exception:
            pass
        
        try:
            _apply_info_tag(li, info)
        except Exception:
            pass
        
        # Aplicar arte
        try:
            _apply_art(li, it, addon_fanart)
        except Exception:
            pass
        _set_unique_ids(li, it)
        
        li.setProperty('IsPlayable', 'true')
        li.setMimeType('application/x-bittorrent')
        
        item_key = it.get('key')
        # Siempre usar KEY en búsqueda SQL (el índice no es fiable aquí)
        url = build_url({'action': 'select', 'key': item_key})
        
        if item_key:
            cm = []
            add_url = build_url({'action': 'add_watchlist', 'wtype': 'movie', 'val': item_key, 'title': title})
            cm.append(('Añadir a Seguir Viendo', f'RunPlugin({add_url})'))
            li.addContextMenuItems(cm)
            
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    
    xbmcplugin.endOfDirectory(HANDLE)

def show_select(index=None, key=None):
    # Prefer resolving by stable key when provided (avoids list ordering/index mismatches).
    it = None
    if key:
        try:
            from resources.lib.db import load_items_by_keys
            items = load_items_by_keys([key]) or []
            it = items[0] if items else None
        except Exception:
            it = None
        try:
            xbmc.log(f"RusterWolf: show_select attempted resolve by key={key} -> found={bool(it)}", xbmc.LOGWARNING)
        except Exception:
            pass
    if it is None:
        try:
            from resources.lib.db import load_all_items
            catalog = load_all_items() or []
        except Exception:
            catalog = []
        try:
            it = catalog[int(index)]
            try:
                xbmc.log(f"RusterWolf: show_select resolved by index={index} -> key={it.get('key')}", xbmc.LOGWARNING)
            except Exception:
                pass
        except Exception:
            xbmcgui.Dialog().notification('RusterWolf 77', 'Elemento no encontrado', xbmcgui.NOTIFICATION_ERROR)
            return
    title = it.get('title')
    torrents = it.get('torrents') or []
    try:
        xbmc.log(f"RusterWolf: show_select item key={it.get('key')} title={title} torrents_count={len(torrents)}", xbmc.LOGWARNING)
    except Exception:
        pass
    if not torrents:
        xbmcgui.Dialog().notification('RusterWolf 77', 'No hay torrents disponibles', xbmcgui.NOTIFICATION_INFO)
        return
        
    # Convertir DVDRip a 1080p visual y lógicamente antes de mostrar
    for t in torrents:
        if str(t.get('quality') or '').strip().lower() == 'dvdrip':
            t['quality'] = '1080p'

    # Ordenar por calidad según preferencia: 4K > 1080p > 720p > Bluray > HDTV
    def _q_rank(t):
        q = str(t.get('quality') or '').lower()
        if '4k' in q or '2160' in q: return 10
        if '1080' in q: return 9
        if '720' in q: return 8
        if 'bluray' in q: return 7
        if 'hdtv' in q: return 6
        return 0
    torrents = sorted(torrents, key=_q_rank, reverse=True)

    choices = [t.get('quality') or 'default' for t in torrents]
    sel = xbmcgui.Dialog().select('Selecciona calidad para: %s' % title, choices)
    if sel < 0:
        return
    torrent_url = torrents[sel].get('magnet')
    if not torrent_url or not torrent_url.startswith('magnet:?xt=urn:btih:'):
        xbmcgui.Dialog().notification('RusterWolf 77', 'Magnet no válido o no encontrado', xbmcgui.NOTIFICATION_ERROR)
        return
        
            
    debrid_provider = ADDON.getSetting('debrid_provider') or "0"
    debrid_cloud_fallback = ADDON.getSettingBool('debrid_cloud_fallback')
    
    play_path = ''
    
    # INYECCIÓN DE TRACKERS: SOLO PARA ELEMENTUM.
    # Si lo pasamos a Debrid, el link se vuelve demasiado largo y su API lo rechaza.
    if debrid_provider == "0":
        public_trackers = [
            "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.demonii.com:1337/announce",
            "udp://tracker.openbittorrent.com:80/announce",
            "udp://tracker.coppersurfer.tk:6969/announce",
            "udp://tracker.internetwarriors.net:1337/announce"
        ]
        for tr in public_trackers:
            if tr not in torrent_url:
                torrent_url += f"&tr={urllib.parse.quote(tr)}"

    if debrid_provider == "1":
        alldebrid_api_key = ADDON.getSetting('alldebrid_api_key')
        if not alldebrid_api_key:
            xbmcgui.Dialog().ok('AllDebrid', 'Falta la API Key en los ajustes.')
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        xbmc.log("RusterWolf: RUTA PREMIUM AllDebrid", xbmc.LOGINFO)
        from resources.lib.player import play_with_alldebrid
        play_path = play_with_alldebrid(torrent_url, alldebrid_api_key, debrid_cloud_fallback)
        
    elif debrid_provider == "2":
        realdebrid_api_key = ADDON.getSetting('realdebrid_api_key')
        if not realdebrid_api_key:
            xbmcgui.Dialog().ok('Real-Debrid', 'Falta la API Key en los ajustes.')
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        xbmc.log("RusterWolf: RUTA PREMIUM Real-Debrid", xbmc.LOGINFO)
        from resources.lib.player import play_with_realdebrid
        play_path = play_with_realdebrid(torrent_url, realdebrid_api_key, debrid_cloud_fallback)
        
    else:
        # RUTA GRATUITA: Usar Elementum
        if not is_elementum_installed():
            xbmcgui.Dialog().ok('Elementum no instalado', 'Instala Elementum desde:', 'https://elementumorg.github.io/')
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return

        play_path = 'plugin://plugin.video.elementum/play?uri=%s' % urllib.parse.quote_plus(torrent_url)

    # Si Debrid no encontró enlace en caché o falló, preguntamos si usar Elementum como alternativa
    if not play_path:
        if debrid_provider in ("1", "2"):
            if is_elementum_installed():
                resp = xbmcgui.Dialog().yesno(
                    'No en caché',
                    'Este archivo no está en la caché de tu Debrid.\n¿Desea comprobar la disponibilidad torrent de este archivo con Elementum?'
                )
                if resp:
                    # Inyectar trackers públicos para Elementum
                    public_trackers = [
                        "udp://tracker.opentrackr.org:1337/announce",
                        "udp://open.demonii.com:1337/announce",
                        "udp://tracker.openbittorrent.com:80/announce",
                        "udp://tracker.coppersurfer.tk:6969/announce",
                        "udp://tracker.internetwarriors.net:1337/announce"
                    ]
                    for tr in public_trackers:
                        if tr not in torrent_url:
                            torrent_url += f"&tr={urllib.parse.quote(tr)}"
                    play_path = 'plugin://plugin.video.elementum/play?uri=%s' % urllib.parse.quote_plus(torrent_url)
                else:
                    xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                    return
            else:
                xbmcgui.Dialog().notification('RusterWolf', 'Elementum no instalado. No se pudo hacer fallback P2P.', xbmcgui.NOTIFICATION_INFO)
                xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
                return
        else:
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        
    # Independiente de P2P o Debrid, guardar historial para el sistema Up Next
    try:
        from resources.lib.player import play_with_elementum
        history_thread = threading.Thread(
            target=play_with_elementum,
            args=(torrent_url, it),
            daemon=True
        )
        history_thread.start()
    except Exception as e:
        xbmc.log(f"RusterWolf: No se pudo iniciar el hilo de historial: {e}", xbmc.LOGERROR)

    # Reproducir usando setResolvedUrl
    li = xbmcgui.ListItem(path=play_path)
    
    # CRUCIAL: Transferir metadatos al ListItem final para que el servicio Next Up los lea
    if it:
        try:
            # InfoTag (Kodi 20+)
            tag = li.getVideoInfoTag()
            title = it.get('title')
            if title:
                tag.setTitle(it.get('episode_title') or title) # Para series, preferir titulo episodio
                tag.setTvShowTitle(title) # Importante para Next Up
            
            if it.get('season'): tag.setSeason(int(it['season']))
            if it.get('episode'): tag.setEpisode(int(it['episode']))
            
            plot = it.get('episode_overview') or it.get('overview') or it.get('plot')
            if plot: tag.setPlot(plot)
            
            media_type = it.get('type')
            if media_type == 'tv': tag.setMediaType('episode')
            elif media_type == 'movie': tag.setMediaType('movie')
            
            # Arte
            _apply_art(li, it)
        except Exception as e:
            xbmc.log(f"RusterWolf: error transfiriendo metadata al player: {e}", xbmc.LOGWARNING)
            
    xbmcplugin.setResolvedUrl(HANDLE, True, li)

def open_settings():
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % ADDON.getAddonInfo('id'))

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
    if action in ('movie_menu', 'tv_menu', 'novedades_menu', 'continue_watching', 'documentary_menu', 'series_documentary_menu', 'premium_menu', 'premium_movie_menu', 'premium_tv_menu'):
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
                   group_by=params.get('group'), genre_filter=params.get('genre'), year_filter=params.get('year'), quality_filter=params.get('quality'), original_params=params)
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
                   group_by=params.get('group'), genre_filter=params.get('genre'), year_filter=params.get('year'), quality_filter=params.get('quality'), original_params=params)
        return
    elif action == 'novedades':
        novedades(page=page, sub=params.get('sub'), original_params=params)
    elif action == 'search':
        do_search(original_params=params)
    elif action == 'select':
        # Pass both index and key so show_select can resolve by stable key when available
        show_select(index=params.get('index'), key=params.get('key'))
    elif action == 'list_seasons':
        list_seasons(params.get('series'))
    elif action == 'list_episodes':
        list_episodes(params.get('series'), params.get('season'))
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
            
    router(params)
