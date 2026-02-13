# -*- coding: utf-8 -*-
import requests
import xbmcaddon
import xbmcgui
from resources.lib.utils.tools import log

BASE_URL = "https://api.alldebrid.com/v4"
AGENT = "Choloretro"

def get_api_key():
    return xbmcaddon.Addon().getSetting('alldebrid_apikey')

def unlock_link(link):
    """
    Desbloquea un enlace (ej. 1fichier) usando AllDebrid.
    Retorna la URL directa o None si falla.
    """
    apikey = get_api_key()
    if not apikey:
        xbmcgui.Dialog().notification('Choloretro', 'Falta API Key de AllDebrid', xbmcgui.NOTIFICATION_ERROR)
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
                xbmcgui.Dialog().notification('Choloretro', 'API Key AllDebrid inválida', xbmcgui.NOTIFICATION_ERROR)
            else:
                xbmcgui.Dialog().notification('Choloretro', f'Error AllDebrid: {error_msg}', xbmcgui.NOTIFICATION_ERROR)
            return None
            
    except Exception as e:
        log(f"AllDebrid Exception: {e}")
        return None