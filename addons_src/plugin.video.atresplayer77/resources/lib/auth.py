# -*- coding: utf-8 -*-
import xbmcgui
import xbmc
import requests
from urllib.parse import urlencode
from .common import addon
from .api import get_session, save_cookies

def open_settings():
    addon.openSettings()

def do_login():
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok("Atresplayer", "Por favor, introduce tu usuario y contraseña en los ajustes del addon.")
        open_settings()
        return
    
    s = requests.Session()
    s.headers.update(get_session().headers)
    try:
        s.get("https://www.atresplayer.com/", timeout=10)
        url = "https://account.atresplayer.com/auth/v1/login"
        payload = {"username": username, "password": password}
        r = s.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            save_cookies(s)
            xbmcgui.Dialog().notification("Atresplayer", "Login Correcto")
        else: xbmcgui.Dialog().notification("Error Login", f"Error {r.status_code}")
    except Exception as e: xbmcgui.Dialog().notification("Error Login", str(e))