# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import os
from resources.lib.services import alldebrid, realdebrid
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify


def play_item(handle, params):
    """
    Resuelve el enlace final y lo envía a Kodi.
    params debe contener 'url' (el enlace de 1fichier) y metadatos opcionales.
    """
    url_1fichier = params.get('url')
    title = params.get('title', 'Video')
    tvshowtitle = params.get('tvshowtitle')
    season = params.get('season')
    episode = params.get('episode')
    tmdb_id = params.get('tmdb')
    
    if not url_1fichier:
        notify('Choloretro', 'Enlace no encontrado', 3000)
        return

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
        
        # Establecer metadatos básicos para el reproductor
        info = {'title': title}
        if tvshowtitle:
            info['tvshowtitle'] = tvshowtitle
            info['mediatype'] = 'episode'
        if season:
            info['season'] = int(season)
        if episode:
            info['episode'] = int(episode)
        
        li.setInfo('video', info)
        
        # Es importante setResolvedUrl para addons que listan items 'isPlayable=True'
        xbmcplugin.setResolvedUrl(handle, True, li)
    else:
        # Si falla, cancelamos la reproducción
        li = xbmcgui.ListItem()
        xbmcplugin.setResolvedUrl(handle, False, li)