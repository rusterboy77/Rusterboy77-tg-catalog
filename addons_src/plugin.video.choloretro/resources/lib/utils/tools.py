# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

def log(msg, level=xbmc.LOGINFO):
    debug = ADDON.getSetting('debug_logging') == 'true'
    if level == xbmc.LOGDEBUG and not debug:
        return
    
    xbmc.log(f"[{ADDON_ID}] {msg}", level)