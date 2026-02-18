# -*- coding: utf-8 -*-
from resources.lib.gui import home, listings
from resources.lib.services import player, alldebrid, realdebrid
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
        
        # --- Películas ---
        elif action == 'list_movies':
            listings.show_movies(self.base_url, self.handle, params)
        elif action == 'list_all_movies':
            listings.list_all_movies(self.base_url, self.handle, params)
        elif action == 'list_movies_by_title':
            listings.show_movies_by_title(self.base_url, self.handle, params)
        elif action == 'list_movies_by_letter':
            listings.list_movies_by_letter(self.base_url, self.handle, params)
        elif action == 'list_movies_by_genre':
            listings.show_movies_by_genre(self.base_url, self.handle, params)
        elif action == 'list_movies_by_genre_filter':
            listings.list_movies_by_genre_filter(self.base_url, self.handle, params)
        elif action == 'list_movies_by_year':
            listings.show_movies_by_year(self.base_url, self.handle, params)
        elif action == 'list_movies_by_year_filter':
            listings.list_movies_by_year_filter(self.base_url, self.handle, params)
        elif action == 'show_collections':
            listings.show_collections(self.base_url, self.handle, params)
        elif action == 'list_collection_items':
            listings.list_collection_items(self.base_url, self.handle, params)
        elif action == 'list_sagas':
            listings.list_sagas(self.base_url, self.handle, params)
        elif action == 'list_saga_items':
            listings.list_saga_items(self.base_url, self.handle, params)
        
        # --- Series ---
        elif action == 'list_tvshows':
            listings.show_tvshows(self.base_url, self.handle, params)
        elif action == 'list_all_tvshows':
            listings.list_all_tvshows(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_title':
            listings.show_tvshows_by_title(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_letter':
            listings.list_tvshows_by_letter(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_genre':
            listings.show_tvshows_by_genre(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_genre_filter':
            listings.list_tvshows_by_genre_filter(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_year':
            listings.show_tvshows_by_year(self.base_url, self.handle, params)
        elif action == 'list_tvshows_by_year_filter':
            listings.list_tvshows_by_year_filter(self.base_url, self.handle, params)
        
        elif action == 'list_seasons':
            listings.show_seasons(self.base_url, self.handle, params)
        elif action == 'list_episodes':
            listings.show_episodes(self.base_url, self.handle, params)
        
        # --- Dibujos (Animación) ---
        elif action == 'show_animated':
            listings.show_animated(self.base_url, self.handle, params)
        elif action == 'list_animated_movies':
            listings.show_animated_movies(self.base_url, self.handle, params)
        elif action == 'list_animated_tvshows':
            listings.show_animated_tvshows(self.base_url, self.handle, params)
        
        # --- Seguir viendo ---
        elif action == 'show_continue_watching':
            listings.show_continue_watching(self.base_url, self.handle, params)
        
        # --- Búsqueda ---
        elif action == 'search':
            listings.show_search(self.base_url, self.handle, params)
        
        # --- AllDebrid Auth ---
        elif action == 'auth_alldebrid':
            alldebrid.authenticate_with_pin()
            import xbmc
            xbmc.executebuiltin('Addon.OpenSettings(plugin.video.choloretro)')
        
        # --- Real-Debrid Auth ---
        elif action == 'auth_realdebrid':
            realdebrid.authenticate_with_pin()
            import xbmc
            xbmc.executebuiltin('Addon.OpenSettings(plugin.video.choloretro)')
        
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