from .common import *

def list_categories():
    """Menú Principal"""
    # Helper local para buscar iconos personalizados o usar fallback
    def _get_icon(name, default='DefaultFolder.png'):
        icon_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media', name)
        if os.path.exists(icon_path): return icon_path
        return default

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

    # 0. Buscador y Seguir Viendo (Arriba para acceso rápido)
    list_item = xbmcgui.ListItem(label='[COLOR yellow]Buscador[/COLOR]')
    list_item.setArt({'icon': _get_icon('buscador.png', 'DefaultAddonSearch.png')})
    url = get_url(action='search')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)

    if dynamic_items:
        for item in dynamic_items:
            label = item.get("title", "Sin título")
            href = item.get("href")
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = _get_icon(icon_name, 'DefaultFolder.png')
            
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            
            if "directos" in href or "guia-tv" in href:
                url = get_url(action='list_live')
            else:
                url = get_url(action='open_item', href=href)
            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
        
        # Añadir manualmente secciones que el filtro LINK suele ocultar
        # Premium
        list_item = xbmcgui.ListItem(label='Premium')
        list_item.setArt({'icon': _get_icon('premium.png'), 'thumb': _get_icon('premium.png')})
        url = get_url(action='list_section', category_id="605b306f7ed1a86f42397281", category_name="Premium")
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

        # Últimos 7 Días (7UD)
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': _get_icon('ultimos_7_dias.png'), 'thumb': _get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    else:
        # Fallback a categorías hardcoded
        for label, cat_id in CATEGORIES.items():
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = _get_icon(icon_name, 'DefaultFolder.png')
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            url = get_url(action='list_section', category_id=cat_id, category_name=label)
            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
        
        # Añadir 7UD al fallback también
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': _get_icon('ultimos_7_dias.png'), 'thumb': _get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    # Siempre añadir acceso directo a Live por si acaso
    list_item = xbmcgui.ListItem(label='En Directo (TV)')
    list_item.setArt({'icon': _get_icon('directo.png', 'DefaultAddonPVRClient.png')})
    url = get_url(action='list_live')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    # 2. Login / Cuenta
    list_item = xbmcgui.ListItem(label='[COLOR blue]Iniciar Sesión / Cuenta[/COLOR]')
    list_item.setArt({'icon': _get_icon('cuenta.png', 'DefaultUser.png')})
    url = get_url(action='login')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)

    # 3. Configuración
    list_item = xbmcgui.ListItem(label='Configuración')
    list_item.setArt({'icon': _get_icon('configuracion.png', 'DefaultAddonService.png')})
    url = get_url(action='settings')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)

    xbmcplugin.endOfDirectory(HANDLE)

def list_live():
    """Lista los canales en directo"""
    # Usar la ruta web oficial, ya que la API directa /live/channels da 404
    open_item('/directos/')

def list_section(category_id, category_name=None, page=0):
    """Conecta a la API y lista el contenido de una categoría"""
    
    # Establecer el tipo de contenido para que la skin active las vistas (Poster, Fanart, etc.)
    if category_name == "Series":
        xbmcplugin.setContent(HANDLE, 'tvshows')
    elif category_name == "Cine":
        xbmcplugin.setContent(HANDLE, 'movies')
    else:
        xbmcplugin.setContent(HANDLE, 'videos')

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
            poster = fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal')
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
                    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)
                else:
                    url = get_url(action='open_item', href=href)
                    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
        
        # Paginación
        page_info = data.get("pageInfo", {})
        total_pages = page_info.get("totalPages", 0)
        current_page = page_info.get("pageNumber", page)
        
        if current_page < total_pages - 1:
            next_page = current_page + 1
            url = get_url(action='list_section', category_id=category_id, category_name=category_name, page=next_page)
            list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{total_pages})[/COLOR]")
            list_item.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
        
    xbmcplugin.endOfDirectory(HANDLE)

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
        
        # DETECCIÓN: Es una página de directos?
        is_live_page = data.get("pageType") == "LIVE"

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

        # Detectar si estamos navegando dentro de una temporada específica
        is_season_view = "seasonId=" in url or "seasonId=" in href
        
        # Imagen de cabecera (Serie/Programa padre) para fallback
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = fix_img(parent_img.get("pathHorizontal"), 'horizontal')

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
             recursive_find_playable(data, candidates)
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
            
            # --- SOLUCIÓN REDUNDANCIA: Expansión automática para Directos ---
            # Si estamos en Directos y hay una fila que es solo un enlace (carpeta), la cargamos aquí mismo
            if is_live_page and container.get("href") and not container.get("items") and not container.get("rows"):
                try:
                     row_href = container["href"]
                     # Ajustar parámetros
                     if "size=" in row_href:
                         row_href = re.sub(r'size=\d+', 'size=30', row_href)
                     elif "?" in row_href:
                         row_href += "&size=30"
                     else:
                         row_href += "?size=30"
                     
                     # xbmc.log(f"ATRES_AUTO_EXPAND: Cargando {row_href}", xbmc.LOGWARNING)
                     r_row = s.get(row_href, timeout=5)
                     if r_row.ok:
                         d_row = r_row.json()
                         if "items" in d_row: content_nodes.extend(d_row["items"])
                         elif "itemRows" in d_row: content_nodes.extend(d_row["itemRows"])
                         elif "rows" in d_row:
                             for r in d_row["rows"]:
                                 if "items" in r: content_nodes.extend(r["items"])
                         # Marcar como expandido y continuar para no añadir la carpeta original
                         continue 
                except Exception: pass

            # Lógica normal para series/programas (expandir capítulos)
            if is_season_view and ("capítulos" in c_title or container.get("type") == "EPISODE") and container.get("href"):
                 try:
                     # MODIFICACIÓN: Forzar size=30 y gestionar paginación
                     eps_href = container["href"]
                     if "size=" in eps_href:
                         eps_href = re.sub(r'size=\d+', 'size=30', eps_href)
                     elif "?" in eps_href:
                         eps_href += "&size=30"
                     else:
                         eps_href += "?size=30"

                     r_eps = s.get(eps_href, timeout=5)
                     if r_eps.ok:
                         d_eps = r_eps.json()
                         if "items" in d_eps: content_nodes.extend(d_eps["items"])
                         elif "itemRows" in d_eps: content_nodes.extend(d_eps["itemRows"])
                         elif "rows" in d_eps:
                             for r in d_eps["rows"]:
                                 if "items" in r: content_nodes.extend(r["items"])
                         
                         # Añadir botón de siguiente página si es necesario
                         if "pageInfo" in d_eps:
                             pi = d_eps["pageInfo"]
                             if pi.get("pageNumber", 0) < pi.get("totalPages", 0) - 1:
                                 next_p = pi.get("pageNumber", 0) + 1
                                 total_p = pi.get("totalPages", 0)
                                 
                                 if "page=" in eps_href:
                                     next_href = re.sub(r'page=\d+', f'page={next_p}', eps_href)
                                 elif "?" in eps_href:
                                     next_href = eps_href + f"&page={next_p}"
                                 else:
                                     next_href = eps_href + f"?page={next_p}"
                                 
                                 content_nodes.append({
                                     "title": f"[COLOR yellow]>> Página Siguiente ({next_p + 1}/{total_p})[/COLOR]",
                                     "type": "LINK",
                                     "href": next_href,
                                     "image": {"pathVertical": "DefaultFolder.png"}
                                 })
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
        
        # IMPORTANTE: Desactivar "Modo Película" si estamos en Directos (LIVE)
        is_movie_mode = main_video_node and not has_seasons and not is_live_page
        
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
            # Si es serie con temporadas explícitas O PAGINA DIRECTOS, todo el contenido recopilado es válido
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
             recursive_find_playable(data, candidates)
             for c in candidates:
                 nodes.append({
                    "title": f"[COLOR green]▶ {c.get('label') or 'Reproducir'}[/COLOR]", 
                    "type": "VIDEO",
                    "href": c.get('href'),
                    "image": data.get("image")
                 })
        
        # Establecer tipo de contenido para las vistas
        if is_season_view or "itemRows" in data:
            xbmcplugin.setContent(HANDLE, 'episodes')
        elif "seasons" in data:
            xbmcplugin.setContent(HANDLE, 'seasons') # O 'tvshows' si prefieres vista de serie
        else:
            xbmcplugin.setContent(HANDLE, 'videos')

        if not nodes:
            # Si no hay nodos, puede ser un capítulo suelto o una película lista para ver
            # xbmc.log(f"ATRES_DEBUG_NO_NODES: Keys={list(data.keys())}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification("Atresplayer", "No se encontraron enlaces reproducibles")
            xbmcplugin.endOfDirectory(HANDLE) # Importante cerrar directorio para evitar error en log
            return

        for node in nodes:
            title = node.get("title") or node.get("name") or "Sin título"
            
            # Imagen
            img_data = node.get("image") or node.get("images") or {}
            poster = fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal')
            
            # MEJORA: Buscar fanart local si no viene de la API (para U7D y canales)
            if not poster and not fanart:
                safe_name = title.lower().strip().replace(' ', '_')
                
                # Parche: Usar cine_2 para diferenciar de la sección principal
                if safe_name == 'cine': safe_name = 'cine_2'

                # Intentar buscar en resources/media/ (ej: antena_3.png, lasexta.png)
                media_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media')
                for ext in ['.png', '.jpg', '.jpeg']:
                    local_img = os.path.join(media_path, safe_name + ext)
                    if os.path.exists(local_img):
                        poster = local_img
                        fanart = local_img
                        break

            # Fallbacks con imagen padre
            if not poster: poster = parent_poster
            if not fanart: fanart = parent_fanart
            if not poster: poster = fanart
            if not fanart: fanart = poster

            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart})
            
            info = {'title': title, 'plot': node.get('description', '')}
            
            # Intentar obtener número de episodio para ordenación correcta
            if "episode" in node:
                try: info['episode'] = int(node["episode"])
                except: pass
            
            # Fix: Forzar que el botón de "Siguiente Página" aparezca al final
            if "Página Siguiente" in title:
                info['episode'] = 99999
                list_item.setProperty('SpecialSort', 'bottom')

            list_item.setInfo('video', info)
            
            # Recursividad: Si tiene href, podemos entrar. Si no, es video final.
            sub_link = node.get("link") or {}
            sub_href = node.get("href") or sub_link.get("href")
            
            # CORRECCIÓN URGENTE PARA CANALES EN DIRECTO Y U7D
            # 1. Si NO tenemos href pero hay contentId, intentamos generar la URL correcta.
            
            node_type = str(node.get("type", "")).upper()
            
            if not sub_href and node.get("contentId"):
                 if "LIVE" in node_type or "CHANNEL" in node_type:
                     sub_href = f"/player/v1/live/{node['contentId']}"
                 elif node_type in ["EPISODE", "VIDEO"]:
                     sub_href = f"/player/v1/episode/{node['contentId']}"
                 # Si es FORMAT, dejamos sub_href vacío para que open_item lo maneje (o falle y no haga bucle)

            # 2. Detectar si es un contenedor (carpeta)
            is_row_container = sub_href and ("/row/" in sub_href or "search" in sub_href)
            
            # 3. Detectar si parece un video final
            looks_like_video = sub_href and ("/episode/" in sub_href or "/player/" in sub_href)
            
            # 4. Decisión final: ¿Carpeta o Play?
            # Si es FORMAT (Programas en U7D), debe ser carpeta.
            if node_type == "FORMAT" and sub_href and not looks_like_video:
                 url = get_url(action='open_item', href=sub_href)
                 is_folder = True
            elif sub_href and not looks_like_video and (node_type not in ['EPISODE', 'VIDEO', 'MOVIE', 'LIVE', 'CHANNEL', 'LIVE_CHANNEL'] or is_row_container):
                url = get_url(action='open_item', href=sub_href)
                is_folder = True
            else:
                # Es un video final
                target_href = sub_href if sub_href else href
                
                # Evitar bucle infinito si no hay sub_href
                if not sub_href and target_href == href:
                    continue

                url = get_url(action='play', href=target_href)
                is_folder = False
                list_item.setProperty('IsPlayable', 'true')

            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, is_folder)

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
                xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    except Exception as e:
        xbmcgui.Dialog().notification("Error Navegación", str(e))
    
    xbmcplugin.endOfDirectory(HANDLE)