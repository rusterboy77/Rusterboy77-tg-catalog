# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import json
from urllib.parse import urlencode, urlparse, parse_qs
from resources.lib.database import get_episodes
from resources.lib.utils.tools import log
from resources.lib.services.player import resolve_for_playback

# IMPORTACIÓN GLOBAL Y ÚNICA
try:
    import AddonSignals
except ImportError:
    try:
        import addon.signals as AddonSignals
    except ImportError:
        log("Service: ERROR CRÍTICO - No se pudo importar AddonSignals. El botón no funcionará.")

# Función que recibe el "PONG" de Up Next
def on_upnext_play_action(data):
    
    # Intento de parseo si llega como string (caso raro)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            pass
            
    # Aseguramos que data sea un diccionario antes de usar .get()
    play_url = data.get('play_url') if isinstance(data, dict) else None
    
    if play_url:
        log("Service UpNext: Botón pulsado. Resolviendo enlace...")
        
        try:
            # 1. Extraer parámetros de la URL del plugin
            parsed = urlparse(play_url)
            params_list = parse_qs(parsed.query)
            # Aplanar lista (parse_qs devuelve listas)
            params = {k: v[0] for k, v in params_list.items()}
            
            # 2. Resolver el enlace SIN cortar la reproducción actual
            stream_url, li = resolve_for_playback(params)
            
            if stream_url and li:
                log("Service UpNext: Enlace resuelto. Transición directa.")
                # 3. Reproducir directamente (Seamless switch)
                xbmc.Player().play(stream_url, li)
            else:
                log("Service UpNext: Fallo en resolución directa. Usando fallback.")
                xbmc.executebuiltin(f'PlayMedia("{play_url}")')
                
        except Exception as e:
            log(f"Service UpNext: Error en transición directa: {e}. Usando fallback.")
            xbmc.executebuiltin(f'PlayMedia("{play_url}")')
    else:
        log("Service UpNext: ERROR - La señal llegó pero no contenía 'play_url'")


def get_next_episode_info(tvshowtitle, season, episode):
    try:
        episodes = get_episodes(tvshowtitle, season)
        current_ep_num = int(episode)
        
        next_ep = None
        for ep in episodes:
            try:
                if int(ep['episode']) == current_ep_num + 1:
                    next_ep = ep
                    break
            except:
                continue
        
        if next_ep:
            links = json.loads(next_ep['links']) if next_ep.get('links') else []
            if not links:
                return None
                
            url_link = links[0]['url']
            
            base_url = "plugin://plugin.video.choloretro/"
            params = {
                'action': 'play',
                'title': f"{tvshowtitle} S{next_ep['season']}E{next_ep['episode']}",
                'url': url_link,
                'tvshowtitle': tvshowtitle,
                'season': next_ep['season'],
                'episode': next_ep['episode'],
                'tmdb': next_ep.get('tmdb_id')
            }
            play_url = base_url + "?" + urlencode(params)
            
            return {
                'title': next_ep.get('title', f'Episodio {next_ep["episode"]}'),
                'tvshowtitle': tvshowtitle,
                'season': next_ep['season'],
                'episode': next_ep['episode'],
                'rating': next_ep.get('rating'),
                'plot': next_ep.get('overview'),
                'thumb': next_ep.get('still_path') or next_ep.get('poster'),
                'fanart': next_ep.get('fanart'),
                'play_url': play_url
            }
    except Exception as e:
        log(f"Service UpNext Error en DB: {e}")
    
    return None


class CholoretroUpNextPlayer(xbmc.Player):
    def __init__(self):
        super(CholoretroUpNextPlayer, self).__init__()
        self.upnext_sent = False

    def onPlayBackStopped(self):
        xbmcgui.Window(10000).clearProperty('Choloretro_Playing')

    def onPlayBackEnded(self):
        xbmcgui.Window(10000).clearProperty('Choloretro_Playing')

    def onAVStarted(self):
        self.upnext_sent = False
        self.check_and_send_upnext()

    def check_and_send_upnext(self):
        # 1. Comprobar que la reproducción la inició nuestro addon
        if xbmcgui.Window(10000).getProperty('Choloretro_Playing') != 'true':
            return
            
        # 2. Doble validación: descartar archivos locales de biblioteca (nuestro addon usa HTTP/HTTPS por el debrid)
        try:
            if not self.getPlayingFile().startswith('http'):
                return
        except:
            pass

        # Bucle de espera
        for _ in range(30):
            if not self.isPlayingVideo():
                return
            if self.getTotalTime() > 0:
                break
            xbmc.sleep(500)
            
        if self.getTotalTime() <= 0:
            log("Service UpNext: Abortado. Duración 0.")
            return

        try:
            tag = self.getVideoInfoTag()
            tvshowtitle = tag.getTVShowTitle()
            season = tag.getSeason()
            episode = tag.getEpisode()
            
            if not tvshowtitle or int(season) <= 0 or int(episode) <= 0:
                return
                
            log(f"Service UpNext: Detectado -> {tvshowtitle} S{season}E{episode}")
            next_info = get_next_episode_info(tvshowtitle, season, episode)
            
            if next_info:
                plot = next_info.get('plot', '')
                if plot and len(plot) > 80:
                    plot = plot[:77] + "..."
                    
                payload = {
                    "addon_id": "plugin.video.choloretro",
                    "current_episode": {
                        "episodeid": int(season) * 10000 + int(episode),
                        "tvshowid": 1,
                        "tvshowtitle": tvshowtitle,
                        "season": season,
                        "episode": episode
                    },
                    "next_episode": {
                        "episodeid": int(next_info['season']) * 10000 + int(next_info['episode']),
                        "tvshowid": 1,
                        "tvshowtitle": next_info['tvshowtitle'],
                        "season": int(next_info['season']),
                        "episode": int(next_info['episode']),
                        "title": next_info['title'],
                        "plot": plot,
                        "art": {
                            "tvshow.poster": next_info.get('thumb', ''),
                            "thumb": next_info.get('thumb', ''),
                            "tvshow.fanart": next_info.get('fanart', ''),
                            "tvshow.clearlogo": "",
                            "tvshow.landscape": ""
                        }
                    },
                    "play_info": {
                        "play_url": next_info['play_url']
                    }
                }
                
                log(f"Service UpNext: Enviando señal para {next_info['title']}")
                AddonSignals.sendSignal('upnext_data', payload)
                self.upnext_sent = True
            else:
                log("Service UpNext: No hay siguiente episodio en DB.")
                
        except Exception as e:
            log(f"Service Check Error: {type(e).__name__} - {str(e)}")


if __name__ == '__main__':
    log("Choloretro Service: Iniciado")

    # Registramos slots para múltiples variantes de ID del addon UpNext para asegurar compatibilidad
    try:
        # SEGÚN EL LOG: Sender: 'upnextprovider.SIGNAL' | Method: 'Other.plugin.video.choloretro_play_action'
        # Esto significa que debemos escuchar en 'upnextprovider' la señal 'plugin.video.choloretro_play_action'
        AddonSignals.registerSlot('upnextprovider', 'plugin.video.choloretro_play_action', on_upnext_play_action)
        
        # Mantenemos otros IDs por compatibilidad
        AddonSignals.registerSlot('service.upnext', 'plugin.video.choloretro_play_action', on_upnext_play_action)
        AddonSignals.registerSlot('script.service.upnext', 'plugin.video.choloretro_play_action', on_upnext_play_action)
    except Exception as e:
        log(f"Choloretro Service: Error registrando slots de AddonSignals: {e}")
    
    player_monitor = CholoretroUpNextPlayer()
    monitor = xbmc.Monitor()
    
    while not monitor.abortRequested():
        monitor.waitForAbort(1)