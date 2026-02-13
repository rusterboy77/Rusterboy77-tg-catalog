# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
from resources.lib.services import alldebrid
from resources.lib.utils.tools import log

def play_item(handle, params):
    """
    Resuelve el enlace final y lo envía a Kodi.
    params debe contener 'url' (el enlace de 1fichier) y metadatos opcionales.
    """
    url_1fichier = params.get('url')
    title = params.get('title', 'Video')
    
    if not url_1fichier:
        xbmcgui.Dialog().notification('Choloretro', 'Enlace no encontrado', xbmcgui.NOTIFICATION_ERROR)
        return

    # Notificar al usuario que estamos resolviendo
    xbmcgui.Dialog().notification('Choloretro', 'Resolviendo enlace...', xbmcgui.NOTIFICATION_INFO, 2000)

    # Desbloquear con AllDebrid
    stream_url = alldebrid.unlock_link(url_1fichier)
    
    if stream_url:
        log(f"Player: Reproduciendo {stream_url}")
        li = xbmcgui.ListItem(path=stream_url)
        
        # Establecer metadatos básicos para el reproductor
        li.setInfo('video', {'title': title})
        
        # Es importante setResolvedUrl para addons que listan items 'isPlayable=True'
        xbmcplugin.setResolvedUrl(handle, True, li)
    else:
        # Si falla, cancelamos la reproducción
        li = xbmcgui.ListItem()
        xbmcplugin.setResolvedUrl(handle, False, li)