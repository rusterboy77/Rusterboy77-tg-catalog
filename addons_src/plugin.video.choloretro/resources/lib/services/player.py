# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import os
import json
import xbmcaddon
from resources.lib.database import get_item_by_key
from resources.lib.services import alldebrid, realdebrid
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify


def resolve_for_playback(params):
    """
    Resuelve el enlace y devuelve (stream_url, listitem) para uso interno o externo.
    """
    item_key = params.get('key')
    title = params.get('title', 'Video')
    tvshowtitle = params.get('tvshowtitle')
    season = params.get('season')
    episode = params.get('episode')
    tmdb_id = params.get('tmdb')
    
    if not item_key:
        notify('Choloretro', 'Clave de enlace no encontrada', 3000)
        return None, None

    item = get_item_by_key(item_key)
    if not item or not item.get('links'):
        notify('Choloretro', 'Enlace no encontrado en la base de datos', 3000)
        return None, None

    try:
        links = json.loads(item['links'])
        url_1fichier = links[0]['url'] if links else None
    except Exception:
        url_1fichier = None

    if not url_1fichier:
        notify('Choloretro', 'Enlace no válido', 3000)
        return None, None

    # Validar que existe al menos una cuenta Debrid configurada antes de hacer las llamadas
    addon = xbmcaddon.Addon()
    ad_key = addon.getSetting('alldebrid_apikey')
    rd_token = addon.getSetting('realdebrid_token')

    if not ad_key and not rd_token:
        notify('Choloretro', 'Configura una cuenta Debrid en Ajustes', 4000)
        return None, None

    # Notificar al usuario que estamos resolviendo
    notify('Choloretro', 'Resolviendo enlace...', 2000)

    stream_url = None
    if ad_key:
        stream_url = alldebrid.unlock_link(url_1fichier)
    
    if not stream_url and rd_token:
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
        
        # Marcador para que el servicio Up Next sepa que es una reproducción nuestra
        xbmcgui.Window(10000).setProperty('Choloretro_Playing', 'true')
        
        return stream_url, li
    
    return None, None


def play_item(handle, params):
    """
    Función principal llamada por el Router de Kodi (main.py).
    """
    log(f"Player: Solicitud de reproducción recibida. Params: {params}")
    
    try:
        stream_url, li = resolve_for_playback(params)
        
        if stream_url and li:
            log("Player: Reproduciendo (URL oculto)")
            xbmcplugin.setResolvedUrl(handle, True, li)
        else:
            # Si falla limpiamente, cancelamos la reproducción
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
    except Exception as e:
        log(f"Player: Error Crítico durante la resolución: {e}")
        notify('Choloretro', 'Error interno al reproducir', 3000)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())