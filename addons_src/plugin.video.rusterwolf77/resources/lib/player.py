
import xbmc, xbmcaddon, xbmcvfs, urllib.parse, os, time, json

ADDON = xbmcaddon.Addon()

def is_elementum_installed():
    try:
        xbmcaddon.Addon('plugin.video.elementum')
        return True
    except Exception:
        return False

def play_with_elementum(torrent_url, item_info=None):
    """
    Reproduce un torrent con Elementum y guarda el historial.
    
    Args:
        torrent_url: string con el magnet link
        item_info: dict con información del item (title, type, year, season, episode, key)
    """
    # No lanzar Elementum desde aquí: la reproducción la resuelve el flujo
    # principal (setResolvedUrl). Esta función solo debe guardar el historial
    # y no iniciar otra petición /play que provoque duplicados.
    uri = urllib.parse.quote_plus(torrent_url)
    
    # Solo guardar historial si tenemos información del item
    if not item_info or not isinstance(item_info, dict):
        return
    
    # Guardar en historial de reproducción (operación atómica y con logs)
    xbmc.log('RusterWolf: history thread start', xbmc.LOGDEBUG)
    try:
        # Obtener el directorio de perfil del addon de forma robusta
        # ADDON.getAddonInfo('profile') devuelve 'special://profile/addon_data/<id>'
        profile_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        os.makedirs(profile_dir, exist_ok=True)
        watch_history_file = os.path.join(profile_dir, 'watch_history.json')
        tmp_file = watch_history_file + '.tmp'
        
        # Cargar historial existente
        watch_history = {}
        if os.path.exists(watch_history_file):
            try:
                with open(watch_history_file, 'r', encoding='utf-8') as f:
                    watch_history = json.load(f) or {}
            except Exception:
                watch_history = {}
        
        # Crear key única para este item
        key = item_info.get('key')
        if not key:
            if item_info.get('type') == 'movie':
                key = f"movie_{item_info.get('title', '')}_{item_info.get('year', '')}"
            else:
                key = f"tv_{item_info.get('title', '')}_{item_info.get('season', '')}_{item_info.get('episode', '')}"
        
        # Guardar información básica
        watch_history[key] = {
            'key': key,
            'title': item_info.get('title', ''),
            'type': item_info.get('type', ''),
            'year': item_info.get('year', ''),
            'season': item_info.get('season'),
            'episode': item_info.get('episode'),
            'last_played': time.time(),
            'position': 0,  # Se actualizará cuando el player termine
            'total': 0
        }

        # Escritura atómica: escribir en fichero temporal y renombrar
        try:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(watch_history, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, watch_history_file)
        except Exception:
            # Fallback: intentar con xbmcvfs (algunas plataformas requieren VFS)
            try:
                data = json.dumps(watch_history, ensure_ascii=False, indent=2)
                vf = xbmcvfs.File(tmp_file, 'w')
                vf.write(data.encode('utf-8'))
                vf.close()
                xbmcvfs.rename(tmp_file, watch_history_file)
            except Exception as e:
                xbmc.log(f"RusterWolf: error guardando historial (write fallback): {e}", xbmc.LOGERROR)

    except Exception as e:
        xbmc.log(f"RusterWolf: error guardando historial: {e}", xbmc.LOGERROR)
    finally:
        xbmc.log('RusterWolf: history thread finished', xbmc.LOGDEBUG)