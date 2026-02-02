import sys
import os
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import xbmc
import base64
import re
import requests
import json
import http.cookiejar
import urllib.parse
from urllib.parse import parse_qsl, urlencode

# Configuración inicial
xbmc.log("ATRESPLAYER77: Iniciando script v1.0.3...", xbmc.LOGWARNING)
try:
    PLUGIN_URL = sys.argv[0]
    HANDLE = int(sys.argv[1])
except:
    PLUGIN_URL = ""
    HANDLE = 0

addon = xbmcaddon.Addon()

# --- CONSTANTES API ---
API_BASE = "https://api.atresplayer.com"
MAIN_CHANNEL_ID = "5a6b32667ed1a834493ec03b"

# IDs de categorías oficiales
CATEGORIES = {
    "Series": "5a6a1b22986b281d18a512b8",
    "Programas": "5a6a1ba0986b281d18a512b9",
    "Documentales": "5b067bf3986b28b0a27c2f42",
    "Infantil": "5a6a24b1986b281d18a512c0",
    "Actualidad": "5a6a215e986b281d18a512bc",
    "Cine": "5b5f2f777ed1a86860102144",
    "Premium": "605b306f7ed1a86f42397281"
}

# Gestión de Cookies y Sesión
PROFILE_DIR = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
COOKIE_FILE = os.path.join(PROFILE_DIR, 'cookies.jar')

def get_session():
    """Crea una sesión persistente con cookies"""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
        'Accept': '*/*',
        'Accept-Language': 'es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Origin': 'https://www.atresplayer.com',
        'Referer': 'https://www.atresplayer.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Connection': 'keep-alive'
    })
    if os.path.exists(COOKIE_FILE):
        try:
            cj = http.cookiejar.LWPCookieJar(COOKIE_FILE)
            cj.load(ignore_discard=True, ignore_expires=True)
            s.cookies = cj
        except Exception: pass
    return s

def save_cookies(s):
    """Guarda las cookies en disco"""
    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)
    cj = http.cookiejar.LWPCookieJar(COOKIE_FILE)
    for c in s.cookies: cj.set_cookie(c)
    cj.save(ignore_discard=True, ignore_expires=True)

def get_url(**kwargs):
    """Ayuda para crear URLs internas del addon"""
    return '{0}?{1}'.format(PLUGIN_URL, urlencode(kwargs))

def fix_img(url, type='vertical'):
    """Arregla las URLs de imágenes de Atresplayer"""
    if not url: return ""
    # A veces vienen sin esquema
    if url.startswith("//"): url = "https:" + url
    elif url.startswith("/"): url = "https://www.atresplayer.com" + url
    
    # CORRECCIÓN: Si la URL es un directorio, añadir un tamaño de imagen estándar.
    if url.endswith('/'):
        if type == 'horizontal':
            url = url + '1280x720.jpg' # Fanart HD
        elif type == 'logo':
            url = url + 'original.png' # Logo transparente
        else:
            url = url + '390x219.jpg' # Poster vertical
    # Añadir User-Agent para asegurar que Kodi pueda descargar la imagen
    return url + "|User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"

def open_settings():
    addon.openSettings()

def recursive_find_playable(data, results):
    """Busca recursivamente cualquier objeto que parezca un enlace de reproducción"""
    if isinstance(data, dict):
        href = data.get("href")
        type_ = data.get("type")
        label = str(data.get("label", "")).lower()
        
        # Criterios: Botón PLAY, enlace a /t/ (target), enlace a /player/
        is_play_btn = type_ == "PLAY" or "reproducir" in label or "ver ahora" in label or "ver la película" in label or label == "ver"
        is_video_link = href and ("/t/" in href or "/player/" in href or "/page/episode/" in href or "/episode/" in href)
        
        if href and (is_play_btn or is_video_link):
             # Evitar duplicados
             if not any(r.get("href") == href for r in results):
                results.append(data)
        
        for v in data.values():
            recursive_find_playable(v, results)
    elif isinstance(data, list):
        for item in data:
            recursive_find_playable(item, results)

def login_process(username, password):
    """Realiza el login contra la API y guarda las cookies (Lógica centralizada)"""
    try:
        s = requests.Session()
        # Usamos los mismos headers que en get_session
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
            'Accept': '*/*',
            'Accept-Language': 'es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7',
            'Origin': 'https://www.atresplayer.com',
            'Referer': 'https://www.atresplayer.com/',
            'Connection': 'keep-alive'
        })
        
        # 1. Obtener cookies de sesión iniciales
        s.get("https://www.atresplayer.com/", timeout=10)
        
        # 2. Login
        url = "https://account.atresplayer.com/auth/v1/login"
        payload = {"username": username, "password": password}
        r = s.post(url, data=payload, timeout=15)
        
        if r.status_code == 200:
            save_cookies(s)
            return True
        return False
    except Exception as e:
        xbmc.log(f"ATRES_LOGIN_ERR: {e}", xbmc.LOGERROR)
        return False

def attempt_auto_login():
    """Intenta renovar la sesión silenciosamente usando las credenciales guardadas"""
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if username and password:
        xbmc.log("ATRESPLAYER77: 401 Detectado - Intentando renovación automática de sesión...", xbmc.LOGWARNING)
        if login_process(username, password):
            xbmc.log("ATRESPLAYER77: Renovación exitosa", xbmc.LOGINFO)
            xbmcgui.Dialog().notification("Atresplayer", "Sesión renovada automáticamente")
            return True
    return False