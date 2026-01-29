# -*- coding: utf-8 -*-
import os
import requests
import http.cookiejar
import xbmcvfs
from .common import addon

API_BASE = "https://api.atresplayer.com"
MAIN_CHANNEL_ID = "5a6b32667ed1a834493ec03b"

CATEGORIES = {
    "Series": "5a6a1b22986b281d18a512b8",
    "Programas": "5a6a1ba0986b281d18a512b9",
    "Documentales": "5b067bf3986b28b0a27c2f42",
    "Infantil": "5a6a24b1986b281d18a512c0",
    "Actualidad": "5a6a215e986b281d18a512bc",
    "Cine": "5b5f2f777ed1a86860102144",
    "Premium": "605b306f7ed1a86f42397281"
}

PROFILE_DIR = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
COOKIE_FILE = os.path.join(PROFILE_DIR, 'cookies.jar')

def get_session():
    """Crea una sesión persistente con cookies"""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
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
    if not os.path.exists(PROFILE_DIR): os.makedirs(PROFILE_DIR)
    cj = http.cookiejar.LWPCookieJar(COOKIE_FILE)
    for c in s.cookies: cj.set_cookie(c)
    cj.save(ignore_discard=True, ignore_expires=True)