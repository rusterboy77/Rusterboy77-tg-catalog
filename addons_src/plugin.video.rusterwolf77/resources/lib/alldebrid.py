# -*- coding: utf-8 -*-
import xbmc, xbmcgui, xbmcaddon
import urllib.request, json, time

ADDON = xbmcaddon.Addon()
AGENT = "RusterWolf77"

def auth():
    url = f"https://api.alldebrid.com/v4.1/pin/get?agent={AGENT}"
    try:
        req = urllib.request.urlopen(url)
        res = json.loads(req.read())
    except Exception as e:
        xbmcgui.Dialog().ok("Error", f"Fallo al conectar con AllDebrid: {e}")
        return

    if res.get("status") != "success":
        xbmcgui.Dialog().ok("Error", "No se pudo iniciar la autenticación.")
        return

    pin = res["data"]["pin"]
    check = res["data"]["check"]
    base_url = res["data"]["base_url"]

    progress = xbmcgui.DialogProgress()
    progress.create("Autenticación AllDebrid", f"Desde tu móvil o PC, visita:\n[B]{base_url}[/B]\nE ingresa el código: [B][COLOR yellow]{pin}[/COLOR][/B]\nEsperando autorización...")

    expires_in = 600
    start_time = time.time()
    authorized = False
    apikey = ""

    while time.time() - start_time < expires_in:
        if progress.iscanceled():
            break
        
        check_url = f"https://api.alldebrid.com/v4.1/pin/check?agent={AGENT}&check={check}&pin={pin}"
        try:
            c_req = urllib.request.urlopen(check_url)
            c_res = json.loads(c_req.read())
            if c_res.get("status") == "success":
                if c_res["data"]["activated"]:
                    apikey = c_res["data"]["apikey"]
                    authorized = True
                    break
        except:
            pass
        
        time.sleep(5)
        percent = int(((time.time() - start_time) / expires_in) * 100)
        progress.update(percent)

    progress.close()

    if authorized and apikey:
        ADDON.setSetting("alldebrid_api_key", apikey)
        xbmcgui.Dialog().ok("AllDebrid", "¡Autenticación completada con éxito!")
    else:
        xbmcgui.Dialog().ok("AllDebrid", "Autenticación cancelada o tiempo agotado.")
