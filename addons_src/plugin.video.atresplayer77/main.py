import sys
import os
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import xbmc
import base64
import re
import requests
import json
import http.cookiejar
import urllib.parse
from urllib.parse import parse_qsl, urlencode

# Configuración inicial
xbmc.log("ATRESPLAYER77: Iniciando script v0.0.41...", xbmc.LOGWARNING)
_url = sys.argv[0]
_handle = int(sys.argv[1])
addon = xbmcaddon.Addon()

# --- CONSTANTES API ---
API_BASE = "https://api.atresplayer.com"
MAIN_CHANNEL_ID = "5a6b32667ed1a834493ec03b"

# IDs de categorías oficiales
CATEGORIES = {
    "Series": "5a6a1b22986b281d18a512b8",
    "Programas": "5a6a1ba0986b281d18a512b9",
    "Documentales": "5b067bf3986b28b0a27c2f42",
    "Infantil": "5a6a24b1986b281d18a512c0",
    "Actualidad": "5a6a215e986b281d18a512bc",
    "Cine": "5b5f2f777ed1a86860102144"
}

# Gestión de Cookies y Sesión
PROFILE_DIR = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
COOKIE_FILE = os.path.join(PROFILE_DIR, 'cookies.jar')

def get_session():
    """Crea una sesión persistente con cookies"""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': '*/*',
        'Accept-Language': 'es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Origin': 'https://www.atresplayer.com',
        'Referer': 'https://www.atresplayer.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Connection': 'keep-alive'
    })
    if os.path.exists(COOKIE_FILE):
        try:
            cj = http.cookiejar.LWPCookieJar(COOKIE_FILE)
            cj.load(ignore_discard=True, ignore_expires=True)
            s.cookies = cj
        except Exception: pass
    return s

def save_cookies(s):
    """Guarda las cookies en disco"""
    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)
    cj = http.cookiejar.LWPCookieJar(COOKIE_FILE)
    for c in s.cookies: cj.set_cookie(c)
    cj.save(ignore_discard=True, ignore_expires=True)

def get_url(**kwargs):
    """Ayuda para crear URLs internas del addon"""
    return '{0}?{1}'.format(_url, urlencode(kwargs))

def _fix_img(url, type='vertical'):
    """Arregla las URLs de imágenes de Atresplayer"""
    if not url: return ""
    # A veces vienen sin esquema
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.atresplayer.com" + url
    # CORRECCIÓN: Si la URL es un directorio, añadir un tamaño de imagen estándar.
    if url.endswith('/'):
        if type == 'horizontal':
            return url + '1280x720.jpg' # Fanart HD
        else:
            return url + '390x219.jpg' # Poster vertical
    return url

def list_categories():
    """Menú Principal"""
    # 1. Intentar cargar menú dinámico de la Web
    s = get_session()
    dynamic_items = []
    try:
        r = s.get(f"{API_BASE}/client/v1/menus/web", timeout=5)
        if r.ok:
            menu = r.json()
            xbmc.log(f"ATRES_MENU_DEBUG: Encontrados {len(menu.get('items', []))} items en menú web", xbmc.LOGWARNING)
            for item in menu.get("items", []):
                if item.get("type") == "LINK" and item.get("href"):
                    dynamic_items.append(item)
    except Exception:
        pass

    if dynamic_items:
        for item in dynamic_items:
            label = item.get("title", "Sin título")
            href = item.get("href")
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media', icon_name)
            if not os.path.exists(icon_path): icon_path = 'DefaultFolder.png'
            
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            
            if "directos" in href or "guia-tv" in href:
                url = get_url(action='list_live')
            else:
                url = get_url(action='open_item', href=href)
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
    else:
        # Fallback a categorías hardcoded
        for label, cat_id in CATEGORIES.items():
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media', icon_name)
            if not os.path.exists(icon_path): icon_path = 'DefaultFolder.png'
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            url = get_url(action='list_section', category_id=cat_id, category_name=label)
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    # Siempre añadir acceso directo a Live por si acaso
    list_item = xbmcgui.ListItem(label='[COLOR red]En Directo (TV)[/COLOR]')
    list_item.setArt({'icon': 'DefaultAddonPVRClient.png'})
    url = get_url(action='list_live')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    # 2. Login / Cuenta
    list_item = xbmcgui.ListItem(label='[COLOR blue]Iniciar Sesión / Cuenta[/COLOR]')
    list_item.setArt({'icon': 'DefaultUser.png'})
    url = get_url(action='login')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    # 3. Configuración
    list_item = xbmcgui.ListItem(label='[COLOR yellow]Configuración[/COLOR]')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = get_url(action='settings')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    xbmcplugin.endOfDirectory(_handle)

def open_settings():
    addon.openSettings()

# --- PUENTE DE BÚSQUEDA PALANTIR 3 ---
def _p3_b64encode(value):
    if not isinstance(value, bytes):
        value = str(value).encode()
    value = base64.b64encode(value)
    length = len(value)
    part = int(length / 4)
    value = re.sub(b'=', b'', value)
    encoded = value[:part][::-1] + value[part:][::-1]
    return urllib.parse.quote(encoded.decode())

def search_palantir_bridge(query):
    if not query: return
    item_dict = {"action": "buscar3", "sql": f"rebuscar {query}", "label": query}
    encoded_item = _p3_b64encode(str(item_dict))
    plugin_url = f"plugin://plugin.video.palantir3/?{encoded_item}"
    xbmc.executebuiltin(f"Container.Update({plugin_url})")
    # Finalizar directorio para evitar error en Kodi si el redirect tarda o falla
    xbmcplugin.endOfDirectory(_handle)

# --- LÓGICA ATRESPLAYER ---
def _recursive_find_playable(data, results):
    """Busca recursivamente cualquier objeto que parezca un enlace de reproducción"""
    if isinstance(data, dict):
        href = data.get("href")
        type_ = data.get("type")
        label = str(data.get("label", "")).lower()
        
        # Criterios: Botón PLAY, enlace a /t/ (target), enlace a /player/
        is_play_btn = type_ == "PLAY" or "reproducir" in label or "ver ahora" in label or "ver la película" in label or label == "ver"
        is_video_link = href and ("/t/" in href or "/player/" in href or "/page/episode/" in href or "/episode/" in href)
        
        if href and (is_play_btn or is_video_link):
             # Evitar duplicados
             if not any(r.get("href") == href for r in results):
                results.append(data)
        
        for v in data.values():
            _recursive_find_playable(v, results)
    elif isinstance(data, list):
        for item in data:
            _recursive_find_playable(item, results)

def list_live():
    """Lista los canales en directo"""
    xbmcplugin.setContent(_handle, 'videos')
    # Volvemos a la API específica de canales que es más fiable que el wrapper web
    url = f"{API_BASE}/client/v1/live/channels"
    params = {"mainChannelId": MAIN_CHANNEL_ID}
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # La API devuelve una lista de canales directamente o dentro de items
        items = data if isinstance(data, list) else data.get("items", [])
        
        for item in items:
            title = item.get("name") or item.get("channel") or item.get("title") or "Canal"
            
            img_data = item.get("image") or item.get("images") or {}
            thumb = _fix_img(img_data.get("pathHorizontal") or img_data.get("pathVertical"), 'horizontal')
            
            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'icon': thumb, 'thumb': thumb, 'fanart': thumb})
            list_item.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
            # El href para reproducir
            href = item.get("href")
            # A veces el href no viene, construimos uno con el ID del canal
            if not href and item.get("id"):
                 href = f"/directos/{item.get('id')}"
            
            if href:
                url = get_url(action='play', href=href)
                list_item.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(_handle, url, list_item, False)
                
    except Exception as e:
        xbmc.log(f"ATRES_LIVE_ERROR: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error Live", str(e))
        
    xbmcplugin.endOfDirectory(_handle)

def list_section(category_id, category_name=None):
    """Conecta a la API y lista el contenido de una categoría"""
    
    # Establecer el tipo de contenido para que la skin active las vistas (Poster, Fanart, etc.)
    if category_name == "Series":
        xbmcplugin.setContent(_handle, 'tvshows')
    elif category_name == "Cine":
        xbmcplugin.setContent(_handle, 'movies')
    else:
        xbmcplugin.setContent(_handle, 'videos')

    url = f"{API_BASE}/client/v1/row/search"
    params = {
        "entityType": "ATPFormat",
        "sectionCategory": "true",
        "mainChannelId": MAIN_CHANNEL_ID,
        "categoryId": category_id,
        "sortType": "THE_MOST",
        "size": 50,
        "page": 0
    }
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        items = data.get("itemRows", [])
        
        for item in items:
            title = item.get("title", "Sin título")
            # Intentamos varios sitios donde suelen poner las imagenes
            img_data = item.get("image") or item.get("images") or {}
            poster = _fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = _fix_img(img_data.get("pathHorizontal"), 'horizontal')
            # Fallbacks
            if not poster: poster = fanart
            if not fanart: fanart = poster
            
            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart})
            list_item.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
            # CORRECCIÓN: El href suele venir dentro de un objeto 'link'
            link_data = item.get("link") or {}
            href = item.get("href") or link_data.get("href")
            if href:
                url = get_url(action='open_item', href=href)
                xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
        
    xbmcplugin.endOfDirectory(_handle)

def open_item(href):
    """Navega dentro de una serie, temporada o programa"""
    # CAMBIO IMPORTANTE: Usar /client/v1/url para resolver rutas, igual que la web
    params = {}
    if href.startswith("http"):
        url = href
    elif href.startswith("/"):
        url = f"{API_BASE}/client/v1/url"
        params = {"href": href}
    else:
        # Fallback para IDs antiguos si los hubiera
        url = f"{API_BASE}/client/v1/items{href}"
    
    xbmc.log(f"ATRES_OPEN: Consultando {url} | params={params}", xbmc.LOGWARNING)
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # --- DETECCIÓN DE REDIRECCIÓN (Fix para Directos y cambios de ruta) ---
        # El log mostró que a veces devuelve: ['url', 'redirect', 'href', 'pageType', 'jsonld']
        if data.get("redirect") or (data.get("url") and "components" not in data and "nodes" not in data):
            # NUEVO: Priorizar href de API si existe (evita bucles con la url web)
            if data.get("href") and "api.atresplayer.com" in data["href"]:
                target = data["href"]
                if target != href:
                    xbmc.log(f"ATRES_REDIRECT: Usando API Href: {target}", xbmc.LOGWARNING)
                    return open_item(target)

            target = data.get("url") or data.get("href")
            if target:
                # Si nos dan una URL completa de atresplayer, la convertimos a relativa para usar la API
                if "atresplayer.com" in target:
                    parsed = urllib.parse.urlparse(target)
                    target = parsed.path
                    if parsed.query: target += "?" + parsed.query
                
                if target != href and target != href + "/":
                    xbmc.log(f"ATRES_REDIRECT: API indica redirección a {target}", xbmc.LOGWARNING)
                    return open_item(target)

        # --- DEBUG DIAGNÓSTICO ---
        # Esto imprimirá en el log la estructura exacta que recibimos
        # xbmc.log(f"ATRES_DEBUG_ROOT_KEYS: {list(data.keys())}", xbmc.LOGWARNING)
        if "components" in data:
            comps = [c.get("component") or c.get("type") for c in data["components"]]
            xbmc.log(f"ATRES_DEBUG_COMPONENTS_LIST: {comps}", xbmc.LOGWARNING)

        # Detectar si estamos navegando dentro de una temporada específica
        is_season_view = "seasonId=" in url
        
        # Imagen de cabecera (Serie/Programa padre) para fallback
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = _fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = _fix_img(parent_img.get("pathHorizontal"), 'horizontal')

        nodes = []
        
        # ESTRATEGIA 0: El propio objeto es reproducible (Peliculas/Directos que vienen completos)
        if data.get("urlVideo") or data.get("sources"):
             nodes.append(data)

        # NUEVO: Detectar firstEpisode (Estructura de Películas confirmada por log)
        if "firstEpisode" in data and data["firstEpisode"].get("href"):
             ep = data["firstEpisode"]
             video_node = {
                 "title": data.get("title", "Reproducir Película"),
                 "type": "VIDEO",
                 "href": ep.get("href"),
                 "image": data.get("image"),
                 "description": data.get("description")
             }
             nodes.append(video_node)

        # ESTRATEGIA 1: Búsqueda Recursiva de Botones de Reproducción (La "Red de Seguridad")
        # En lugar de buscar solo en 'hero', buscamos en TODO el JSON cualquier cosa que parezca un botón de Play
        play_candidates = []
        _recursive_find_playable(data, play_candidates)
        
        for action in play_candidates:
            label = action.get("label") or action.get("title") or "Reproducir"
            href_act = action.get("href")
            xbmc.log(f"ATRES_ACTION: Encontrado candidato '{label}' -> {href_act}", xbmc.LOGWARNING)
            
            video_node = {
                "title": f"[COLOR green]▶ {label}[/COLOR]", 
                "type": "VIDEO",
                "href": href_act,
                "image": data.get("image"),
                "description": data.get("description", "")
            }
            nodes.append(video_node)

        # 2. Bloques de CONTENIDO
        
        # A. Seasons (Series) - Prioridad
        if "seasons" in data:
            for season in data["seasons"]:
                found_eps = False
                if "episodes" in season:
                    nodes.extend(season["episodes"])
                    found_eps = True
                elif "items" in season:
                    nodes.extend(season["items"])
                    found_eps = True
                
                # Si no hay episodios inline, añadir la temporada como carpeta
                if not found_eps:
                    nodes.append(season)

        # B. Components y Rows
        other_containers = []
        if "components" in data: other_containers.extend(data["components"])
        if "rows" in data: other_containers.extend(data["rows"])
        
        for container in other_containers:
            if "items" in container:
                nodes.extend(container["items"])
            elif "rows" in container:
                for row in container["rows"]:
                    nodes.extend(row.get("items") or [])
            elif "episodes" in container:
                nodes.extend(container["episodes"])
            elif "nodes" in container:
                nodes.extend(container["nodes"])
            # Fallback para contenedores navegables (ej: enlaces a secciones)
            elif "href" in container and "title" in container and container.get("type") not in ["HERO", "Hero"]:
                 nodes.append(container)

        # 3. Fallback: Si no hay componentes, mirar listas raíz
        if not nodes:
             if "nodes" in data: nodes.extend(data["nodes"])
             if "itemRows" in data: nodes.extend(data["itemRows"])
             if "episode" in data: nodes.append(data["episode"])
        
        # Establecer tipo de contenido para las vistas
        if is_season_view or "itemRows" in data:
            xbmcplugin.setContent(_handle, 'episodes')
        elif "seasons" in data:
            xbmcplugin.setContent(_handle, 'seasons') # O 'tvshows' si prefieres vista de serie
        else:
            xbmcplugin.setContent(_handle, 'videos')

        if not nodes:
            # Si no hay nodos, puede ser un capítulo suelto o una película lista para ver
            xbmc.log(f"ATRES_DEBUG_NO_NODES: Keys={list(data.keys())}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("Atresplayer", "No se encontraron enlaces reproducibles")
            xbmcplugin.endOfDirectory(_handle) # Importante cerrar directorio para evitar error en log
            return

        for node in nodes:
            title = node.get("title") or node.get("name") or "Sin título"
            
            # Imagen
            img_data = node.get("image") or node.get("images") or {}
            poster = _fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = _fix_img(img_data.get("pathHorizontal"), 'horizontal')
            # Fallbacks con imagen padre
            if not poster: poster = parent_poster
            if not fanart: fanart = parent_fanart
            if not poster: poster = fanart
            if not fanart: fanart = poster

            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart})
            list_item.setInfo('video', {'title': title, 'plot': node.get('description', '')})
            
            # Recursividad: Si tiene href, podemos entrar. Si no, es video final.
            sub_link = node.get("link") or {}
            sub_href = node.get("href") or sub_link.get("href")
            
            # Detectar si es un episodio para reproducir directamente
            node_type = node.get("type")
            
            # CORRECCIÓN: Si el enlace contiene '/row/' o 'search', es una lista (carpeta), no un vídeo
            is_row_container = sub_href and ("/row/" in sub_href or "search" in sub_href)
            
            # AÑADIDO: 'MOVIE', 'LIVE', 'CHANNEL' a la lista de tipos reproducibles
            if sub_href and (node_type not in ['EPISODE', 'VIDEO', 'MOVIE', 'LIVE', 'CHANNEL'] or is_row_container):
                url = get_url(action='open_item', href=sub_href)
                is_folder = True
            else:
                # Es un video final (capítulo)
                target_href = sub_href if sub_href else href
                url = get_url(action='play', href=target_href)
                is_folder = False
                list_item.setProperty('IsPlayable', 'true')

            xbmcplugin.addDirectoryItem(_handle, url, list_item, is_folder)

    except Exception as e:
        xbmcgui.Dialog().notification("Error Navegación", str(e))
    
    xbmcplugin.endOfDirectory(_handle)

def do_login():
    """Placeholder para el login"""
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok("Atresplayer", "Por favor, introduce tu usuario y contraseña en los ajustes del addon.")
        open_settings()
        return
    
    # Usar una sesión limpia para el login (evitar cookies viejas corruptas)
    s = requests.Session()
    # Usar las mismas cabeceras que get_session para consistencia
    s.headers.update(get_session().headers)

    # Paso 1: Obtener cookies iniciales (CSRF, etc.) visitando la web de login
    try:
        xbmc.log("ATRES_LOGIN: Visitando home para obtener cookies...", xbmc.LOGWARNING)
        s.get("https://www.atresplayer.com/", timeout=10)
    except Exception as e:
        xbmc.log(f"ATRES_LOGIN_WARN: Fallo en GET inicial: {e}", xbmc.LOGWARNING)

    # Paso 2: Realizar el POST de login
    url = "https://account.atresplayer.com/auth/v1/login"
    payload = {"username": username, "password": password}
    
    try:
        # DEBUG: Imprimir el comando cURL equivalente para comparar con el navegador
        req_headers = dict(s.headers)
        req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        curl_cmd = f"curl -X POST '{url}'"
        for k, v in req_headers.items():
            curl_cmd += f" -H '{k}: {v}'"
        curl_cmd += f" --data '{urlencode(payload)}'"
        xbmc.log(f"ATRES_CURL_DEBUG: {curl_cmd}", xbmc.LOGWARNING)

        # Enviar como FORMULARIO (data=payload) según cURL
        r = s.post(url, data=payload, timeout=15)
        
        if r.status_code == 200:
            save_cookies(s)
            xbmcgui.Dialog().notification("Atresplayer", "Login Correcto")
            xbmc.log(f"ATRES_LOGIN_SUCCESS: Conectado usando {url}", xbmc.LOGWARNING)
        elif r.status_code in (401, 403):
            xbmcgui.Dialog().notification("Error Login", "Usuario o contraseña incorrectos")
        else:
            xbmc.log(f"ATRES_LOGIN_FAIL: {r.status_code} en {url} -> {r.text[:200]}", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("Error Login", f"Error {r.status_code}")
    except Exception as e:
        xbmc.log(f"ATRES_LOGIN_EXC: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error Login", str(e))

def play(href):
    """Resuelve la URL del vídeo y lo reproduce"""
    params = {}
    if href.startswith("http"): 
        url = href
    elif href.startswith("/"):
        url = f"{API_BASE}/client/v1/url"
        params = {"href": href}
    else: 
        url = f"{API_BASE}/client/v1/items{href}"
    
    s = get_session()
    xbmc.log(f"ATRES_PLAY: Solicitando vídeo {url}", xbmc.LOGWARNING)
    
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # --- DETECCIÓN DE REDIRECCIÓN EN PLAYER ---
        # NUEVO: Priorizar href de API si existe (evita bucles con la url web)
        if data.get("href") and "api.atresplayer.com" in data["href"] and "urlVideo" not in data and "sources" not in data:
             target = data["href"]
             if target != href:
                 xbmc.log(f"ATRES_PLAY_REDIRECT: Usando API Href: {target}", xbmc.LOGWARNING)
                 return play(target)

        # NUEVO: Detectar firstEpisode en Player (por si llegamos aquí directamente)
        if "firstEpisode" in data and data["firstEpisode"].get("href"):
             target = data["firstEpisode"]["href"]
             if target != href:
                 xbmc.log(f"ATRES_PLAY_REDIRECT: Usando firstEpisode: {target}", xbmc.LOGWARNING)
                 return play(target)

        if data.get("redirect") or (data.get("url") and "urlVideo" not in data and "sources" not in data):
             target = data.get("url") or data.get("href")
             if target:
                 if "atresplayer.com" in target:
                    parsed = urllib.parse.urlparse(target)
                    target = parsed.path
                 if target != href:
                     xbmc.log(f"ATRES_PLAY_REDIRECT: Redirigiendo a {target}", xbmc.LOGWARNING)
                     return play(target)

        # 1. Obtener URL del Player o Sources directos
        video_url = data.get("urlVideo")
        
        # Si no hay video_url ni sources, es posible que estemos en una ficha (Format)
        # Intentamos buscar el enlace de reproducción dentro de la estructura
        if not video_url and not data.get("sources"):
            xbmc.log("ATRES_PLAY: No se encontró urlVideo/sources, buscando candidatos...", xbmc.LOGWARNING)
            candidates = []
            _recursive_find_playable(data, candidates)
            if candidates:
                # Priorizar enlaces que contengan /player/
                best = next((c for c in candidates if "/player/" in c.get("href", "")), candidates[0])
                new_href = best.get("href")
                if new_href and new_href != href:
                    xbmc.log(f"ATRES_PLAY: Redirigiendo a {new_href}", xbmc.LOGWARNING)
                    return play(new_href)

        # Si es una URL de API de player (ej: https://api.atresplayer.com/player/v1/...), hay que consultarla
        if video_url and "/player/" in video_url:
            xbmc.log(f"ATRES_PLAY: Resolviendo endpoint de player: {video_url}", xbmc.LOGWARNING)
            r_player = s.get(video_url, timeout=10)
            r_player.raise_for_status()
            data = r_player.json() # Sobrescribimos data con la respuesta del player (que trae 'sources')
            video_url = None # Reseteamos para buscar en sources

        if not video_url and "sources" in data:
            # Preferimos DASH (.mpd)
            for src in data["sources"]:
                if src.get("type") == "application/dash+xml":
                    video_url = src.get("src")
                    break
            # Si no hay DASH, cogemos el primero que haya
            if not video_url and data["sources"]:
                video_url = data["sources"][0].get("src")
        
        if not video_url:
             xbmc.log(f"ATRES_PLAY_FAIL: No sources found in {data}", xbmc.LOGERROR)
             xbmcgui.Dialog().notification("Atresplayer", "No se encontró URL de video")
             return

        # Crear el item de reproducción
        li = xbmcgui.ListItem(path=video_url)
        # Configurar InputStream Adaptive (necesario para DASH/HLS)
        if ".mpd" in video_url or ".m3u8" in video_url:
            li.setProperty('inputstream', 'inputstream.adaptive')
            li.setProperty('inputstream.adaptive.manifest_type', 'mpd' if '.mpd' in video_url else 'hls')
            li.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
            
            # MEJORA: Forzar inicio con ancho de banda alto (evita 720p inicial)
            li.setProperty('inputstream.adaptive.min_bandwidth', '10000000') # 10 Mbps

            # IMPORTANTE: Pasar las cookies y headers a InputStream Adaptive
            headers_dict = {
                'User-Agent': s.headers.get('User-Agent', ''),
                'Origin': s.headers.get('Origin', 'https://www.atresplayer.com'),
                'Referer': s.headers.get('Referer', 'https://www.atresplayer.com/')
            }
            # Añadir cookies si existen
            cookie_str = "; ".join([f"{c.name}={c.value}" for c in s.cookies])
            if cookie_str:
                headers_dict['Cookie'] = cookie_str
            headers = "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in headers_dict.items()])
            
            li.setProperty('inputstream.adaptive.stream_headers', headers)
            li.setProperty('inputstream.adaptive.manifest_headers', headers)
            li.setProperty('inputstream.adaptive.license_headers', headers)

        xbmcplugin.setResolvedUrl(_handle, True, li)

    except Exception as e:
        xbmcgui.Dialog().notification("Error Reproducción", str(e))
        xbmc.log(f"ATRES_PLAY_ERR: {e}", xbmc.LOGERROR)

def router(paramstring):
    params = dict(parse_qsl(paramstring))
    
    if not params:
        list_categories()
        return

    action = params.get('action')

    if action == 'settings':
        open_settings()
    elif action == 'list_section':
        list_section(params.get('category_id'), params.get('category_name'))
    elif action == 'open_item':
        open_item(params.get('href'))
    elif action == 'login':
        do_login()
    elif action == 'list_live':
        list_live()
    elif action == 'play':
        play(params.get('href'))
    elif action == 'bridge_palantir':
        search_palantir_bridge(params.get('q'))

if __name__ == '__main__':
    router(sys.argv[2][1:])