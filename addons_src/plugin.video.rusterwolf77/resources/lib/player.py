
import xbmc, xbmcgui, xbmcaddon, xbmcvfs, urllib.parse, os, time, json, base64
try:
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Cipher import AES

ADDON = xbmcaddon.Addon()
ADDON_ICON = ADDON.getAddonInfo('icon')

import requests
import requests.packages.urllib3.util.connection as urllib3_cn
import socket

VALID_VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.m2ts', '.ts', '.mov', '.flv', '.wmv')
VALID_ARCHIVE_EXTS = ('.rar', '.zip', '.iso', '.tar', '.7z', 'part01.rar', 'part1.rar')

def decrypt_url(encrypted_url):
    _s = [104, 84, 104, 56, 117, 82, 110, 76, 53, 98, 88, 56, 80, 90, 67, 54, 84, 99, 51, 116, 52, 54, 110, 86, 68, 70, 102, 66, 112, 66, 54, 84, 106, 119, 51, 113, 97, 122, 81, 84, 104, 112, 101, 120, 112, 103, 56, 98, 76, 100, 105, 109, 101, 118, 78, 72, 106, 53, 118, 74, 82, 48, 110, 80]
    seed = bytes(_s)
    decoded_seed = base64.b64decode(seed)
    iv = decoded_seed[:16]
    key = decoded_seed[16:]
    padding_needed = 4 - (len(encrypted_url) % 4)
    if padding_needed and padding_needed != 4:
        encrypted_url += "=" * padding_needed
    cipher = AES.new(key, AES.MODE_OFB, iv)
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_url)
    return cipher.decrypt(encrypted_bytes).decode('utf-8')


def is_elementum_installed():
    try:
        xbmcaddon.Addon('plugin.video.elementum')
        return True
    except Exception:
        return False

def play_1fichier_with_alldebrid(encrypted_url, api_key):
    agent = "RusterWolf77"
    base_url = "https://api.alldebrid.com/v4.1"
    
    try:
        xbmcgui.Dialog().notification('AllDebrid', 'Resolviendo enlace...', ADDON_ICON)
        
        # 1. Descifrar la URL
        plain_url = decrypt_url(encrypted_url)
        if not plain_url.startswith('http'):
            raise ValueError("La URL descifrada no es válida")

        # 2. Desbloquear con AllDebrid
        url_unlock = f"{base_url}/link/unlock?agent={agent}&apikey={api_key}&link={urllib.parse.quote(plain_url)}"
        res_unlock = requests.get(url_unlock, timeout=15).json()
            
        if res_unlock.get('status') != 'success':
            err_msg = res_unlock.get('error', {}).get('message', 'Error al desbloquear el enlace de AllDebrid')
            xbmcgui.Dialog().ok('AllDebrid - Error', err_msg)
            return None
            
        xbmcgui.Dialog().notification('AllDebrid', '¡Enlace listo!', ADDON_ICON)
        return res_unlock.get('data', {}).get('link')
    except Exception as e:
        xbmcgui.Dialog().ok('AllDebrid', f'Fallo al procesar enlace: {str(e)}')
        xbmc.log(f"RusterWolf AllDebrid Error: {e}", xbmc.LOGERROR)
        return None

def play_with_alldebrid(magnet, api_key):
    """Desbloquea el torrent usando AllDebrid."""
    agent = "RusterWolf77"
    base_url = "https://api.alldebrid.com/v4.1"
    
    try:
        xbmcgui.Dialog().notification('AllDebrid', 'Comprobando caché instantánea...', ADDON_ICON)
        # 1. Subir magnet (Usando POST para evitar errores con enlaces muy largos)
        url_upload = f"{base_url}/magnet/upload?agent={agent}&apikey={api_key}"
        res = requests.post(url_upload, data={'magnets[]': magnet}, timeout=15).json()
            
        if res.get('status') != 'success':
            err_msg = res.get('error', {}).get('message', 'Error subiendo enlace Magnet')
            xbmcgui.Dialog().ok('AllDebrid - Error', err_msg)
            return None
            
        magnet_data = res.get('data', {}).get('magnets', [{}])[0]
        if 'error' in magnet_data:
            err_msg = magnet_data.get('error', {}).get('message', 'Magnet inválido o rechazado')
            xbmcgui.Dialog().ok('AllDebrid - Error', err_msg)
            return None
            
        magnet_id = magnet_data.get('id')
        if not magnet_id:
            xbmcgui.Dialog().ok('AllDebrid - Error', 'Error al obtener ID del torrent')
            return None
        
        # 2. Si no está listo al instante
        if not magnet_data.get('ready'):
            # Borrarlo para no ensuciar la nube
            url_del = f"{base_url}/magnet/delete?agent={agent}&apikey={api_key}&id={magnet_id}"
            requests.get(url_del, timeout=10)
            xbmcgui.Dialog().notification('AllDebrid', 'Torrent no está en caché.', ADDON_ICON)
            return None
            
        # 3. Obtener estado para sacar enlace original
        url_status = f"{base_url}/magnet/status?agent={agent}&apikey={api_key}&id={magnet_id}"
        
        magnet_info = {}
        links = []
        
        # Extrae los enlaces del nuevo formato de árbol de la v4.1
        def _extract_v41_links(nodes):
            ext = []
            for n in nodes:
                if isinstance(n, dict):
                    if 'e' in n and isinstance(n['e'], list):
                        ext.extend(_extract_v41_links(n['e']))
                    elif 'l' in n and n.get('l'):
                        ext.append({'filename': n.get('n', ''), 'size': n.get('s', 0), 'link': n.get('l')})
            return ext
        
        for _ in range(5): # Bucle de espera (hasta 10 segundos)
            res_status = requests.get(url_status, timeout=15).json()
                
            if res_status.get('status') != 'success':
                err_msg = res_status.get('error', {}).get('message', 'Error obteniendo estado')
                xbmcgui.Dialog().ok('AllDebrid - Error', err_msg)
                return None
                
            status_data = res_status.get('data', {}).get('magnets', {})
            
            if isinstance(status_data, list) and status_data:
                magnet_info = status_data[0]
            elif isinstance(status_data, dict):
                # A veces AllDebrid mapea por ID: {"12345": {"id": 12345, "links": [...]}}
                if str(magnet_id) in status_data:
                    magnet_info = status_data[str(magnet_id)]
                elif magnet_id in status_data:
                    magnet_info = status_data[magnet_id]
                else:
                    magnet_info = status_data
            else:
                magnet_info = {}
            
            links = magnet_info.get('links', [])
            
            # Si no hay 'links' pero sí 'files' (formato v4.1)
            if not links and 'files' in magnet_info:
                links = _extract_v41_links(magnet_info.get('files', []))
                
            if links:
                break # Ya tenemos los enlaces listos, salimos del bucle
                
            time.sleep(2) # Damos 2 segundos a AllDebrid para que termine de procesar

        if not links:
            xbmc.log(f"RusterWolf AD Debug info incompleta: {res_status}", xbmc.LOGWARNING)
            xbmcgui.Dialog().ok('AllDebrid', 'El torrent está procesándose, pero tarda demasiado en generar los links. Vuelve a intentarlo en unos segundos.')
            return None
            
        # Buscar el archivo más grande (normalmente el vídeo principal)
        target_link = None
        max_size = 0
        valid_exts = ('.mp4', '.mkv', '.avi', '.m2ts', '.ts', '.mov', '.flv', '.wmv')
        
        for l in links:
            if isinstance(l, dict):
                filename = l.get('filename', '').lower()
                size = l.get('size', 0)
                if filename.endswith(VALID_VIDEO_EXTS) and size > max_size:
                    max_size = size
                    target_link = l.get('link')
            elif isinstance(l, str):
                # Por si la API devuelve directamente las URLs
                if any(l.lower().endswith(ext) for ext in VALID_VIDEO_EXTS):
                    target_link = l
                    break
        
        if not target_link:
            # Fallback: intentar coger el más grande que no sea un archivo comprimido ni de texto
            for l in links:
                if isinstance(l, dict):
                    filename = l.get('filename', '').lower()
                    size = l.get('size', 0)
                    if not filename.endswith(VALID_ARCHIVE_EXTS + ('.txt', '.nfo')) and size > max_size:
                        max_size = size
                        target_link = l.get('link')
            
            if not target_link:
                # Si llegamos aquí, es muy probable que el torrent solo contenga RARs
                fallback_link = links[0].get('link') if isinstance(links[0], dict) else links[0]
                if fallback_link and any(ext in fallback_link.lower() for ext in VALID_ARCHIVE_EXTS):
                    xbmcgui.Dialog().ok('AllDebrid - Error', 'Este torrent contiene archivos comprimidos (.rar / .zip) y no se puede reproducir en streaming.\n\nPor favor, selecciona otra calidad en la lista.')
                    return None
                target_link = fallback_link
        
        # 4. Desbloquear para obtener enlace de descarga final (.mkv/.mp4)
        url_unlock = f"{base_url}/link/unlock?agent={agent}&apikey={api_key}&link={urllib.parse.quote(target_link)}"
        res_unlock = requests.get(url_unlock, timeout=15).json()
            
        if res_unlock.get('status') != 'success':
            err_msg = res_unlock.get('error', {}).get('message', 'Error al desbloquear el enlace')
            xbmcgui.Dialog().ok('AllDebrid - Error', err_msg)
            return None
            
        xbmcgui.Dialog().notification('AllDebrid', '¡Reproducción instantánea lista!', ADDON_ICON)
        return res_unlock.get('data', {}).get('link')
        
    except requests.exceptions.HTTPError as e:
        try:
            err_res = e.response.json()
            err_msg = err_res.get('error', {}).get('message', f'HTTP Error {e.code}')
            xbmcgui.Dialog().ok('AllDebrid - Error HTTP', err_msg)
            xbmc.log(f"RusterWolf AD HTTP Error: {err_res}", xbmc.LOGERROR)
        except Exception:
            xbmcgui.Dialog().ok('AllDebrid', f'Fallo de API HTTP')
        return None
    except Exception as e:
        xbmcgui.Dialog().ok('AllDebrid', f'Fallo de conexión: {str(e)}')
        xbmc.log(f"RusterWolf AD Error: {e}", xbmc.LOGERROR)
        return None

def play_with_realdebrid(magnet, api_key):
    """Desbloquea el torrent usando Real-Debrid."""
    headers = {'Authorization': f'Bearer {api_key}'}
    base_url = "https://api.real-debrid.com/rest/1.0"
    
    try:
        xbmcgui.Dialog().notification('Real-Debrid', 'Comprobando caché instantánea...', ADDON_ICON)
        # 1. Agregar magnet
        res = requests.post(f"{base_url}/torrents/addMagnet", data={'magnet': magnet}, headers=headers, timeout=15).json()
        
        torrent_id = res.get('id')
        if not torrent_id: return None

        # 2. Comprobar info e iniciar conversión si RD lo requiere
        info = requests.get(f"{base_url}/torrents/info/{torrent_id}", headers=headers, timeout=15).json()
            
        if info.get('status') == 'magnet_conversion':
            time.sleep(3) # Pausa básica para conversión
            info = requests.get(f"{base_url}/torrents/info/{torrent_id}", headers=headers, timeout=15).json()
        
        # 3. Seleccionar archivos
        if info.get('status') == 'waiting_files_selection':
            files = info.get('files', [])
            video_files = [str(f['id']) for f in files if f['path'].lower().endswith(VALID_VIDEO_EXTS)]
            
            if not video_files:
                # Comprobar si en su lugar son archivos comprimidos
                rar_files = [str(f['id']) for f in files if f['path'].lower().endswith(VALID_ARCHIVE_EXTS)]
                if rar_files:
                    requests.delete(f"{base_url}/torrents/delete/{torrent_id}", headers=headers, timeout=10)
                    xbmcgui.Dialog().ok('Real-Debrid - Error', 'Este torrent contiene archivos comprimidos (.rar / .zip) y no se puede reproducir en streaming.\n\nPor favor, selecciona otra calidad en la lista.')
                    return None
                    
            file_selection = ','.join(video_files) if video_files else 'all'
            
            requests.post(f"{base_url}/torrents/selectFiles/{torrent_id}", data={'files': file_selection}, headers=headers, timeout=15)
            
            info = requests.get(f"{base_url}/torrents/info/{torrent_id}", headers=headers, timeout=15).json()

        # 4. Comprobar caché
        if info.get('status') != 'downloaded':
            requests.delete(f"{base_url}/torrents/delete/{torrent_id}", headers=headers, timeout=10)
            xbmcgui.Dialog().notification('Real-Debrid', 'Torrent no está en caché.', ADDON_ICON)
            return None
            
        # 5. Desbloquear link
        links = info.get('links', [])
        if not links: return None
            
        unr_info = requests.post(f"{base_url}/unrestrict/link", data={'link': links[0]}, headers=headers, timeout=15).json()
            
        xbmcgui.Dialog().notification('Real-Debrid', '¡Reproducción instantánea lista!', ADDON_ICON)
        return unr_info.get('download')
        
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().notification('Real-Debrid', f'Error de API', ADDON_ICON)
        return None
    except Exception as e:
        xbmcgui.Dialog().notification('Real-Debrid', 'Error desconocido', ADDON_ICON)
        return None

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