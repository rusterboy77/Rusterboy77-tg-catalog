from .common import *

def list_categories():
    """Menú Principal"""
    def _get_icon(name, default='DefaultFolder.png'):
        icon_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media', name)
        if os.path.exists(icon_path): return icon_path
        return default

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

    # 0. Buscador
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
        
        # Añadidos manuales importantes
        list_item = xbmcgui.ListItem(label='Premium')
        list_item.setArt({'icon': _get_icon('premium.png'), 'thumb': _get_icon('premium.png')})
        url = get_url(action='list_section', category_id="605b306f7ed1a86f42397281", category_name="Premium")
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': _get_icon('ultimos_7_dias.png'), 'thumb': _get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    else:
        # Fallback
        for label, cat_id in CATEGORIES.items():
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = _get_icon(icon_name, 'DefaultFolder.png')
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            url = get_url(action='list_section', category_id=cat_id, category_name=label)
            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
        
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': _get_icon('ultimos_7_dias.png'), 'thumb': _get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    list_item = xbmcgui.ListItem(label='En Directo (TV)')
    list_item.setArt({'icon': _get_icon('directo.png', 'DefaultAddonPVRClient.png')})
    url = get_url(action='list_live')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    # Login y Config
    list_item = xbmcgui.ListItem(label='[COLOR blue]Iniciar Sesión / Cuenta[/COLOR]')
    list_item.setArt({'icon': _get_icon('cuenta.png', 'DefaultUser.png')})
    url = get_url(action='login')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)

    list_item = xbmcgui.ListItem(label='Configuración')
    list_item.setArt({'icon': _get_icon('configuracion.png', 'DefaultAddonService.png')})
    url = get_url(action='settings')
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, False)

    xbmcplugin.endOfDirectory(HANDLE)

def list_live():
    """Lista los canales en directo"""
    open_item('/directos/')

def list_section(category_id, category_name=None, page=0):
    """Lista el contenido de una categoría"""
    if category_name == "Series": xbmcplugin.setContent(HANDLE, 'tvshows')
    elif category_name == "Cine": xbmcplugin.setContent(HANDLE, 'movies')
    else: xbmcplugin.setContent(HANDLE, 'videos')

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
            img_data = item.get("image") or item.get("images") or {}
            poster = fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal')
            
            # Buscar logo: Prioridad logoURL (root) > pathLogo (images) > program > channel
            logo_path = item.get("logoURL") or img_data.get("pathLogo")
            if not logo_path and "program" in item:
                logo_path = (item["program"].get("images") or {}).get("pathLogo")
            if not logo_path and "channel" in item:
                logo_path = (item["channel"].get("images") or {}).get("pathLogo")
            
            clearlogo = fix_img(logo_path, 'logo')
            if not poster: poster = fanart
            if not fanart: fanart = poster
            
            list_item = xbmcgui.ListItem(label=title)
            art = {'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart}
            if clearlogo: art['clearlogo'] = clearlogo
            if clearlogo: art['clearart'] = clearlogo
            list_item.setArt(art)
            list_item.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
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
        
        page_info = data.get("pageInfo", {})
        if page_info.get("pageNumber", page) < page_info.get("totalPages", 0) - 1:
            next_page = page_info.get("pageNumber", page) + 1
            url = get_url(action='list_section', category_id=category_id, category_name=category_name, page=next_page)
            list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{page_info.get('totalPages', 0)})[/COLOR]")
            list_item.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
        
    xbmcplugin.endOfDirectory(HANDLE)

def open_item(href):
    """Navega dentro de una serie, temporada o programa"""
    # Ajuste de tamaño de página
    if "/row/search" in href:
        if "size=" in href: href = re.sub(r'size=\d+', 'size=30', href)
        elif "?" in href: href += "&size=30"
        else: href += "?size=30"

    # Resolución de URL
    params = {}
    if href.startswith("http"): url = href
    elif href.startswith("/"):
        url = f"{API_BASE}/client/v1/url"
        params = {"href": href}
    else: url = f"{API_BASE}/client/v1/items{href}"
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # --- DETECCIÓN DE REDIRECCIÓN Y TIPO DE PÁGINA ---
        # Detectamos si es la página de Directos para activar el fix de redundancia
        is_live_page = data.get("pageType") == "LIVE"

        # Detectar si es un objeto de redirección/resolución (tiene href/url pero no contenido)
        is_resolution_object = (data.get("href") or data.get("url")) and "components" not in data and "nodes" not in data and "itemRows" not in data
        if data.get("redirect") or is_resolution_object:
            # Prioridad 1: ID de episodio directo
            if "firstEpisode" in data and isinstance(data["firstEpisode"], str):
                 ep_id = data["firstEpisode"]
                 target = f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
                 return open_item(target)
            # Prioridad 2: API Href
            if data.get("href") and "api.atresplayer.com" in data["href"]:
                target = data["href"]
                if target != href: return open_item(target)
            # Prioridad 3: URL/Href genérico
            target = data.get("url") or data.get("href")
            if target:
                if "atresplayer.com" in target:
                    parsed = urllib.parse.urlparse(target)
                    target = parsed.path
                    if parsed.query: target += "?" + parsed.query
                if target != href and target != href + "/":
                    return open_item(target)

        is_season_view = "seasonId=" in url or "seasonId=" in href
        
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = fix_img(parent_img.get("pathHorizontal"), 'horizontal')

        nodes = []
        
        # Estrategia 0: El propio objeto es reproducible
        if data.get("urlVideo") or data.get("sources"):
             nodes.append(data)

        # --- FASE 1: BUSCAR VIDEO PRINCIPAL (PLAY) ---
        main_video_node = None
        has_seasons = "seasons" in data and data["seasons"]
        
        if "firstEpisode" in data and isinstance(data["firstEpisode"], dict) and data["firstEpisode"].get("href"):
             ep = data["firstEpisode"]
             main_video_node = {
                 "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                 "type": "VIDEO",
                 "href": ep.get("href"),
                 "image": data.get("image"),
                 "description": data.get("description")
             }

        if not main_video_node and "episode" in data:
             ep_val = data["episode"]
             ep_target = None
             if isinstance(ep_val, str): ep_target = ep_val
             elif isinstance(ep_val, dict): ep_target = ep_val.get("href")

             if ep_target:
                 main_video_node = {
                     "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                     "type": "VIDEO",
                     "href": ep_target,
                     "image": data.get("image"),
                     "description": data.get("description")
                 }

        if not main_video_node:
            hero = data.get('hero')
            if not hero and 'components' in data:
                for c in data['components']:
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
        
        if not main_video_node and not has_seasons and data.get("id"):
             try:
                 fmt_id = data["id"]
                 url_prog = f"{API_BASE}/client/v1/inProgressFormat/watch/{fmt_id}"
                 r_prog = s.get(url_prog, timeout=5)
                 if r_prog.ok:
                     d_prog = r_prog.json()
                     ep_id = None
                     if "firstEpisode" in d_prog:
                         val = d_prog["firstEpisode"]
                         if isinstance(val, str): ep_id = val
                         elif isinstance(val, dict): ep_id = val.get("id") or val.get("href")
                     if ep_id:
                         target = ep_id if (str(ep_id).startswith("http") or str(ep_id).startswith("/")) else f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}"
                         main_video_node = {
                             "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                             "type": "VIDEO",
                             "href": target,
                             "image": data.get("image"),
                             "description": data.get("description")
                         }
             except Exception: pass

        if not main_video_node and not has_seasons:
             candidates = []
             recursive_find_playable(data, candidates)
             for c in candidates:
                 h = c.get('href', '')
                 if '/episode/' in h or '/player/' in h:
                     main_video_node = {
                        "title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]",
                        "type": "VIDEO",
                        "href": h,
                        "image": data.get("image"),
                        "description": data.get("description")
                     }
                     break

        # --- FASE 2: PROCESAR CONTENIDO ADICIONAL ---
        content_nodes = []
        
        if "episodes" in data and data["episodes"]:
             content_nodes.extend(data["episodes"])
        elif "seasons" in data and not is_season_view:
            for season in data["seasons"]:
                found_eps = False
                if "episodes" in season: content_nodes.extend(season["episodes"]); found_eps = True
                elif "items" in season: content_nodes.extend(season["items"]); found_eps = True
                if not found_eps: content_nodes.append(season)

        other_containers = []
        if "components" in data: other_containers.extend(data["components"])
        if "rows" in data: other_containers.extend(data["rows"])
        
        # Detectar si estamos en la sección de Últimos 7 Días para no filtrarla
        is_u7d = "/u7d/" in href or "ultimos-7-dias" in href or data.get("pageType") == "U7D"
        
        BAD_TITLES = ["clips", "extras", "mejores momentos", "relacionado", "reparto", "detalles", "más de", "redes", "te puede interesar", "caras", "interesar", "sigue viendo", "recomendado", "suscríbete", "noticias", "blog"]
        # CORRECCIÓN: Bloquear solo "mosaico directo" para no borrar contenido útil de U7D que venga en "Mosaico"
        if not is_u7d: BAD_TITLES.extend(["últimos 7 días", "ultimos 7 dias", "mosaico directo"])
        
        for container in other_containers:
            c_title = (container.get("title") or "").lower()
            
            # --- SOLUCIÓN REDUNDANCIA: Expansión automática para Directos ---
            # Solo se activa si is_live_page es True (Página de directos)
            if is_live_page and container.get("href") and not container.get("items") and not container.get("rows"):
                try:
                     row_href = container["href"]
                     if "size=" in row_href: row_href = re.sub(r'size=\d+', 'size=30', row_href)
                     elif "?" in row_href: row_href += "&size=30"
                     else: row_href += "?size=30"
                     
                     r_row = s.get(row_href, timeout=5)
                     if r_row.ok:
                         d_row = r_row.json()
                         if "items" in d_row: content_nodes.extend(d_row["items"])
                         elif "itemRows" in d_row: content_nodes.extend(d_row["itemRows"])
                         elif "rows" in d_row: 
                             for r in d_row["rows"]:
                                 if "items" in r: content_nodes.extend(r["items"])
                         # Continue evita que se añada la carpeta, ya que hemos expandido el contenido
                         continue 
                except Exception: pass

            if is_season_view and ("capítulos" in c_title or container.get("type") == "EPISODE") and container.get("href"):
                 try:
                     eps_href = container["href"]
                     if "size=" in eps_href: eps_href = re.sub(r'size=\d+', 'size=30', eps_href)
                     elif "?" in eps_href: eps_href += "&size=30"
                     else: eps_href += "?size=30"

                     r_eps = s.get(eps_href, timeout=5)
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
            
            c_href = container.get("href") or ""
            if "entityType=ATPClip" in c_href or "entityType=ATPExtra" in c_href or "entityType=ATPSection" in c_href: continue

            if "items" in container: content_nodes.extend(container["items"])
            elif "rows" in container:
                for row in container["rows"]:
                    r_title = (row.get("title") or "").lower()
                    if any(bad in r_title for bad in BAD_TITLES): continue
                    content_nodes.extend(row.get("items") or [])
            elif "episodes" in container: content_nodes.extend(container["episodes"])
            elif "nodes" in container: content_nodes.extend(container["nodes"])
            elif "href" in container and "title" in container and container.get("type") not in ["HERO", "Hero"]:
                 content_nodes.append(container)

        if "nodes" in data: content_nodes.extend(data["nodes"])
        if "itemRows" in data: content_nodes.extend(data["itemRows"])
        if "episode" in data: content_nodes.append(data["episode"])

        # --- FASE 3: LISTA FINAL ---
        
        # IMPORTANTE: Desactivar "Modo Película" si estamos en Directos (LIVE)
        is_movie_mode = main_video_node and not has_seasons and not is_live_page
        
        valid_content = []
        if is_movie_mode:
            for n in content_nodes:
                ntype = str(n.get("type", "")).upper()
                if ntype in ["EPISODE", "VIDEO"] or "season" in str(n).lower():
                    valid_content.append(n)
        else:
            valid_content.extend(content_nodes)

        if main_video_node and not valid_content:
            nodes.append(main_video_node)

        nodes.extend(valid_content)

        if not nodes and not main_video_node:
             candidates = []
             recursive_find_playable(data, candidates)
             for c in candidates:
                 nodes.append({
                    "title": f"[COLOR green]▶ {c.get('label') or 'Reproducir'}[/COLOR]", 
                    "type": "VIDEO",
                    "href": c.get('href'),
                    "image": data.get("image")
                 })
        
        if is_season_view or "itemRows" in data: xbmcplugin.setContent(HANDLE, 'episodes')
        elif "seasons" in data: xbmcplugin.setContent(HANDLE, 'seasons')
        else: xbmcplugin.setContent(HANDLE, 'videos')

        if not nodes:
            xbmcgui.Dialog().notification("Atresplayer", "No se encontraron enlaces")
            xbmcplugin.endOfDirectory(HANDLE)
            return

        for node in nodes:
            title = node.get("title") or node.get("name") or "Sin título"
            
            img_data = node.get("image") or node.get("images") or {}
            poster = fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal')
            
            # Buscar logo: Prioridad logoURL (root) > pathLogo (images) > program > channel
            logo_path = node.get("logoURL") or img_data.get("pathLogo")
            if not logo_path and "program" in node:
                logo_path = (node["program"].get("images") or {}).get("pathLogo")
            if not logo_path and "channel" in node:
                logo_path = (node["channel"].get("images") or {}).get("pathLogo")
            
            clearlogo = fix_img(logo_path, 'logo')
            
            if not poster and not fanart:
                safe_name = title.lower().strip().replace(' ', '_')
                if safe_name == 'cine': safe_name = 'cine_2'
                media_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media')
                for ext in ['.png', '.jpg', '.jpeg']:
                    local_img = os.path.join(media_path, safe_name + ext)
                    if os.path.exists(local_img):
                        poster = local_img; fanart = local_img; break

            if not poster: poster = parent_poster
            if not fanart: fanart = parent_fanart
            if not poster: poster = fanart
            if not fanart: fanart = poster

            list_item = xbmcgui.ListItem(label=title)
            art = {'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart}
            if clearlogo: art['clearlogo'] = clearlogo
            if clearlogo: art['clearart'] = clearlogo
            list_item.setArt(art)
            
            info = {'title': title, 'plot': node.get('description', '')}
            if "episode" in node:
                try: info['episode'] = int(node["episode"])
                except: pass
            
            if "Página Siguiente" in title:
                info['episode'] = 99999
                list_item.setProperty('SpecialSort', 'bottom')

            list_item.setInfo('video', info)
            
            sub_link = node.get("link") or {}
            sub_href = node.get("href") or sub_link.get("href")
            
            # --- CORRECCIÓN FINAL: Restaurada lógica original estricta para sub_href ---
            # Eliminado cualquier bloque que forzara /player/v1/...
            
            node_type = str(node.get("type", "")).upper()
            is_row_container = sub_href and ("/row/" in sub_href or "search" in sub_href)
            looks_like_video = sub_href and ("/episode/" in sub_href or "/player/" in sub_href)
            
            # Decisión Play vs Carpeta usando la lógica que funcionaba antes, añadiendo los tipos LIVE
            if sub_href and not looks_like_video and (node_type not in ['EPISODE', 'VIDEO', 'MOVIE', 'LIVE', 'CHANNEL', 'LIVE_CHANNEL'] or is_row_container):
                url = get_url(action='open_item', href=sub_href)
                is_folder = True
            else:
                target_href = sub_href if sub_href else href
                if not sub_href and target_href == href: continue
                url = get_url(action='play', href=target_href)
                is_folder = False
                list_item.setProperty('IsPlayable', 'true')

            xbmcplugin.addDirectoryItem(HANDLE, url, list_item, is_folder)

        if "pageInfo" in data:
            page_info = data["pageInfo"]
            if page_info.get("pageNumber", 0) < page_info.get("totalPages", 0) - 1:
                next_p = page_info.get("pageNumber", 0) + 1
                if "page=" in href: next_href = re.sub(r'page=\d+', f'page={next_p}', href)
                elif "?" in href: next_href = href + f"&page={next_p}"
                else: next_href = href + f"?page={next_p}"
                
                url = get_url(action='open_item', href=next_href)
                list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_p + 1}/{page_info.get('totalPages', 0)})[/COLOR]")
                list_item.setArt({'icon': 'DefaultFolder.png'})
                xbmcplugin.addDirectoryItem(HANDLE, url, list_item, True)

    except Exception as e:
        xbmcgui.Dialog().notification("Error Navegación", str(e))
    
    xbmcplugin.endOfDirectory(HANDLE)