# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import os
from resources.lib.services import alldebrid, realdebrid
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify


def resolve_for_playback(params):
    """
    Resuelve el enlace y devuelve (stream_url, listitem) para uso interno o externo.
    """
    url_1fichier = params.get('url')
    title = params.get('title', 'Video')
    tvshowtitle = params.get('tvshowtitle')
    season = params.get('season')
    episode = params.get('episode')
    tmdb_id = params.get('tmdb')
    
    if not url_1fichier:
        notify('Choloretro', 'Enlace no encontrado', 3000)
        return None, None

    # Notificar al usuario que estamos resolviendo
    notify('Choloretro', 'Resolviendo enlace...', 2000)

    # 1. Intentar desbloquear con AllDebrid
    stream_url = alldebrid.unlock_link(url_1fichier)
    
    # 2. Si falla o no hay cuenta AD, intentar con Real-Debrid
    if not stream_url:
        stream_url = realdebrid.unlock_link(url_1fichier)
    
    if stream_url:
        log("Player: Reproduciendo (URL oculto)")
        li = xbmcgui.ListItem(path=stream_url)
        
        # Compatibilidad con Kodi 20+ (InfoTag) para evitar warnings y asegurar lectura correcta
        tag = li.getVideoInfoTag()
        tag.setTitle(title)
        if tvshowtitle:
            tag.setTvShowTitle(tvshowtitle)
            tag.setMediaType('episode')
        if season:
            tag.setSeason(int(season))
        if episode:
            tag.setEpisode(int(episode))
        
        return stream_url, li
    
    return None, None


def play_item(handle, params):
    """
    Función principal llamada por el Router de Kodi (main.py).
    """
    log(f"Player: Solicitud de reproducción recibida. Params: {params}")
    
    stream_url, li = resolve_for_playback(params)
    
    if stream_url and li:
        log("Player: Reproduciendo (URL oculto)")
        # Es importante setResolvedUrl para addons que listan items 'isPlayable=True'
        xbmcplugin.setResolvedUrl(handle, True, li)
    else:
        # Si falla, cancelamos la reproducción
        li = xbmcgui.ListItem()
        xbmcplugin.setResolvedUrl(handle, False, li)