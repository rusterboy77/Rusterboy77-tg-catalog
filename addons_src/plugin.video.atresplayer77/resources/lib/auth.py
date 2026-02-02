from .common import *

def do_login():
    """Placeholder para el login"""
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok("Atresplayer", "Por favor, introduce tu usuario y contraseña en los ajustes del addon.")
        open_settings()
        return
    
    # Usamos la función centralizada de common.py
    if login_process(username, password):
        xbmcgui.Dialog().notification("Atresplayer", "Login Correcto")
    else:
        xbmcgui.Dialog().notification("Error Login", "Credenciales incorrectas o error de conexión")