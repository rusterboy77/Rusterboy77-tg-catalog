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
_url = sys.argv[0]
_handle = int(sys.argv[1])
addon = xbmcaddon.Addon()

# --- CONSTANTES API (Extraídas de ingeniería inversa) ---
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

def _fix_img(url):
    """Arregla las URLs de imágenes de Atresplayer"""
    if not url: return ""
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.atresplayer.com" + url
    return url

def list_categories():
    """Menú Principal"""
    # 1. Listar Categorías de la API
    for label, cat_id in CATEGORIES.items():
        list_item = xbmcgui.ListItem(label=label)
        list_item.setArt({'icon': 'DefaultFolder.png'})
        # Llamamos a la acción 'list_section' pasando el ID
        url = get_url(action='list_section', category_id=cat_id)
        xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    # 2. Extras
    list_item = xbmcgui.ListItem(label='[COLOR yellow]Configuración[/COLOR]')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = get_url(action='settings')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    xbmcplugin.endOfDirectory(_handle)

def open_settings():
    addon.openSettings()

# --- PUENTE DE BÚSQUEDA PALANTIR 3 ---
def _p3_b64encode(value):
    """Codificación específica de Palantir 3 (Extraída de ingeniería inversa)"""
    if not isinstance(value, bytes):
        value = str(value).encode()
    value = base64.b64encode(value)
    length = len(value)
    part = int(length / 4)
    value = re.sub(b'=', b'', value)
    # Palantir reversible encoding: reverse 1/4 and 3/4
    encoded = value[:part][::-1] + value[part:][::-1]
    return urllib.parse.quote(encoded.decode())

def search_palantir_bridge(query):
    """Recibe texto plano, lo codifica y llama a Palantir 3"""
    if not query: return
    
    # Palantir espera un string que representa un diccionario de Python
    item_dict = {"action": "buscar3", "sql": f"rebuscar {query}", "label": query}
    
    encoded_item = _p3_b64encode(str(item_dict))
    plugin_url = f"plugin://plugin.video.palantir3/?{encoded_item}"
    xbmc.executebuiltin(f"Container.Update({plugin_url})")

# --- LÓGICA ATRESPLAYER ---
def list_section(category_id):
    """Conecta a la API y lista el contenido de una categoría"""
    # Endpoint descubierto en EspaDaily
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
            # Extraer imagen
            img_data = item.get("image", {})
            raw_thumb = img_data.get("pathHorizontal") or img_data.get("pathVertical")
            thumb = _fix_img(raw_thumb)
            
            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'thumb': thumb, 'icon': thumb})
            list_item.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
            # Por ahora no entramos, solo mostramos (Próximo paso: listar temporadas)
            url = get_url(action='show_info', title=title)
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
        
    xbmcplugin.endOfDirectory(_handle)

def router(paramstring):
    """Enrutador: Decide qué función ejecutar según la URL"""
    params = dict(parse_qsl(paramstring))
    
    # Si no hay acción, vamos al menú principal
    if not params:
        list_categories()
        return

    action = params.get('action')

    if action == 'settings':
        open_settings()
    elif action == 'list_section':
        list_section(params.get('category_id'))
    elif action == 'show_info':
        # Placeholder para cuando hagas click en una serie
        xbmcgui.Dialog().ok("Atresplayer", f"Has seleccionado: {params.get('title')}\n\n(El listado de capítulos se implementará en el siguiente paso)")
    elif action == 'bridge_palantir':
        # Acción llamada desde skins externos
        search_palantir_bridge(params.get('q'))
