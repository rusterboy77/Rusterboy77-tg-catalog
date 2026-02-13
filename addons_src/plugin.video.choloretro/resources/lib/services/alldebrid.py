# -*- coding: utf-8 -*-
import requests
import xbmcaddon
import xbmcgui
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
    Abre un diálogo modal con PIN para autenticarse en AllDebrid.
    Tipo de flujo similar a otros addons (GetPin -> Usuario abre navegador -> Ingresa PIN -> Se guarda API Key).
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
        check_url = pin_data.get('check_url')
        user_url = pin_data.get('user_url')
        
        if not pin or not user_url:
            notify('Choloretro', 'No se pudo obtener datos de autenticación', 3000)
            return False
        
        # 2. Mostrar diálogo con instrucciones y URL
        dialog = xbmcgui.Dialog()
        
        mensaje = f"""Sigue estos pasos para autenticarte en AllDebrid:

1. Abre tu navegador y ve a:
   {user_url}

2. Introduce el siguiente PIN cuando se te pida:
   {pin}

3. Una vez autenticado, vuelve aquí y pulsa OK.
   
El PIN expirará en 15 minutos."""
        
        if dialog.yesno('AllDebrid Autenticación', mensaje, yeslabel='Continuar', nolabel='Cancelar'):
            # 3. Verificar que el usuario se haya autenticado (con reintentos)
            max_attempts = 30  # 30 segundos esperando
            attempt = 0
            
            # Mostrar diálogo de progreso
            progress = xbmcgui.DialogProgress()
            progress.create('AllDebrid', 'Esperando autenticación...')
            
            while attempt < max_attempts:
                try:
                    check_response = requests.get(check_url, params={'agent': AGENT}, timeout=10)
                    check_data = check_response.json()
                    
                    if check_data.get('status') == 'success':
                        api_key = check_data.get('data', {}).get('apikey')
                        if api_key:
                            # Guardar API Key
                            set_api_key(api_key)
                            progress.close()
                            notify('Choloretro', 'Autenticación exitosa', 3000)
                            return True
                    
                    # Actualizar progreso
                    progress.update(int((attempt / max_attempts) * 100))
                    
                except Exception as e:
                    log(f"AllDebrid check error: {e}")
                
                # Esperar 1 segundo antes de reintentar
                import time
                time.sleep(1)
                attempt += 1
            
            progress.close()
            notify('Choloretro', 'Tiempo de autenticación agotado', 3000)
            return False
        else:
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