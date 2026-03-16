# -*- coding: utf-8 -*-
import xbmc, xbmcgui, xbmcaddon
import urllib.request, urllib.parse, urllib.error, json, time

ADDON = xbmcaddon.Addon()
CLIENT_ID = "X245A4XAIBGVM" # ID por defecto para integraciones de terceros en Real-Debrid

def auth():
    url = f"https://api.real-debrid.com/oauth/v2/device/code?client_id={CLIENT_ID}&new_credentials=yes"
    try:
        req = urllib.request.urlopen(url)
        res = json.loads(req.read())
    except Exception as e:
        xbmcgui.Dialog().ok("Error", f"Fallo al conectar con Real-Debrid: {e}")
        return

    device_code = res["device_code"]
    user_code = res["user_code"]
    verification_url = res["verification_url"]
    interval = int(res["interval"])
    expires_in = int(res["expires_in"])

    progress = xbmcgui.DialogProgress()
    progress.create("Autenticación Real-Debrid", f"Desde tu móvil o PC, visita:\n[B]{verification_url}[/B]\nE ingresa el código: [B][COLOR yellow]{user_code}[/COLOR][/B]\nEsperando autorización...")

    start_time = time.time()
    authorized = False
    client_secret = ""
    client_id_new = CLIENT_ID

    while time.time() - start_time < expires_in:
        if progress.iscanceled():
            break
        
        check_url = f"https://api.real-debrid.com/oauth/v2/device/credentials?client_id={CLIENT_ID}&code={device_code}"
        try:
            c_req = urllib.request.urlopen(check_url)
            c_res = json.loads(c_req.read())
            if "client_secret" in c_res:
                client_secret = c_res["client_secret"]
                client_id_new = c_res["client_id"]
                authorized = True
                break
        except urllib.error.HTTPError as e:
            pass # Un error 403 simplemente significa que el usuario aún no ha puesto el código
        except Exception:
            pass
        
        time.sleep(interval)
        percent = int(((time.time() - start_time) / expires_in) * 100)
        progress.update(percent)

    if not authorized or not client_secret:
        progress.close()
        xbmcgui.Dialog().ok("Real-Debrid", "Autenticación cancelada o tiempo agotado.")
        return

    # Paso final: Intercambiar el código por el token de acceso
    token_url = "https://api.real-debrid.com/oauth/v2/token"
    data = urllib.parse.urlencode({
        "client_id": client_id_new,
        "client_secret": client_secret,
        "code": device_code,
        "grant_type": "http://oauth.net/grant_type/device/1.0"
    }).encode('utf-8')

    try:
        t_req = urllib.request.Request(token_url, data=data)
        t_res = json.loads(urllib.request.urlopen(t_req).read())
        access_token = t_res["access_token"]
        ADDON.setSetting("realdebrid_api_key", access_token)
        progress.close()
        xbmcgui.Dialog().ok("Real-Debrid", "¡Autenticación completada con éxito!")
    except Exception as e:
        progress.close()
        xbmcgui.Dialog().ok("Error", f"Error obteniendo token final: {e}")
