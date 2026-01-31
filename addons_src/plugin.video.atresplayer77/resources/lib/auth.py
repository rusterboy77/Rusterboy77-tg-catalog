from .common import *

def do_login():
    """Placeholder para el login"""
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok("Atresplayer", "Por favor, introduce tu usuario y contraseña en los ajustes del addon.")
        open_settings()
        return
    
    # Usar una sesión limpia para el login (evitar cookies viejas corruptas)
    s = requests.Session()
    # Usar las mismas cabeceras que get_session para consistencia
    s.headers.update(get_session().headers)

    # Paso 1: Obtener cookies iniciales (CSRF, etc.) visitando la web de login
    try:
        xbmc.log("ATRES_LOGIN: Visitando home para obtener cookies...", xbmc.LOGWARNING)
        s.get("https://www.atresplayer.com/", timeout=10)
    except Exception as e:
        xbmc.log(f"ATRES_LOGIN_WARN: Fallo en GET inicial: {e}", xbmc.LOGWARNING)

    # Paso 2: Realizar el POST de login
    url = "https://account.atresplayer.com/auth/v1/login"
    payload = {"username": username, "password": password}
    
    try:
        # DEBUG: Imprimir el comando cURL equivalente para comparar con el navegador
        req_headers = dict(s.headers)
        req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        curl_cmd = f"curl -X POST '{url}'"
        for k, v in req_headers.items():
            curl_cmd += f" -H '{k}: {v}'"
        curl_cmd += f" --data '{urlencode(payload)}'"
        xbmc.log(f"ATRES_CURL_DEBUG: {curl_cmd}", xbmc.LOGWARNING)

        # Enviar como FORMULARIO (data=payload) según cURL
        r = s.post(url, data=payload, timeout=15)
        
        if r.status_code == 200:
            save_cookies(s)
            xbmcgui.Dialog().notification("Atresplayer", "Login Correcto")
            xbmc.log(f"ATRES_LOGIN_SUCCESS: Conectado usando {url}", xbmc.LOGWARNING)
        elif r.status_code in (401, 403):
            xbmcgui.Dialog().notification("Error Login", "Usuario o contraseña incorrectos")
        else:
            xbmc.log(f"ATRES_LOGIN_FAIL: {r.status_code} en {url} -> {r.text[:200]}", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("Error Login", f"Error {r.status_code}")
    except Exception as e:
        xbmc.log(f"ATRES_LOGIN_EXC: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Error Login", str(e))