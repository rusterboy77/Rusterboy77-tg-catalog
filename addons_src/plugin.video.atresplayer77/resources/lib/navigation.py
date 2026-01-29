# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import xbmc
import re
import urllib.parse
from .common import get_url, get_icon, fix_img, recursive_find_playable, _handle
from .api import get_session, API_BASE, CATEGORIES, MAIN_CHANNEL_ID

def list_categories():
    """Menú Principal"""
    s = get_session()
    dynamic_items = []
    try:
        r = s.get(f"{API_BASE}/client/v1/menus/web", timeout=5)
        if r.ok:
            menu = r.json()
            for item in menu.get("items", []):
                if item.get("type") == "LINK" and item.get("href"):
                    dynamic_items.append(item)
    except Exception: pass

    # Buscador
    list_item = xbmcgui.ListItem(label='[COLOR yellow]Buscador[/COLOR]')
    list_item.setArt({'icon': get_icon('buscador.png', 'DefaultAddonSearch.png')})
    url = get_url(action='search')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    if dynamic_items:
        for item in dynamic_items:
            label = item.get("title", "Sin título")
            href = item.get("href")
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = get_icon(icon_name, 'DefaultFolder.png')
            
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            
            if "directos" in href or "guia-tv" in href:
                url = get_url(action='list_live')
            else:
                url = get_url(action='open_item', href=href)
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
        
        # Premium y 7 Días
        list_item = xbmcgui.ListItem(label='Premium')
        list_item.setArt({'icon': get_icon('premium.png'), 'thumb': get_icon('premium.png')})
        url = get_url(action='list_section', category_id="605b306f7ed1a86f42397281", category_name="Premium")
        xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': get_icon('ultimos_7_dias.png'), 'thumb': get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
    else:
        # Fallback
        for label, cat_id in CATEGORIES.items():
            icon_name = label.lower().replace(' ', '_') + ".png"
            icon_path = get_icon(icon_name, 'DefaultFolder.png')
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({'icon': icon_path, 'thumb': icon_path})
            url = get_url(action='list_section', category_id=cat_id, category_name=label)
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
        
        list_item = xbmcgui.ListItem(label='Últimos 7 Días')
        list_item.setArt({'icon': get_icon('ultimos_7_dias.png'), 'thumb': get_icon('ultimos_7_dias.png')})
        url = get_url(action='open_item', href='/u7d/')
        xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    # En Directo
    list_item = xbmcgui.ListItem(label='[COLOR red]En Directo (TV)[/COLOR]')
    list_item.setArt({'icon': get_icon('directo.png', 'DefaultAddonPVRClient.png')})
    url = get_url(action='list_live')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    # Cuenta y Config
    list_item = xbmcgui.ListItem(label='[COLOR blue]Iniciar Sesión / Cuenta[/COLOR]')
    list_item.setArt({'icon': get_icon('cuenta.png', 'DefaultUser.png')})
    url = get_url(action='login')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    list_item = xbmcgui.ListItem(label='[COLOR yellow]Configuración[/COLOR]')
    list_item.setArt({'icon': get_icon('configuracion.png', 'DefaultAddonService.png')})
    url = get_url(action='settings')
    xbmcplugin.addDirectoryItem(_handle, url, list_item, False)

    xbmcplugin.endOfDirectory(_handle)

def list_live():
    try:
        s = get_session()
        r = s.get(f"{API_BASE}/client/v1/url", params={"href": "/directos/"}, timeout=10)
        if r.ok:
            data = r.json()
            candidates = (data.get("rows") or []) + (data.get("components") or [])
            for c in candidates:
                title = str(c.get("title", "")).lower()
                if "directo" in title and c.get("href"):
                    open_item(c["href"])
                    return
    except Exception: pass
    open_item('/directos/')

def list_section(category_id, category_name=None, page=0):
    if category_name == "Series": xbmcplugin.setContent(_handle, 'tvshows')
    elif category_name == "Cine": xbmcplugin.setContent(_handle, 'movies')
    else: xbmcplugin.setContent(_handle, 'videos')

    url = f"{API_BASE}/client/v1/row/search"
    params = {"entityType": "ATPFormat", "sectionCategory": "true", "mainChannelId": MAIN_CHANNEL_ID, "categoryId": category_id, "sortType": "THE_MOST", "size": 30, "page": page}
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        for item in data.get("itemRows", []):
            title = item.get("title", "Sin título")
            img_data = item.get("image") or item.get("images") or {}
            poster = fix_img(img_data.get("pathVertical"), 'vertical')
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal')
            if not poster: poster = fanart
            if not fanart: fanart = poster
            
            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart})
            list_item.setInfo('video', {'title': title, 'plot': item.get('description', '')})
            
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
        
        page_info = data.get("pageInfo", {})
        if page_info.get("pageNumber", page) < page_info.get("totalPages", 0) - 1:
            next_page = page_info.get("pageNumber", page) + 1
            url = get_url(action='list_section', category_id=category_id, category_name=category_name, page=next_page)
            list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{page_info.get('totalPages', 0)})[/COLOR]")
            list_item.setArt({'icon': 'DefaultFolder.png'})
            xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
            
    except Exception as e:
        xbmcgui.Dialog().notification("Error API", str(e))
    xbmcplugin.endOfDirectory(_handle)

def open_item(href):
    if "/row/search" in href:
        href = re.sub(r'size=\d+', 'size=30', href) if "size=" in href else (href + "&size=30" if "?" in href else href + "?size=30")

    params = {}
    if href.startswith("http"): url = href
    elif href.startswith("/"): url = f"{API_BASE}/client/v1/url"; params = {"href": href}
    else: url = f"{API_BASE}/client/v1/items{href}"
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Redirecciones
        if data.get("redirect") or (data.get("url") and "components" not in data and "nodes" not in data):
            if "firstEpisode" in data and isinstance(data["firstEpisode"], str):
                 return open_item(f"https://api.atresplayer.com/client/v1/page/episode/{data['firstEpisode']}")
            target = data.get("url") or data.get("href")
            if target:
                if "atresplayer.com" in target: target = urllib.parse.urlparse(target).path
                if target != href and target != href + "/": return open_item(target)

        is_season_view = "seasonId=" in url or "seasonId=" in href
        parent_img = data.get("image") or data.get("images") or {}
        parent_poster = fix_img(parent_img.get("pathVertical"), 'vertical')
        parent_fanart = fix_img(parent_img.get("pathHorizontal"), 'horizontal')

        nodes = []
        if data.get("urlVideo") or data.get("sources"): nodes.append(data)

        main_video_node = None
        has_seasons = "seasons" in data and data["seasons"]
        
        if "firstEpisode" in data and isinstance(data["firstEpisode"], dict) and data["firstEpisode"].get("href"):
             main_video_node = {"title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]", "type": "VIDEO", "href": data["firstEpisode"].get("href"), "image": data.get("image"), "description": data.get("description")}
        
        if not main_video_node:
            hero = data.get('hero')
            if not hero and 'components' in data:
                for c in data['components']:
                    if c.get('component') in ['Hero', 'HERO', 'Showcase', 'Header', 'Poster', 'Banner']: hero = c; break
            if hero:
                for action in (hero.get("actions") or hero.get("buttons") or hero.get("links") or []):
                    if action.get("type") == "PLAY" or "reproducir" in str(action.get("label", "")).lower():
                        main_video_node = {"title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]", "type": "VIDEO", "href": action.get("href"), "image": data.get("image"), "description": data.get("description")}; break

        if not main_video_node and not has_seasons:
             candidates = []
             recursive_find_playable(data, candidates)
             for c in candidates:
                 if '/episode/' in c.get('href', '') or '/player/' in c.get('href', ''):
                     main_video_node = {"title": f"[COLOR green]▶ Reproducir: {data.get('title')}[/COLOR]", "type": "VIDEO", "href": c.get('href'), "image": data.get("image"), "description": data.get("description")}; break

        content_nodes = []
        if "episodes" in data and data["episodes"]: content_nodes.extend(data["episodes"])
        elif "seasons" in data and not is_season_view:
            for season in data["seasons"]:
                if "episodes" in season: content_nodes.extend(season["episodes"])
                elif "items" in season: content_nodes.extend(season["items"])
                else: content_nodes.append(season)

        other_containers = (data.get("components") or []) + (data.get("rows") or [])
        BAD_TITLES = ["clips", "extras", "secciones", "mejores momentos", "relacionado", "reparto", "detalles", "más de", "redes", "te puede interesar", "caras", "interesar", "sigue viendo", "recomendado", "suscríbete", "noticias", "blog", "capítulos", "capitulos", "temporadas", "episodios", "programas", "programas completos"]
        
        for container in other_containers:
            c_title = (container.get("title") or "").lower()
            if is_season_view and ("capítulos" in c_title or container.get("type") == "EPISODE") and container.get("href"):
                 try:
                     eps_href = container["href"] + ("&size=30" if "?" in container["href"] else "?size=30")
                     r_eps = s.get(eps_href, timeout=5)
                     if r_eps.ok:
                         d_eps = r_eps.json()
                         if "items" in d_eps: content_nodes.extend(d_eps["items"])
                         elif "itemRows" in d_eps: content_nodes.extend(d_eps["itemRows"])
                 except Exception: pass
                 continue
            if any(bad in c_title for bad in BAD_TITLES): continue
            if "items" in container: content_nodes.extend(container["items"])
            elif "rows" in container:
                for row in container["rows"]:
                    if not any(bad in (row.get("title") or "").lower() for bad in BAD_TITLES): content_nodes.extend(row.get("items") or [])
                    # FIX: Añadir filas lazy (con href pero sin items) como nodos navegables
                    if "href" in row and "items" not in row:
                        content_nodes.append(row)
            elif "href" in container and "title" in container and container.get("type") not in ["HERO", "Hero"]: content_nodes.append(container)

        if "nodes" in data: content_nodes.extend(data["nodes"])
        if "itemRows" in data: content_nodes.extend(data["itemRows"])
        if "episode" in data: content_nodes.append(data["episode"])

        if main_video_node and not content_nodes: nodes.append(main_video_node)
        nodes.extend(content_nodes)

        if is_season_view or "itemRows" in data: xbmcplugin.setContent(_handle, 'episodes')
        elif "seasons" in data: xbmcplugin.setContent(_handle, 'seasons')
        else: xbmcplugin.setContent(_handle, 'videos')

        if not nodes:
            xbmcgui.Dialog().notification("Atresplayer", "No se encontraron enlaces reproducibles")
            xbmcplugin.endOfDirectory(_handle); return

        for node in nodes:
            title = node.get("title") or node.get("name") or "Sin título"
            img_data = node.get("image") or node.get("images") or {}
            poster = fix_img(img_data.get("pathVertical"), 'vertical') or parent_poster
            fanart = fix_img(img_data.get("pathHorizontal"), 'horizontal') or parent_fanart
            if not poster: poster = fanart
            if not fanart: fanart = poster

            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({'poster': poster, 'icon': poster, 'thumb': fanart, 'fanart': fanart})
            info = {'title': title, 'plot': node.get('description', '')}
            if "episode" in node:
                try: info['episode'] = int(node["episode"])
                except: pass
            if "Página Siguiente" in title: info['episode'] = 99999; list_item.setProperty('SpecialSort', 'bottom')
            list_item.setInfo('video', info)
            
            sub_href = node.get("href") or (node.get("link") or {}).get("href")
            looks_like_video = sub_href and ("/episode/" in sub_href or "/player/" in sub_href)
            is_row_container = sub_href and ("/row/" in sub_href or "search" in sub_href)
            
            if sub_href and not looks_like_video and (node.get("type") not in ['EPISODE', 'VIDEO', 'MOVIE', 'LIVE', 'CHANNEL'] or is_row_container):
                url = get_url(action='open_item', href=sub_href)
                xbmcplugin.addDirectoryItem(_handle, url, list_item, True)
            else:
                url = get_url(action='play', href=sub_href or href)
                list_item.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(_handle, url, list_item, False)
        
        # FIX: Restaurar bloque de paginación
        if "pageInfo" in data:
            page_info = data["pageInfo"]
            total_pages = page_info.get("totalPages", 0)
            current_page = page_info.get("pageNumber", 0)
            
            if current_page < total_pages - 1:
                next_page = current_page + 1
                if "page=" in href: next_href = re.sub(r'page=\d+', f'page={next_page}', href)
                elif "?" in href: next_href = href + f"&page={next_page}"
                else: next_href = href + f"?page={next_page}"
                
                url = get_url(action='open_item', href=next_href)
                list_item = xbmcgui.ListItem(label=f"[COLOR yellow]>> Página Siguiente ({next_page + 1}/{total_pages})[/COLOR]")
                list_item.setArt({'icon': 'DefaultFolder.png'})
                xbmcplugin.addDirectoryItem(_handle, url, list_item, True)

    except Exception as e: xbmcgui.Dialog().notification("Error Navegación", str(e))
    xbmcplugin.endOfDirectory(_handle)