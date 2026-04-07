# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import urllib.parse
import time
import os
from resources.lib.db import get_next_episode
import zlib

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
    try:
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        hist_file = os.path.join(profile_dir, 'watch_history.json')
        
        if not xbmcvfs.exists(hist_file):
            return None
            
        history = None
        try:
            with open(hist_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            try:
                vf = xbmcvfs.File(hist_file, 'r')
                data = vf.read()
                vf.close()
                history = json.loads(data)
            except Exception:
                pass
            
        if not history: return None
        
        items = sorted(history.values(), key=lambda x: x.get('last_played', 0), reverse=True)
        last_item = items[0]
        
        if time.time() - last_item.get('last_played', 0) < 1200:
            return last_item
            
    except Exception as e:
        log(f"Error leyendo historial: {e}")
    return None

def on_upnext_play_action(data):
    if not data: return
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass
    
    play_url = data.get('play_url') if isinstance(data, dict) else None
    
    if play_url:
        log(f"Botón pulsado. Play URL: {play_url}")
        xbmc.executebuiltin(f'PlayMedia("{play_url}")')

class RusterWolfUpNextPlayer(xbmc.Player):
    def __init__(self):
        super(RusterWolfUpNextPlayer, self).__init__()
        self.upnext_sent = False

    def onPlayBackStopped(self):
        self._handle_playback_end(stopped=True)

    def onPlayBackEnded(self):
        self._handle_playback_end(stopped=False)
        
    def _handle_playback_end(self, stopped):
        if xbmcgui.Window(10000).getProperty('Rusterwolf_Playing') != 'true': return
        
        key = xbmcgui.Window(10000).getProperty('Rusterwolf_Playing_Key')
        if not key: return
        
        xbmcgui.Window(10000).clearProperty('Rusterwolf_Playing')
        xbmcgui.Window(10000).clearProperty('Rusterwolf_Playing_Key')

    def onAVStarted(self):
        self.upnext_sent = False
        xbmc.sleep(3000)
        self.check_and_send_upnext()

    def check_and_send_upnext(self):
        if self.upnext_sent: return
        if not self.isPlayingVideo(): return
        
        if xbmcgui.Window(10000).getProperty('Rusterwolf_Playing') != 'true':
            return
            
        try:
            playing_file = self.getPlayingFile()
            if not (playing_file.startswith('http') or playing_file.startswith('plugin')):
                return
        except:
            pass

        if self.getTotalTime() <= 0:
            
            return

        try:
            
            tag = self.getVideoInfoTag()
            
            try:
                tvshowtitle = tag.getTVShowTitle()
            except AttributeError:
                tvshowtitle = ''
            
            title_tag = tag.getTitle()
            try: season = int(tag.getSeason())
            except: season = 0
            try: episode = int(tag.getEpisode())
            except: episode = 0
            
            
            if not tvshowtitle or season <= 0:
                hist_item = get_last_played_from_history()
                if hist_item:
                    tvshowtitle = hist_item.get('title')
                    season = int(hist_item.get('season') or 0)
                    episode = int(hist_item.get('episode') or 0)

            
            if not tvshowtitle or season <= 0:
                return
            
            
            next_ep = get_next_episode(tvshowtitle, season, episode)
            
            if next_ep:
                next_title = next_ep.get('episode_title') or f"Episodio {next_ep['episode']}"
                next_key = next_ep.get('key')
                play_url = f"plugin://plugin.video.rusterwolf77/?action=select&key={urllib.parse.quote(next_key)}"
                
                show_id = abs(zlib.crc32((tvshowtitle or '').encode('utf-8'))) % 100000
                
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

class RusterWolfMonitor(xbmc.Monitor):
    def onSettingsChanged(self):
        if xbmc.getInfoLabel('Container.PluginName') == 'plugin.video.rusterwolf77':
            xbmc.sleep(200) 
            xbmc.executebuiltin('Container.Refresh')

if __name__ == '__main__':
    log("Service iniciado")
    if AddonSignals:
        AddonSignals.registerSlot('upnextprovider', 'plugin.video.rusterwolf77_play_action', on_upnext_play_action)
        AddonSignals.registerSlot('service.upnext', 'plugin.video.rusterwolf77_play_action', on_upnext_play_action)
    
    monitor = RusterWolfMonitor()
    player = RusterWolfUpNextPlayer()
    
    update_checked = False
    tick_counter = 0
    
    while not monitor.abortRequested():
        if not update_checked:
            try:
                from resources.lib.db import maybe_update_db_from_remote
                log("Iniciando comprobación de BD en segundo plano...")
                maybe_update_db_from_remote(force=False, silent=True)
                update_checked = True
            except Exception as e:
                log(f"Error actualizando DB en background: {e}")
                
        if player.isPlayingVideo() and not player.upnext_sent:
            if monitor.waitForAbort(5): break
            player.check_and_send_upnext()
        else:
            if monitor.waitForAbort(5): break
    pass
