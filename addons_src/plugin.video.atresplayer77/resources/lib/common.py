# -*- coding: utf-8 -*-
import sys
import os
import urllib.parse
import xbmcaddon

# Contexto global del Addon
_url = sys.argv[0]
_handle = int(sys.argv[1])
addon = xbmcaddon.Addon()

def get_url(**kwargs):
    """Ayuda para crear URLs internas del addon"""
    return '{0}?{1}'.format(_url, urllib.parse.urlencode(kwargs))

def get_icon(name, default='DefaultFolder.png'):
    """Busca iconos personalizados en resources/media"""
    icon_path = os.path.join(addon.getAddonInfo('path'), 'resources', 'media', name)
    if os.path.exists(icon_path): return icon_path
    return default

def fix_img(url, type='vertical'):
    """Arregla las URLs de imágenes de Atresplayer"""
    if not url: return ""
    # A veces vienen sin esquema
    if url.startswith("//"): return "https:" + url
    if url.startswith("/"): return "https://www.atresplayer.com" + url
    # Si la URL es un directorio, añadir un tamaño de imagen estándar.
    if url.endswith('/'):
        if type == 'horizontal':
            return url + '1280x720.jpg' # Fanart HD
        else:
            return url + '390x219.jpg' # Poster vertical
    return url

def recursive_find_playable(data, results):
    """Busca recursivamente cualquier objeto que parezca un enlace de reproducción"""
    if isinstance(data, dict):
        href = data.get("href")
        type_ = data.get("type")
        label = str(data.get("label", "")).lower()
        is_play_btn = type_ == "PLAY" or "reproducir" in label or "ver ahora" in label or "ver la película" in label or label == "ver"
        is_video_link = href and ("/t/" in href or "/player/" in href or "/page/episode/" in href or "/episode/" in href)
        if href and (is_play_btn or is_video_link):
             if not any(r.get("href") == href for r in results):
                results.append(data)
        for v in data.values(): recursive_find_playable(v, results)
    elif isinstance(data, list):
        for item in data: recursive_find_playable(item, results)