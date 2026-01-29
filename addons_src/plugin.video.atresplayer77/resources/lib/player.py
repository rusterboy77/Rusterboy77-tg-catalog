from .common import *

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
            recursive_find_playable(data, candidates)
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
             xbmcgui.Dialog().notification("Atresplayer", "No se encontraron fuentes de video")
             return

        # Crear el item de reproducción
        li = xbmcgui.ListItem(path=video_url)
        # Configurar InputStream Adaptive (necesario para DASH/HLS)
        if ".mpd" in video_url or ".m3u8" in video_url:
            li.setProperty('inputstream', 'inputstream.adaptive')
            
            # Detectar DRM y configurar licencia si existe
            drm_url = ""
            if "drm" in data and isinstance(data["drm"], dict):
                drm_url = data["drm"].get("widevine", {}).get("url", "")
            
            # Búsqueda recursiva si no se encuentra en la raíz (para estructuras anidadas)
            if not drm_url:
                widevine_data = _find_key(data, "widevine")
                if widevine_data and isinstance(widevine_data, dict):
                    drm_url = widevine_data.get("url", "")
            
            # DIAGNÓSTICO: Si no encontramos DRM, volcamos la respuesta al log para ver qué estructura tiene
            if not drm_url and (".mpd" in video_url or ".m3u8" in video_url):
                xbmc.log(f"ATRES_DRM_FAIL: No se encontró clave DRM. Respuesta API: {json.dumps(data)}", xbmc.LOGWARNING)

            if drm_url:
                li.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
                li.setProperty('inputstream.adaptive.license_key', drm_url)
            
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

        xbmcplugin.setResolvedUrl(HANDLE, True, li)

    except Exception as e:
        xbmcgui.Dialog().notification("Error Reproducción", str(e))
        xbmc.log(f"ATRES_PLAY_ERR: {e}", xbmc.LOGERROR)