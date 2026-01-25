import sys
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmc
import base64
import re
import requests
import json
from urllib.parse import parse_qsl, urlencode

# Configuración inicial
xbmc.log("ATRESPLAYER77: Iniciando script v0.0.11...", xbmc.LOGWARNING)
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
    # 1. Listar Categorías de la API
    for label, cat_id in CATEGORIES.items():
        list_item = xbmcgui.ListItem(label=label)
        list_item.setArt({'icon': 'DefaultFolder.png'})
        url = get_url(action='list_section', category_id=cat_id)
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

# --- LÓGICA ATRESPLAYER ---
def list_section(category_id):
    """Conecta a la API y lista el contenido de una categoría"""
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
    
    try:
        r = requests.get(url, params=params, timeout=10)
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
    # La API para detalles es /client/v1/items + el href del item
    # CORRECCIÓN: Si el href ya es una URL completa (empieza por http), la usamos tal cual
    if href.startswith("http"):
        url = href
    else:
        url = f"{API_BASE}/client/v1/items{href}"
    
    xbmc.log(f"ATRES_OPEN: Consultando {url}", xbmc.LOGWARNING)
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Imagen de cabecera (Serie/Programa padre) para fallback
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = _fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = _fix_img(parent_img.get("pathHorizontal"), 'horizontal')

        nodes = []
        
        # ESTRATEGIA 1: Nodos directos (Programas simples)
        if "nodes" in data:
            nodes = data["nodes"]
            
        # ESTRATEGIA 2: Secciones (Series antiguas)
        if not nodes and "sections" in data:
            for sec in data["sections"]:
                nodes.extend(sec.get("items") or sec.get("nodes") or [])
                
        # ESTRATEGIA 3: Componentes (Series nuevas / Formato página)
        if not nodes and "components" in data:
            for comp in data["components"]:
                if "items" in comp:
                    nodes.extend(comp["items"])
                elif "rows" in comp:
                    nodes.extend(comp["rows"])

        # ESTRATEGIA 4: Temporadas (Detectado en logs recientes)
        if not nodes and "seasons" in data:
            seasons = data["seasons"]
            if seasons:
                xbmc.log(f"ATRES_DEBUG_SEASON_0: {list(seasons[0].keys())}", xbmc.LOGWARNING)
                # Intento 1: Extraer episodios de dentro
                for season in seasons:
                    nodes.extend(season.get("items") or season.get("nodes") or season.get("episodes") or [])
                # Intento 2: Si no hay episodios, las temporadas son las carpetas
                if not nodes:
                    nodes = seasons

        # ESTRATEGIA 5: Filas (Detectado en logs recientes)
        if not nodes and "rows" in data:
            rows = data["rows"]
            if rows:
                xbmc.log(f"ATRES_DEBUG_ROWS_0: {list(rows[0].keys())}", xbmc.LOGWARNING)
                # Intento 1: Extraer items de dentro
                for row in rows:
                    nodes.extend(row.get("items") or row.get("nodes") or [])
                # Intento 2: Si no hay items, las filas son las carpetas
                if not nodes:
                    nodes = rows

        # ESTRATEGIA 6: Episodio suelto (Detectado en logs recientes)
        if not nodes and "episode" in data:
            nodes.append(data["episode"])
        
        if not nodes:
            # Si no hay nodos, puede ser un capítulo suelto o una película lista para ver
            xbmcgui.Dialog().ok("Atresplayer", f"Contenido final: {data.get('title')}\n(El siguiente paso es implementar la reproducción)")
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
            if sub_href:
                url = get_url(action='open_item', href=sub_href)
                is_folder = True
            else:
                # Es un video final (capítulo)
                url = get_url(action='play', href=href) # Placeholder
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
    xbmcgui.Dialog().ok("Atresplayer", f"Preparado para conectar como: {username}\n(Lógica de login en construcción)")

def router(paramstring):
    params = dict(parse_qsl(paramstring))
    
    if not params:
        list_categories()
        return

    action = params.get('action')

    if action == 'settings':
        open_settings()
    elif action == 'list_section':
        list_section(params.get('category_id'))
    elif action == 'open_item':
        open_item(params.get('href'))
    elif action == 'login':
        do_login()
    elif action == 'play':
        xbmcgui.Dialog().ok("Atresplayer", f"Reproducción en construcción para: {params.get('href')}")
    elif action == 'bridge_palantir':
        search_palantir_bridge(params.get('q'))

if __name__ == '__main__':
    router(sys.argv[2][1:])