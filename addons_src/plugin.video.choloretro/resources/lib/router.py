# -*- coding: utf-8 -*-
from resources.lib.gui import home, listings
from resources.lib.services import player
from resources.lib.utils.tools import log
import xbmcplugin

class Router:
    def __init__(self, base_url, handle):
        self.base_url = base_url
        self.handle = handle

    def dispatch(self, params):
        action = params.get('action')

        # --- Menú Principal ---
        if not action:
            home.show_main_menu(self.base_url, self.handle)
        
        # --- Listados ---
        elif action == 'list_movies':
            listings.show_movies(self.base_url, self.handle, params)
        elif action == 'list_tvshows':
            listings.show_tvshows(self.base_url, self.handle, params)
        elif action == 'list_seasons':
            listings.show_seasons(self.base_url, self.handle, params)
        elif action == 'list_episodes':
            listings.show_episodes(self.base_url, self.handle, params)
        
        # --- Reproducción ---
        elif action == 'play':
            # Aquí es donde la magia de AllDebrid ocurrirá
            player.play_item(self.handle, params)
            
        # --- Ajustes ---
        elif action == 'settings':
            import xbmc
            xbmc.executebuiltin('Addon.OpenSettings(plugin.video.choloretro)')
            
        else:
            log(f"Router: Acción desconocida {action}")
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)