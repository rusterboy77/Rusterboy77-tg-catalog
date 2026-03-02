# -*- coding: utf-8 -*-
import xbmcgui
import xbmcplugin
import xbmcaddon
import os
from urllib.parse import urlencode

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
FANART = os.path.join(ADDON_PATH, 'resources', 'media', 'fanart.jpeg')
ICON = os.path.join(ADDON_PATH, 'resources', 'media', 'icon.png')

def build_url(base_url, query):
    return base_url + '?' + urlencode(query)

def show_main_menu(base_url, handle):
    ADDON = xbmcaddon.Addon()
    ADDON_PATH = ADDON.getAddonInfo('path')
    FANART = os.path.join(ADDON_PATH, 'fanart.jpg')
    ICON = os.path.join(ADDON_PATH, 'icon.png')
    
    xbmcplugin.setContent(handle, 'files')
    
    menu_items = [
        ('Películas', {'action': 'list_movies'}, 'peliculas.png'),
        ('Series', {'action': 'list_tvshows'}, 'series.png'),
        ('Dibujos', {'action': 'show_animated'}, 'dibujos.png'),
        ('Anime', {'action': 'show_anime'}, 'anime.png'),
        ('Seguir viendo', {'action': 'show_continue_watching'}, 'seguir_viendo.png'),
        ('Buscador', {'action': 'search'}, 'buscador.png'),
        ('Ajustes', {'action': 'settings'}, 'ajustes.png'),
    ]

    for title, params, icon_name in menu_items:
        li = xbmcgui.ListItem(label=title)
        icon_path = os.path.join(ADDON_PATH, 'resources', 'media', icon_name)
        li.setArt({'icon': icon_path, 'fanart': FANART})
        
        # InfoTag para Kodi 19+
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(title)
        
        url = build_url(base_url, params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)