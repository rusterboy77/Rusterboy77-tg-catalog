from .common import *

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

def do_search(query=None):
    """Buscador global"""
    # Parte 1: Obtener query si no se ha pasado (soluciona que el teclado vuelva a salir)
    if query is None:
        kb = xbmc.Keyboard('', 'Buscar en Atresplayer')
        kb.doModal()
        if not kb.isConfirmed(): return
        query_text = kb.getText()
        if not query_text: return
        
        # Recargar la vista con la query en la URL para que la navegación funcione
        url = get_url(action='search', query=query_text)
        xbmc.executebuiltin(f"Container.Update({url})")
        return

    # Parte 2: Realizar la búsqueda con la query
    # Establecer tipo de contenido para vista de posters (soluciona vista de iconos)
    xbmcplugin.setContent(_handle, 'tvshows')
    
    # Endpoint de búsqueda actualizado (v1/row/search)
    # Usar quote para garantizar %20 en lugar de + (requests usa + por defecto)
    q_enc = urllib.parse.quote(query)
    url = f"{API_BASE}/client/v1/row/search?text={q_enc}"
    
    s = get_session()
    try:
        # Params según sniffing: entityType=ATPFormat, text=query
        params = {
            "entityType": "ATPFormat",
            "size": 30,
            "page": 0
        }
        xbmc.log(f"ATRES_SEARCH: Consultando {url} | params={params}", xbmc.LOGWARNING)
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        results = []
        # Estructura nueva: itemRows en la raíz
        if "itemRows" in data: results.extend(data["itemRows"])
        
        if "items" in data: results.extend(data["items"])
        if "rows" in data: 
             for row in data["rows"]:
                 if "items" in row: results.extend(row["items"])
                 if "itemRows" in row: results.extend(row["itemRows"])
        
        if not results:
            xbmcgui.Dialog().notification("Atresplayer", "No se encontraron resultados")
            xbmcplugin.endOfDirectory(_handle)
            return

        for item in results:
            title = item.get("title") or item.get("name")
            if not title: continue
            
            img_data = item.get("image") or item.get("images") or {}
            poster = _fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = _fix_img(img_data.get("pathHorizontal"), 'horizontal')
            
            li = xbmcgui.ListItem(label=title)
            li.setArt({'poster': poster, 'icon': poster, 'thumb': poster, 'fanart': fanart})
            li.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
            href = item.get("href") or (item.get("link") or {}).get("href")
            if href:
                # Determinar si es playable o carpeta
                type_ = str(item.get("type")).upper()
                if type_ in ['VIDEO', 'EPISODE', 'MOVIE', 'LIVE']:
                     url_item = get_url(action='play', href=href)
                     is_folder = False
                     li.setProperty('IsPlayable', 'true')
                else:
                     url_item = get_url(action='open_item', href=href)
                     is_folder = True
                
                xbmcplugin.addDirectoryItem(_handle, url_item, li, is_folder)
                
    except Exception as e:
        xbmcgui.Dialog().notification("Error Búsqueda", str(e))
        xbmc.log(f"ATRES_SEARCH_ERR: {e}", xbmc.LOGERROR)
    
    xbmcplugin.endOfDirectory(_handle)