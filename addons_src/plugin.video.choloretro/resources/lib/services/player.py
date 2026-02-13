# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import os
from resources.lib.services import alldebrid
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify


def play_item(handle, params):
    """
    Resuelve el enlace final y lo envía a Kodi.
    params debe contener 'url' (el enlace de 1fichier) y metadatos opcionales.
    """
    url_1fichier = params.get('url')
    title = params.get('title', 'Video')
    
    if not url_1fichier:
        notify('Choloretro', 'Enlace no encontrado', 3000)
        return

    # Notificar al usuario que estamos resolviendo
    notify('Choloretro', 'Resolviendo enlace...', 2000)

    # Desbloquear con AllDebrid
    stream_url = alldebrid.unlock_link(url_1fichier)
    
    if stream_url:
        log("Player: Reproduciendo (URL oculto)")
        li = xbmcgui.ListItem(path=stream_url)
        
        # Establecer metadatos básicos para el reproductor
        li.setInfo('video', {'title': title})
        
        # Es importante setResolvedUrl para addons que listan items 'isPlayable=True'
        xbmcplugin.setResolvedUrl(handle, True, li)
    else:
        # Si falla, cancelamos la reproducción
        li = xbmcgui.ListItem()
        xbmcplugin.setResolvedUrl(handle, False, li)