# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import json
import time
from resources.lib.database import get_episodes
from resources.lib.utils.tools import log

class UpNextMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.playing_file = None
        self.upnext_signal_sent = False

    def onNotification(self, sender, method, data):
        # Método opcional si quieres reaccionar a eventos específicos
        pass

def get_next_episode_info(tvshowtitle, season, episode):
    """Busca el siguiente episodio en la base de datos local."""
    try:
        # 1. Buscar episodios de la misma temporada
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
        
        # 2. Si no hay siguiente en esta temporada, buscar el primero de la siguiente (opcional, simplificado aquí)
        # Para simplificar, este código busca el siguiente en la misma temporada.
        
        if next_ep:
            # Construir URL de reproducción para el siguiente
            links = json.loads(next_ep['links']) if next_ep.get('links') else []
            if not links:
                return None
                
            url_link = links[0]['url']
            
            # Construir plugin URL
            from urllib.parse import urlencode
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
        log(f"Service UpNext Error: {e}")
    
    return None

def check_and_send_upnext():
    player = xbmc.Player()
    if not player.isPlayingVideo():
        return False

    try:
        tag = player.getVideoInfoTag()
        tvshowtitle = tag.getTVShowTitle()
        season = tag.getSeason()
        episode = tag.getEpisode()
        
        # Verificar que estamos viendo una serie y que tenemos datos
        if not tvshowtitle or season == -1 or episode == -1:
            return False
            
        # Verificar duración para no disparar al inicio
        duration = player.getTotalTime()
        current_time = player.getTime()
        
        # Lógica: Buscar siguiente episodio solo si estamos reproduciendo
        # y aún no hemos enviado la señal
        next_info = get_next_episode_info(tvshowtitle, season, episode)
        
        if next_info:
            # Preparar payload para Up Next
            payload = {
                "current_episode": {
                    "tvshowtitle": tvshowtitle,
                    "season": season,
                    "episode": episode
                },
                "next_episode": {
                    "episodeid": 0, # Dummy ID
                    "tvshowtitle": next_info['tvshowtitle'],
                    "season": next_info['season'],
                    "episode": next_info['episode'],
                    "title": next_info['title'],
                    "thumb": next_info['thumb'],
                    "fanart": next_info['fanart'],
                    "plot": next_info['plot'],
                    "play_url": next_info['play_url']
                }
            }
            # Enviar señal a service.upnext
            xbmc.executebuiltin(f'RunScript(service.upnext, data={json.dumps(json.dumps(payload))})')
            return True
            
    except Exception as e:
        log(f"Service Check Error: {e}")
    
    return False

if __name__ == '__main__':
    monitor = UpNextMonitor()
    log("Choloretro Service: Iniciado")
    
    while not monitor.abortRequested():
        # Comprobar cada 10 segundos si hay video reproduciéndose
        if xbmc.Player().isPlayingVideo():
            # Si está reproduciendo, comprobamos si necesitamos enviar UpNext
            # Solo lo enviamos una vez cerca del final, pero UpNext gestiona el tiempo,
            # nosotros solo le damos los datos. Lo ideal es enviarlo al principio/medio.
            
            # Para simplificar, intentamos enviar los datos una vez detectamos la serie
            # Up Next se encarga de mostrarlo al final.
            # Usamos una bandera en el monitor para no spamear
            if not monitor.upnext_signal_sent:
                if check_and_send_upnext():
                    monitor.upnext_signal_sent = True
        else:
            monitor.upnext_signal_sent = False
            
        if monitor.waitForAbort(10):
            break