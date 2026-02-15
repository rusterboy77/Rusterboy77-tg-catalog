# -*- coding: utf-8 -*-
# c:\Users\ruste\AppData\Roaming\Kodi\addons\plugin.video.choloretro\resources\lib\services\realdebrid.py
import requests
import xbmcaddon
import xbmcgui
import time
from resources.lib.utils.tools import log
from resources.lib.services.notify import notify

# Constantes Real-Debrid
BASE_URL = "https://api.real-debrid.com/rest/1.0"
AUTH_URL = "https://api.real-debrid.com/oauth/v2"
CLIENT_ID = "X245A4XAIBGVM"  # ID público para Device Flow

def get_token():
    return xbmcaddon.Addon().getSetting('realdebrid_token')

def set_token(token):
    xbmcaddon.Addon().setSetting('realdebrid_token', token)

def authenticate_with_pin():
    """
    Flujo de autenticación Device Flow para Real-Debrid.
    """
    try:
        # 1. Solicitar código de dispositivo
        params = {'client_id': CLIENT_ID, 'new_credentials': 'yes'}
        response = requests.get(f"{AUTH_URL}/device/code", params=params, timeout=10)
        data = response.json()
        
        device_code = data.get('device_code')
        user_code = data.get('user_code')
        verification_url = data.get('verification_url')
        interval = data.get('interval', 5)
        expires_in = data.get('expires_in', 900)
        
        if not user_code:
            notify('Choloretro', 'Error al obtener código de Real-Debrid', 3000)
            return False
            
        # 2. Mostrar diálogo al usuario
        dialog = xbmcgui.Dialog()
        
        mensaje = f"""Sigue estos pasos para autenticarte en Real-Debrid:

1. Abre tu navegador y ve a:
   {verification_url}

2. Introduce el siguiente código:
   {user_code}

3. Una vez autorizado en la web, pulsa 'Continuar'.
   
El código expira en {int(expires_in/60)} minutos."""
        
        # Mostrar diálogo de instrucciones (Estilo AllDebrid)
        if not dialog.yesno('Real-Debrid Autenticación', mensaje, yeslabel='Continuar', nolabel='Cancelar'):
            return False
        
        # Usamos DialogProgress para permitir cancelación y mostrar estado
        progress = xbmcgui.DialogProgress()
        progress.create('Real-Debrid', f'Verificando autorización...\nCódigo: {user_code}')
        
        start_time = time.time()
        
        while (time.time() - start_time) < expires_in:
            if progress.iscanceled():
                progress.close()
                return False
            
            # Esperar el intervalo requerido
            time.sleep(interval)
            
            # 3. Verificar credenciales
            check_params = {'client_id': CLIENT_ID, 'code': device_code}
            check_resp = requests.get(f"{AUTH_URL}/device/credentials", params=check_params)
            
            if check_resp.status_code == 200:
                creds = check_resp.json()
                client_id = creds.get('client_id')
                client_secret = creds.get('client_secret')
                
                if client_id and client_secret:
                    # 4. Canjear credenciales por Token
                    token_params = {
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'code': device_code,
                        'grant_type': 'http://oauth.net/grant_type/device/1.0'
                    }
                    token_resp = requests.post(f"{AUTH_URL}/token", data=token_params)
                    token_data = token_resp.json()
                    
                    access_token = token_data.get('access_token')
                    if access_token:
                        set_token(access_token)
                        progress.close()
                        notify('Choloretro', 'Real-Debrid: Autenticación exitosa', 3000)
                        return True
            
            # Actualizar barra de progreso
            percent = int(((time.time() - start_time) / expires_in) * 100)
            progress.update(percent)
            
        progress.close()
        notify('Choloretro', 'Tiempo de espera agotado', 3000)
        return False
        
    except Exception as e:
        log(f"Real-Debrid Auth Error: {e}")
        notify('Choloretro', f'Error de autenticación: {str(e)}', 3000)
        return False

def unlock_link(link):
    """
    Desbloquea un enlace usando Real-Debrid.
    """
    token = get_token()
    if not token:
        # Retornamos None silenciosamente para permitir fallback a otros servicios
        return None

    headers = {'Authorization': f'Bearer {token}'}
    data = {'link': link}

    try:
        response = requests.post(f"{BASE_URL}/unrestrict/link", headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('download')
        elif response.status_code == 401:
            notify('Choloretro', 'Real-Debrid: Token inválido o expirado', 3000)
            return None
        else:
            # Intentar leer mensaje de error
            try:
                err = response.json()
                msg = err.get('error', 'Error desconocido')
                log(f"Real-Debrid Error: {msg}")
                notify('Choloretro', f'Real-Debrid: {msg}', 3000)
            except:
                pass
            return None
            
    except Exception as e:
        log(f"Real-Debrid Exception: {e}")
        return None
