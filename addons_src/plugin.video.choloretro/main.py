# -*- coding: utf-8 -*-
import sys
import os
from urllib.parse import parse_qsl
from resources.lib.router import Router
from resources.lib.utils.tools import log
from resources.lib.database import init_db, update_db_from_remote
import xbmcgui
import xbmcaddon
from resources.lib.services.notify import notify

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')

# Resolver icono del addon (buscar en múltiples ubicaciones)
try:
    if os.path.exists(os.path.join(ADDON_PATH, 'icon.png')):
        ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')
    elif os.path.exists(os.path.join(ADDON_PATH, 'resources', 'media', 'icon.png')):
        ADDON_ICON = os.path.join(ADDON_PATH, 'resources', 'media', 'icon.png')
    else:
        ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')  # Fallback
except:
    ADDON_ICON = os.path.join(ADDON_PATH, 'icon.png')

def main():
    # Parsear argumentos de Kodi
    url = sys.argv[0]
    handle = int(sys.argv[1])
    params_str = sys.argv[2][1:] if len(sys.argv) > 2 and sys.argv[2] else ''
    params = dict(parse_qsl(params_str))

    # Inicializar DB si es la raíz (sin params)
    if not params:
        init_db()
        # Descargar base de datos precompilada desde GitHub
        try:
            if update_db_from_remote():
                # Usar helper de notificaciones
                notify('Choloretro', 'Catálogo actualizado', 2000)
        except Exception as e:
            log(f"Main: Error en update_db_from_remote: {e}")

    # Instanciar enrutador y despachar
    router = Router(url, handle)
    router.dispatch(params)

if __name__ == '__main__':
    main()