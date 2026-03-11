# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import urllib.parse
import time
import os
from resources.lib.db import get_next_episode, load_items_by_keys

# Intentar importar AddonSignals de forma segura
try:
    import AddonSignals
except ImportError:
    try:
        import addon.signals as AddonSignals
    except ImportError:
        AddonSignals = None
        xbmc.log("RusterWolf Service: CRÍTICO - AddonSignals no encontrado. Next Up no funcionará.", xbmc.LOGERROR)

ADDON = xbmcaddon.Addon()

def log(msg):
    xbmc.log(f"RusterWolf Service: {msg}", xbmc.LOGDEBUG)

def get_last_played_from_history():
    """Recupera el último item reproducido del historial si es reciente (< 2 min)."""
    try:
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        hist_file = os.path.join(profile_dir, 'watch_history.json')
        if not os.path.exists(hist_file):
            return None
            
        with open(hist_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
            
        # Buscar el item con el timestamp más reciente
        if not history: return None
        
        # Ordenar por last_played descendente
        items = sorted(history.values(), key=lambda x: x.get('last_played', 0), reverse=True)
        last_item = items[0]
        
        # Verificar si es reciente (menos de 120 segundos)
        if time.time() - last_item.get('last_played', 0) < 120:
            return last_item
            
    except Exception as e:
        log(f"Error leyendo historial: {e}")
    return None

def on_upnext_play_action(data):
    """Callback cuando el usuario pulsa el botón 'Ver ahora' en la notificación."""
    if not data: return
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass
    
    play_url = data.get('play_url') if isinstance(data, dict) else None
    
    if play_url:
        log(f"Botón pulsado. Play URL: {play_url}")
        
        try:
            parsed = urllib.parse.urlparse(play_url)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            key = params.get('key')
            
            if key:
                # 1. Cargar info del item desde DB
                items = load_items_by_keys([key])
                if items:
                    it = items[0]
                    # 2. Elegir el primer torrent disponible (Autoplay)
                    torrents = it.get('torrents', [])
                    magnet = None
                    if torrents:
                        magnet = torrents[0].get('magnet')
                    
                    if magnet:
                        # 3. Construir URL directa de Elementum
                        elementum_url = 'plugin://plugin.video.elementum/play?uri=%s' % urllib.parse.quote_plus(magnet)
                        
                        # 4. Crear ListItem con metadata
                        li = xbmcgui.ListItem(path=elementum_url)
                        
                        tag = li.getVideoInfoTag()
                        tag.setTitle(it.get('episode_title') or f"Episodio {it.get('episode')}")
                        tag.setTvShowTitle(it.get('title'))
                        if it.get('season'): tag.setSeason(int(it['season']))
                        if it.get('episode'): tag.setEpisode(int(it['episode']))
                        tag.setMediaType('episode')
                        tag.setPlot(it.get('episode_overview') or it.get('overview'))
                        
                        art = {}
                        if it.get('poster'): art['poster'] = it['poster']
                        if it.get('fanart'): art['fanart'] = it['fanart']
                        if it.get('still_path'): art['thumb'] = it['still_path']
                        li.setArt(art)
                        
                        # 5. IMPORTANTE: Guardar en historial antes de reproducir para que el siguiente ciclo funcione
                        try:
                            from resources.lib.player import play_with_elementum
                            play_with_elementum(magnet, it)
                        except: pass

                        log(f"Reproduciendo siguiente: {it.get('title')} S{it.get('season')}E{it.get('episode')}")
                        xbmc.Player().play(elementum_url, li)
                        return

            xbmc.executebuiltin(f'PlayMedia("{play_url}")')
            
        except Exception as e:
            log(f"Error en playback action: {e}")
            xbmc.executebuiltin(f'PlayMedia("{play_url}")')

class RusterWolfUpNextPlayer(xbmc.Player):
    def __init__(self):
        super(RusterWolfUpNextPlayer, self).__init__()
        self.upnext_sent = False

    def onAVStarted(self):
        self.upnext_sent = False
        # Esperamos un poco más para dar tiempo a Elementum a establecerse
        xbmc.sleep(3000)
        self.check_and_send_upnext()

    def check_and_send_upnext(self):
        if self.upnext_sent: return
        if not self.isPlayingVideo(): return
        
        # Esperar a que haya duración válida (esencial para que NextUp calcule el tiempo)
        if self.getTotalTime() <= 0:
            # log("Esperando duración válida...") # Demasiado ruido, mejor no loguear esto constantemente
            return

        try:
            # 1. Intentar obtener datos del player (Tags)
            tag = self.getVideoInfoTag()
            
            # CORRECCIÓN: El método correcto es getTVShowTitle (TV en mayúsculas)
            try:
                tvshowtitle = tag.getTVShowTitle()
            except AttributeError:
                tvshowtitle = ''
            
            title_tag = tag.getTitle()
            try: season = int(tag.getSeason())
            except: season = 0
            try: episode = int(tag.getEpisode())
            except: episode = 0
            
            # 2. Si falla (Elementum a veces limpia los tags), usar FALLBACK del historial
            if not tvshowtitle or season <= 0:
                hist_item = get_last_played_from_history()
                if hist_item:
                    tvshowtitle = hist_item.get('title')
                    season = int(hist_item.get('season') or 0)
                    episode = int(hist_item.get('episode') or 0)

            # Validar que tenemos lo mínimo necesario
            if not tvshowtitle or season <= 0:
                return
            
            # Buscar siguiente en DB
            next_ep = get_next_episode(tvshowtitle, season, episode)
            
            if next_ep:
                next_title = next_ep.get('episode_title') or f"Episodio {next_ep['episode']}"
                next_key = next_ep.get('key')
                play_url = f"plugin://plugin.video.rusterwolf77/?action=play_next&key={urllib.parse.quote(next_key)}"
                
                # Crear ID numérico único para la serie basado en el nombre
                show_id = abs(hash(tvshowtitle)) % 100000
                
                payload = {
                    "addon_id": "plugin.video.rusterwolf77",
                    "current_episode": {
                        "episodeid": int(season) * 10000 + int(episode),
                        "tvshowid": show_id,
                        "tvshowtitle": tvshowtitle,
                        "season": int(season),
                        "episode": int(episode)
                    },
                    "next_episode": {
                        "episodeid": int(next_ep['season']) * 10000 + int(next_ep['episode']),
                        "tvshowid": show_id,
                        "tvshowtitle": next_ep['title'],
                        "season": int(next_ep['season']),
                        "episode": int(next_ep['episode']),
                        "title": next_title,
                        "plot": next_ep.get('episode_overview') or next_ep.get('overview', ''),
                        "art": {
                            "tvshow.poster": next_ep.get('poster', ''),
                            "thumb": next_ep.get('still_path') or next_ep.get('poster', ''),
                            "tvshow.fanart": next_ep.get('fanart', ''),
                            "tvshow.landscape": next_ep.get('fanart', '')
                        }
                    },
                    "play_info": {
                        "play_url": play_url
                    }
                }
                
                log(f"Enviando señal UpNext: {tvshowtitle} -> {next_title}")
                if AddonSignals:
                    AddonSignals.sendSignal('upnext_data', payload)
                self.upnext_sent = True
                
        except Exception as e:
            log(f"Error checking UpNext: {e}")

if __name__ == '__main__':
    log("Service iniciado")
    if AddonSignals:
        AddonSignals.registerSlot('upnextprovider', 'plugin.video.rusterwolf77_play_action', on_upnext_play_action)
        AddonSignals.registerSlot('service.upnext', 'plugin.video.rusterwolf77_play_action', on_upnext_play_action)
    
    monitor = xbmc.Monitor()
    player = RusterWolfUpNextPlayer()
    
    while not monitor.abortRequested():
        # Bucle de vigilancia
        if player.isPlayingVideo() and not player.upnext_sent:
             # Comprobar cada 5 segundos si ya tenemos duración y metadatos
             if monitor.waitForAbort(5): break
             player.check_and_send_upnext()
        else:
             if monitor.waitForAbort(5): break
