# -*- coding: utf-8 -*-
import requests
import xbmcaddon
import xbmcgui
import time
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify

BASE_URL = "https://api.alldebrid.com/v4"
AGENT = "Choloretro"

def get_api_key():
    return xbmcaddon.Addon().getSetting('alldebrid_apikey')

def set_api_key(api_key):
    xbmcaddon.Addon().setSetting('alldebrid_apikey', api_key)

def authenticate_with_pin():
    """
    Abre un diálogo de progreso con PIN para autenticarse en AllDebrid.
    Permite salir de la aplicación en el móvil y continuar el chequeo en segundo plano.
    """
    try:
        # 1. Obtener PIN desde AllDebrid
        response = requests.get(f"{BASE_URL}/pin/get", params={'agent': AGENT}, timeout=10)
        data = response.json()
        
        if data.get('status') != 'success':
            notify('Choloretro', 'Error al obtener PIN de AllDebrid', 3000)
            return False
        
        pin_data = data.get('data', {})
        pin = pin_data.get('pin')
        check = pin_data.get('check')
        base_url_auth = pin_data.get('base_url')
        
        if not pin or not check:
            notify('Choloretro', 'No se pudo obtener datos de autenticación', 3000)
            return False
        
        # 2. Mostrar diálogo de progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Autenticación AllDebrid', f"Desde tu móvil o PC, visita:\n[B]{base_url_auth}[/B]\nE ingresa el código: [B][COLOR yellow]{pin}[/COLOR][/B]\nEsperando autorización...")
        
        expires_in = 600 # 10 minutos
        start_time = time.time()
        authorized = False
        
        while time.time() - start_time < expires_in:
            if progress.iscanceled():
                break
                
            check_url = f"{BASE_URL}/pin/check"
            check_params = {'agent': AGENT, 'check': check, 'pin': pin}
            try:
                check_response = requests.get(check_url, params=check_params, timeout=10)
                check_data = check_response.json()
                
                if check_data.get('status') == 'success':
                    if check_data.get('data', {}).get('activated'):
                        api_key = check_data.get('data', {}).get('apikey')
                        if api_key:
                            set_api_key(api_key)
                            authorized = True
                            break
            except Exception as e:
                pass
            
            time.sleep(5)
            percent = int(((time.time() - start_time) / expires_in) * 100)
            progress.update(percent)
            
        progress.close()
        
        if authorized:
            notify('Choloretro', 'Autenticación exitosa', 3000)
            return True
        else:
            notify('Choloretro', 'Autenticación cancelada o tiempo agotado', 3000)
            return False
            
    except Exception as e:
        log(f"AllDebrid Auth Error: {e}")
        notify('Choloretro', f'Error de autenticación: {str(e)}', 3000)
        return False

def unlock_link(link):
    """
    Desbloquea un enlace (ej. 1fichier) usando AllDebrid.
    Retorna la URL directa o None si falla.
    """
    apikey = get_api_key()
    if not apikey:
        notify('Choloretro', 'Falta API Key de AllDebrid', 3000)
        return None

    params = {
        'agent': AGENT,
        'apikey': apikey,
        'link': link
    }

    try:
        response = requests.get(f"{BASE_URL}/link/unlock", params=params, timeout=10)
        data = response.json()
        
        if data.get('status') == 'success':
            # El enlace directo suele estar en data['data']['link']
            return data['data']['link']
        else:
            error_code = data.get('error', {}).get('code', 'Unknown')
            error_msg = data.get('error', {}).get('message', 'Error desconocido')
            log(f"AllDebrid Error: {error_code} - {error_msg}")
            
            if error_code == 'AUTH_BAD_APIKEY':
                notify('Choloretro', 'API Key AllDebrid inválida', 3000)
            else:
                notify('Choloretro', f'Error AllDebrid: {error_msg}', 3000)
            return None
            
    except Exception as e:
        log(f"AllDebrid Exception: {e}")
        return None