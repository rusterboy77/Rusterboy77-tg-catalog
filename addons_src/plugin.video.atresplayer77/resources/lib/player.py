# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import xbmc
import urllib.parse
from .common import _handle, recursive_find_playable
from .api import get_session, API_BASE

def play(href):
    """Resuelve la URL del vídeo y lo reproduce"""
    params = {}
    if href.startswith("http"): url = href
    elif href.startswith("/"): url = f"{API_BASE}/client/v1/url"; params = {"href": href}
    else: url = f"{API_BASE}/client/v1/items{href}"
    
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        video_url = data.get("urlVideo")

        # Redirecciones y fallbacks
        if data.get("href") and "api.atresplayer.com" in data["href"] and not video_url and not data.get("sources"):
             if data["href"] != href: return play(data["href"])

        if "firstEpisode" in data and isinstance(data["firstEpisode"], str):
             return play(f"https://api.atresplayer.com/client/v1/page/episode/{data['firstEpisode']}")

        if not video_url and not data.get("sources") and data.get("id"):
             try:
                 r_prog = s.get(f"{API_BASE}/client/v1/inProgressFormat/watch/{data['id']}", timeout=5)
                 if r_prog.ok:
                     d_prog = r_prog.json()
                     if "firstEpisode" in d_prog:
                         val = d_prog["firstEpisode"]
                         ep_id = val if isinstance(val, str) else val.get("id")
                         if ep_id: return play(f"https://api.atresplayer.com/client/v1/page/episode/{ep_id}")
             except Exception: pass

        if "firstEpisode" in data and isinstance(data["firstEpisode"], dict) and data["firstEpisode"].get("href"):
             if data["firstEpisode"]["href"] != href: return play(data["firstEpisode"]["href"])

        if "episode" in data:
             ep_val = data["episode"]
             target = ep_val if isinstance(ep_val, str) else ep_val.get("href") if isinstance(ep_val, dict) else None
             if target: return play(target)

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

        if not video_url: video_url = _find_key(data, "urlVideo")
        if not video_url and not data.get("sources"):
             sources_found = _find_key(data, "sources")
             if sources_found: data["sources"] = sources_found
        
        if not video_url and not data.get("sources"):
            hero = data.get('hero')
            if not hero and 'components' in data:
                for c in data['components']:
                    if c.get('component') in ['Hero', 'HERO', 'Showcase', 'Header', 'Poster', 'Banner']: hero = c; break
            if hero:
                for action in (hero.get("actions") or hero.get("buttons") or hero.get("links") or []):
                    if action.get("type") == "PLAY" or "reproducir" in str(action.get("label", "")).lower():
                        if action.get("href") and action.get("href") != href: return play(action.get("href"))

        if not video_url and not data.get("sources"):
            candidates = []
            recursive_find_playable(data, candidates)
            if candidates:
                best = next((c for c in candidates if "/player/" in c.get("href", "")), candidates[0])
                if best.get("href") and best.get("href") != href: return play(best.get("href"))

        if video_url and "/player/" in video_url:
            r_player = s.get(video_url, timeout=10)
            r_player.raise_for_status()
            data = r_player.json()
            video_url = None

        def _get_best_source(sources):
            if not sources: return None
            for src in sources:
                if src.get("type") == "application/dash+xml" and src.get("src"): return src.get("src")
            for src in sources:
                if "mpegurl" in str(src.get("type")) and src.get("src"): return src.get("src")
            for src in sources:
                if src.get("src"): return src.get("src")
            return None

        if not video_url: video_url = _get_best_source(data.get("sourcesLive"))
        if not video_url: video_url = _get_best_source(data.get("sources"))

        if not video_url:
             xbmcgui.Dialog().notification("Atresplayer", "No se encontró URL de video")
             return

        li = xbmcgui.ListItem(path=video_url)
        if ".mpd" in video_url or ".m3u8" in video_url:
            li.setProperty('inputstream', 'inputstream.adaptive')
            li.setProperty('inputstream.adaptive.manifest_type', 'mpd' if '.mpd' in video_url else 'hls')
            li.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
            
            # Restaurar headers y cookies para que funcione la reproducción
            headers_dict = {
                'User-Agent': s.headers.get('User-Agent', ''),
                'Origin': s.headers.get('Origin', 'https://www.atresplayer.com'),
                'Referer': s.headers.get('Referer', 'https://www.atresplayer.com/')
            }
            cookie_str = "; ".join([f"{c.name}={c.value}" for c in s.cookies])
            if cookie_str: headers_dict['Cookie'] = cookie_str
            
            headers = "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in headers_dict.items()])
            li.setProperty('inputstream.adaptive.stream_headers', headers)
            li.setProperty('inputstream.adaptive.manifest_headers', headers)
            li.setProperty('inputstream.adaptive.license_headers', headers)
            
        xbmcplugin.setResolvedUrl(_handle, True, li)

    except Exception as e: xbmcgui.Dialog().notification("Error Reproducción", str(e))