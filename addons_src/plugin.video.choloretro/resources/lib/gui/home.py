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
    xbmcplugin.setContent(handle, 'files')
    
    menu_items = [
        ('Películas', {'action': 'list_movies'}),
        ('Series', {'action': 'list_tvshows'}),
        ('Novedades', {'action': 'list_movies'}), # Podrías crear una acción especifica
        ('Ajustes', {'action': 'settings'}),
    ]

    for title, params in menu_items:
        li = xbmcgui.ListItem(label=title)
        li.setArt({'icon': ICON, 'fanart': FANART})
        
        # InfoTag para Kodi 19+
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(title)
        
        url = build_url(base_url, params)
        xbmcplugin.addDirectoryItem(handle, url, li, True)

    xbmcplugin.setPluginFanart(handle, FANART)
    xbmcplugin.endOfDirectory(handle)