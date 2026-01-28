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
xbmc.log("ATRESPLAYER77: Iniciando script v0.0.58...", xbmc.LOGWARNING)
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
    "Cine": "5b5f2f777ed1a86860102144",
    "Premium": "605b306f7ed1a86f42397281"
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
        
        # Añadir manualmente secciones que el filtro LINK suele ocultar
        # Premium
        list_item = xbmcgui.ListItem(label='Premium')
        list_item.setArt({'icon': 'DefaultFolder.png', 'thumb': 'DefaultFolder.png'})
        url = get_url(action='list_section', category_id="605b306f7ed1a86f42397281", category_name="Premium")
        xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

        # Últimos 7 Días (7UD)
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': 'DefaultFolder.png', 'thumb': 'DefaultFolder.png'})
        url = get_url(action='open_item', href='/u7d/')
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
        
        # Añadir 7UD al fallback también
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': 'DefaultFolder.png', 'thumb': 'DefaultFolder.png'})
        url = get_url(action='open_item', href='/u7d/')
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
    # Usar la ruta web oficial, ya que la API directa /live/channels da 404
    open_item('/directos/')

def list_section(category_id, category_name=None, page=0):
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
        "size": 30,
        "page": page
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
                if category_name == "Cine":
                    url = get_url(action='play', href=href)
                    list_item.setProperty('IsPlayable', 'true')
                    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)
                else:
                    url = get_url(action='open_item', href=href)
                    xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
        
        # Paginación
        page_info = data.get("pageInfo", {})
        total_pages = page_info.get("totalPages", 0)
        current_page = page_info.get("pageNumber", page)
        
        if current_page < total_pages - 1:
            next_page = current_page + 1
            url = get_url(action='list_section', category_id=category_id, category_name=category_name, page=next_page)
            list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{total_pages})[/COLOR]")
            list_item.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
        
    xbmcplugin.endOfDirectory(_handle)

def open_item(href):
    """Navega dentro de una serie, temporada o programa"""
    # Forzar tamaño de página a 30 para listas (evita sobrecarga y habilita paginación)
    if "/row/search" in href:
        if "size=" in href:
            href = re.sub(r'size=\d+', 'size=30', href)
        elif "?" in href:
            href += "&size=30"
        else:
            href += "?size=30"

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
    
    # xbmc.log(f"ATRES_OPEN: Consultando {url} | params={params}", xbmc.LOGWARNING)
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # DEBUG: Descomenta esto si quieres ver la estructura al entrar en una ficha
        # xbmc.log(f"ATRES_OPEN_DUMP: {json.dumps(data)}", xbmc.LOGWARNING)
        
        # --- DETECCIÓN DE REDIRECCIÓN (Fix para Directos y cambios de ruta) ---
        # El log mostró que a veces devuelve: ['url', 'redirect', 'href', 'pageType', 'jsonld']
        if data.get("redirect") or (data.get("url") and "components" not in data and "nodes" not in data):
            # NUEVO: Manejo de respuesta inProgressFormat (solo ID de episodio)
            if "firstEpisode" in data and isinstance(data["firstEpisode"], str):
                 ep_id = data["firstEpisode"]
                 target = f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
                 xbmc.log(f"ATRES_REDIRECT: inProgressFormat ID -> {target}", xbmc.LOGWARNING)
                 return open_item(target)

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
            # xbmc.log(f"ATRES_DEBUG_COMPONENTS_LIST: {comps}", xbmc.LOGWARNING)

        # Detectar si estamos navegando dentro de una temporada específica
        is_season_view = "seasonId=" in url or "seasonId=" in href
        
        # Imagen de cabecera (Serie/Programa padre) para fallback
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = _fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = _fix_img(parent_img.get("pathHorizontal"), 'horizontal')

        nodes = []
        
        # ESTRATEGIA 0: El propio objeto es reproducible (Peliculas/Directos que vienen completos)
        if data.get("urlVideo") or data.get("sources"):
             nodes.append(data)

        # --- FASE 1: BUSCAR VIDEO PRINCIPAL (PLAY) ---
        main_video_node = None
        has_seasons = "seasons" in data and data["seasons"]
        
        # A. firstEpisode (Estructura típica de películas/eventos)
        if "firstEpisode" in data and isinstance(data["firstEpisode"], dict) and data["firstEpisode"].get("href"):
             ep = data["firstEpisode"]
             main_video_node = {
                 "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                 "type": "VIDEO",
                 "href": ep.get("href"),
                 "image": data.get("image"),
                 "description": data.get("description")
             }

        # A.2 Episode (Campo directo en Formatos de Cine detectado en logs)
        if not main_video_node and "episode" in data:
             ep_val = data["episode"]
             ep_target = None
             if isinstance(ep_val, str): ep_target = ep_val
             elif isinstance(ep_val, dict): ep_target = ep_val.get("href")

             if ep_target:
                 # xbmc.log(f"ATRES_OPEN: Detectado campo 'episode' para Cine: {ep_target}", xbmc.LOGWARNING)
                 main_video_node = {
                     "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                     "type": "VIDEO",
                     "href": ep_target,
                     "image": data.get("image"),
                     "description": data.get("description")
                 }

        # B. Hero Action (Botón en la cabecera) - Si no tenemos firstEpisode
        if not main_video_node:
            hero = data.get('hero')
            if not hero and 'components' in data:
                for c in data['components']:
                    # Ampliamos la lista de componentes posibles donde puede estar el botón
                    if c.get('component') in ['Hero', 'HERO', 'Showcase', 'Header', 'Poster', 'Banner']:
                        hero = c; break
            if hero:
                actions = hero.get("actions") or hero.get("buttons") or hero.get("links") or []
                for action in actions:
                    label = str(action.get("label", "")).lower()
                    if action.get("type") == "PLAY" or "reproducir" in label or "ver " in label or "ahora" in label:
                        main_video_node = {
                            "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                            "type": "VIDEO",
                            "href": action.get("href"),
                            "image": data.get("image"),
                            "description": data.get("description")
                        }
                        break
        
        # C. Fallback: Intentar inProgressFormat si es una ficha de formato sin video
        if not main_video_node and not has_seasons and data.get("id"):
             try:
                 fmt_id = data["id"]
                 url_prog = f"{API_BASE}/client/v1/inProgressFormat/watch/{fmt_id}"
                 # xbmc.log(f"ATRES_FALLBACK: Probando inProgressFormat {url_prog}", xbmc.LOGWARNING)
                 r_prog = s.get(url_prog, timeout=5)
                 if r_prog.ok:
                     d_prog = r_prog.json()
                     # xbmc.log(f"ATRES_FALLBACK_RESP: {str(d_prog)[:200]}", xbmc.LOGWARNING)
                     
                     ep_id = None
                     if "firstEpisode" in d_prog:
                         val = d_prog["firstEpisode"]
                         if isinstance(val, str): ep_id = val
                         elif isinstance(val, dict): ep_id = val.get("id") or val.get("href")

                     if ep_id:
                         # Si es un ID simple, construimos la URL. Si es una URL completa, la usamos.
                         target = ep_id if (str(ep_id).startswith("http") or str(ep_id).startswith("/")) else f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
                         main_video_node = {
                             "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                             "type": "VIDEO",
                             "href": target,
                             "image": data.get("image"),
                             "description": data.get("description")
                         }
             except Exception as e:
                 xbmc.log(f"ATRES_FALLBACK_ERR: {e}", xbmc.LOGERROR)

        # D. Búsqueda Recursiva (Último recurso si no hay temporadas y no hemos encontrado botón)
        if not main_video_node and not has_seasons:
             candidates = []
             _recursive_find_playable(data, candidates)
             for c in candidates:
                 h = c.get('href', '')
                 # Priorizar enlaces a player o episodios
                 if '/episode/' in h or '/player/' in h:
                     main_video_node = {
                        "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                        "type": "VIDEO",
                        "href": h,
                        "image": data.get("image"),
                        "description": data.get("description")
                     }
                     break

        # --- FASE 2: PROCESAR CONTENIDO ADICIONAL (Temporadas, Filas) ---
        content_nodes = []
        
        # A. Seasons (Series)
        # NUEVO: Si hay episodios en la raíz (vista de Temporada), usarlos directamente y evitar duplicar temporadas
        if "episodes" in data and data["episodes"]:
             content_nodes.extend(data["episodes"])
        elif "seasons" in data and not is_season_view:
            for season in data["seasons"]:
                found_eps = False
                if "episodes" in season:
                    content_nodes.extend(season["episodes"])
                    found_eps = True
                elif "items" in season:
                    content_nodes.extend(season["items"])
                    found_eps = True
                # Si no hay episodios inline, añadir la temporada como carpeta
                if not found_eps:
                    content_nodes.append(season)

        # B. Components y Rows
        other_containers = []
        if "components" in data: other_containers.extend(data["components"])
        if "rows" in data: other_containers.extend(data["rows"])
        
        # FILTRO: Palabras clave para eliminar secciones basura
        BAD_TITLES = ["clips", "extras", "secciones", "mejores momentos", "relacionado", "reparto", "detalles", "más de", "redes", "te puede interesar", "caras", "interesar", "sigue viendo", "recomendado", "suscríbete", "noticias", "blog", "capítulos", "capitulos", "temporadas", "episodios", "programas", "programas completos"]
        
        for container in other_containers:
            # 1. Filtrar por título del contenedor
            c_title = (container.get("title") or "").lower()
            
            # NUEVO: Si estamos en una temporada y hay una fila de "Capítulos" (que suele estar filtrada),
            # la cargamos explícitamente para mostrar los episodios inline.
            if is_season_view and ("capítulos" in c_title or container.get("type") == "EPISODE") and container.get("href"):
                 try:
                     r_eps = s.get(container["href"], timeout=5)
                     if r_eps.ok:
                         d_eps = r_eps.json()
                         if "items" in d_eps: content_nodes.extend(d_eps["items"])
                         elif "itemRows" in d_eps: content_nodes.extend(d_eps["itemRows"])
                         elif "rows" in d_eps:
                             for r in d_eps["rows"]:
                                 if "items" in r: content_nodes.extend(r["items"])
                 except Exception: pass
                 continue

            if any(bad in c_title for bad in BAD_TITLES): continue
            
            # 2. Filtrar por tipo de contenido en el enlace (href)
            c_href = container.get("href") or ""
            if "entityType=ATPClip" in c_href or "entityType=ATPExtra" in c_href or "entityType=ATPSection" in c_href: continue

            if "items" in container:
                content_nodes.extend(container["items"])
            elif "rows" in container:
                for row in container["rows"]:
                    # 3. Filtrar filas internas
                    r_title = (row.get("title") or "").lower()
                    if any(bad in r_title for bad in BAD_TITLES): continue
                    content_nodes.extend(row.get("items") or [])
            elif "episodes" in container:
                content_nodes.extend(container["episodes"])
            elif "nodes" in container:
                content_nodes.extend(container["nodes"])
            # Fallback para contenedores navegables (ej: enlaces a secciones)
            elif "href" in container and "title" in container and container.get("type") not in ["HERO", "Hero"]:
                 content_nodes.append(container)

        # 3. Fallback: Listas raíz
        if "nodes" in data: content_nodes.extend(data["nodes"])
        if "itemRows" in data: content_nodes.extend(data["itemRows"])
        if "episode" in data: content_nodes.append(data["episode"])

        # --- FASE 3: CONSTRUIR LISTA FINAL ---
        is_movie_mode = main_video_node and not has_seasons
        
        # 1. Filtrar contenido válido (Episodios/Temporadas) y descartar clips basura
        valid_content = []
        if is_movie_mode:
            # En modo "película/programa suelto", filtramos clips y extras agresivamente
            for n in content_nodes:
                ntype = str(n.get("type", "")).upper()
                # Si encontramos episodios sueltos (ej: Programas que no usan temporadas), son contenido válido
                if ntype in ["EPISODE", "VIDEO"] or "season" in str(n).lower():
                    valid_content.append(n)
        else:
            # Si es serie con temporadas explícitas, todo el contenido recopilado es válido
            valid_content.extend(content_nodes)

        # 2. Decidir si mostramos el botón "Reproducir" (Hero)
        # Solo lo mostramos si NO hay contenido válido (es decir, es una película sola o un directo)
        # Esto evita que en Series/Programas salga el botón "Reproducir" duplicado arriba.
        if main_video_node and not valid_content:
            nodes.append(main_video_node)

        # 3. Añadir el contenido válido (Episodios, Temporadas)
        nodes.extend(valid_content)

        # Fallback final de emergencia si no hay nada de nada
        if not nodes and not main_video_node:
             # Intento desesperado de encontrar algo reproducible
             candidates = []
             _recursive_find_playable(data, candidates)
             for c in candidates:
                 nodes.append({
                    "title": f"[COLOR green]▶ {c.get('label') or 'Reproducir'}[/COLOR]", 
                    "type": "VIDEO",
                    "href": c.get('href'),
                    "image": data.get("image")
                 })
        
        # Establecer tipo de contenido para las vistas
        if is_season_view or "itemRows" in data:
            xbmcplugin.setContent(_handle, 'episodes')
        elif "seasons" in data:
            xbmcplugin.setContent(_handle, 'seasons') # O 'tvshows' si prefieres vista de serie
        else:
            xbmcplugin.setContent(_handle, 'videos')

        if not nodes:
            # Si no hay nodos, puede ser un capítulo suelto o una película lista para ver
            # xbmc.log(f"ATRES_DEBUG_NO_NODES: Keys={list(data.keys())}", xbmc.LOGERROR)
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
            
            # HEURÍSTICA: Si el href parece un episodio o player, forzar playable (evita abrir carpeta con botón reproducir)
            looks_like_video = sub_href and ("/episode/" in sub_href or "/player/" in sub_href)
            
            # AÑADIDO: 'MOVIE', 'LIVE', 'CHANNEL' a la lista de tipos reproducibles
            if sub_href and not looks_like_video and (node_type not in ['EPISODE', 'VIDEO', 'MOVIE', 'LIVE', 'CHANNEL'] or is_row_container):
                url = get_url(action='open_item', href=sub_href)
                is_folder = True
            else:
                # Es un video final (capítulo)
                target_href = sub_href if sub_href else href
                url = get_url(action='play', href=target_href)
                is_folder = False
                list_item.setProperty('IsPlayable', 'true')

            xbmcplugin.addDirectoryItem(_handle, url, list_item, is_folder)

        # Paginación para listas dinámicas (open_item)
        if "pageInfo" in data:
            page_info = data["pageInfo"]
            total_pages = page_info.get("totalPages", 0)
            current_page = page_info.get("pageNumber", 0)
            
            if current_page < total_pages - 1:
                next_page = current_page + 1
                if "page=" in href:
                    next_href = re.sub(r'page=\d+', f'page={next_page}', href)
                elif "?" in href:
                    next_href = href + f"&page={next_page}"
                else:
                    next_href = href + f"?page={next_page}"
                
                url = get_url(action='open_item', href=next_href)
                list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{total_pages})[/COLOR]")
                list_item.setArt({'icon': 'DefaultFolder.png'})
                xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

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
    # xbmc.log(f"ATRES_PLAY: Solicitando vídeo {url}", xbmc.LOGWARNING)
    
    try:
        r = s.get(url, params=params, timeout=10)
        
        # DEBUG: Imprimir respuesta ANTES de validar status (por si da 403/404)
        try:
            pass # xbmc.log(f"ATRES_PLAY_DUMP: {json.dumps(r.json())}", xbmc.LOGWARNING)
        except Exception:
            pass # xbmc.log(f"ATRES_PLAY_RAW: {r.text[:2000]}", xbmc.LOGWARNING)

        r.raise_for_status()
        data = r.json()
        
        # Helper para búsquedas recursivas (Definido al inicio para evitar errores)
        def _find_key(d, k):
             if isinstance(d, dict):
                 if k in d and d[k]: return d[k]
                 for v in d.values():
                     res = _find_key(v, k)
                     if res: return res
             elif isinstance(d, list):
                 for i in d:
                     res = _find_key(i, k)
                     if res: return res
             return None

        # Inicializar video_url al principio
        video_url = data.get("urlVideo")

        # --- DETECCIÓN DE REDIRECCIÓN EN PLAYER ---
        # NUEVO: Priorizar href de API si existe (evita bucles con la url web)
        if data.get("href") and "api.atresplayer.com" in data["href"] and "urlVideo" not in data and "sources" not in data:
             target = data["href"]
             if target != href:
                 xbmc.log(f"ATRES_PLAY_REDIRECT: Usando API Href: {target}", xbmc.LOGWARNING)
                 return play(target)

        # NUEVO: Detectar firstEpisode como string (inProgressFormat)
        if "firstEpisode" in data and isinstance(data["firstEpisode"], str):
             ep_id = data["firstEpisode"]
             target = f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
             xbmc.log(f"ATRES_PLAY_REDIRECT: Usando inProgressFormat ID: {target}", xbmc.LOGWARNING)
             return play(target)

        # NUEVO: Fallback inProgressFormat dentro de PLAY (por si open_item falló o usamos botón forzado)
        if not video_url and not data.get("sources") and data.get("id"):
             try:
                 fmt_id = data["id"]
                 url_prog = f"{API_BASE}/client/v1/inProgressFormat/watch/{fmt_id}"
                 xbmc.log(f"ATRES_PLAY_FALLBACK: Probando inProgressFormat {url_prog}", xbmc.LOGWARNING)
                 r_prog = s.get(url_prog, timeout=5)
                 if r_prog.ok:
                     d_prog = r_prog.json()
                     ep_id = None
                     if "firstEpisode" in d_prog:
                         val = d_prog["firstEpisode"]
                         if isinstance(val, str): ep_id = val
                         elif isinstance(val, dict): ep_id = val.get("id")
                     if ep_id:
                         target = f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
                         return play(target)
             except Exception: pass

        # NUEVO: Detectar firstEpisode en Player (por si llegamos aquí directamente)
        if "firstEpisode" in data and isinstance(data["firstEpisode"], dict) and data["firstEpisode"].get("href"):
             target = data["firstEpisode"]["href"]
             if target != href:
                 xbmc.log(f"ATRES_PLAY_REDIRECT: Usando firstEpisode: {target}", xbmc.LOGWARNING)
                 return play(target)

        # NUEVO: Detectar campo 'episode' (Cine)
        if "episode" in data:
             ep_val = data["episode"]
             target = ep_val if isinstance(ep_val, str) else ep_val.get("href") if isinstance(ep_val, dict) else None
             if target:
                 xbmc.log(f"ATRES_PLAY_REDIRECT: Usando campo episode: {target}", xbmc.LOGWARNING)
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

        # NUEVO: Buscar urlVideo recursivamente si no está en la raíz (para estructuras anidadas)
        if not video_url:
             video_url = _find_key(data, "urlVideo")
             if video_url:
                 xbmc.log(f"ATRES_PLAY: urlVideo encontrado recursivamente: {video_url}", xbmc.LOGWARNING)

        # NUEVO: Buscar sources recursivamente si no están en la raíz
        if not video_url and not data.get("sources"):
             sources_found = _find_key(data, "sources")
             if sources_found:
                 xbmc.log(f"ATRES_PLAY: sources encontrado recursivamente", xbmc.LOGWARNING)
                 data["sources"] = sources_found
        
        # NUEVO: Si no hay video, buscar botones de acción (Hero) igual que en los menús
        # Esto soluciona CINE cuando la URL del episodio es una ficha de presentación
        if not video_url and not data.get("sources"):
            hero = data.get('hero')
            if not hero and 'components' in data:
                for c in data['components']:
                    if c.get('component') in ['Hero', 'HERO', 'Showcase', 'Header', 'Poster', 'Banner']:
                        hero = c; break
            if hero:
                actions = hero.get("actions") or hero.get("buttons") or hero.get("links") or []
                for action in actions:
                    if action.get("type") == "PLAY" or "reproducir" in str(action.get("label", "")).lower():
                        target = action.get("href")
                        if target and target != href:
                             xbmc.log(f"ATRES_PLAY: Botón Hero encontrado, redirigiendo: {target}", xbmc.LOGWARNING)
                             return play(target)

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

        # LÓGICA DE SELECCIÓN DE FUENTE (Soporte Live y VOD)
        def _get_best_source(sources):
            if not sources: return None
            # 1. DASH
            for src in sources:
                if src.get("type") == "application/dash+xml" and src.get("src"):
                    return src.get("src")
            # 2. HLS
            for src in sources:
                if "mpegurl" in str(src.get("type")) and src.get("src"):
                    return src.get("src")
            # 3. Cualquiera con src
            for src in sources:
                if src.get("src"): return src.get("src")
            return None

        if not video_url:
            # Intentar fuentes de directo (sourcesLive)
            video_url = _get_best_source(data.get("sourcesLive"))
        
        if not video_url:
            # Intentar fuentes estándar (sources)
            video_url = _get_best_source(data.get("sources"))

        if not video_url:
             # DEBUG CRÍTICO: Imprimir estructura completa si falla para comparar con la web
             # xbmc.log(f"ATRES_PLAY_FAIL_DUMP: {json.dumps(data)}", xbmc.LOGERROR)
             xbmc.log(f"ATRES_PLAY_FAIL: No sources found", xbmc.LOGERROR)
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
        list_section(params.get('category_id'), params.get('category_name'), int(params.get('page', 0)))
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