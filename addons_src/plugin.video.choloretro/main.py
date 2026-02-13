# -*- coding: utf-8 -*-
import sys
from urllib.parse import parse_qsl
from resources.lib.router import Router
from resources.lib.utils.tools import log
from resources.lib.database import init_db, update_db_from_remote

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
                import xbmcgui
                xbmcgui.Dialog().notification('Choloretro', 'Catálogo actualizado', xbmcgui.NOTIFICATION_INFO, 2000)
        except Exception as e:
            log(f"Main: Error en update_db_from_remote: {e}")

    # Instanciar enrutador y despachar
    router = Router(url, handle)
    router.dispatch(params)

if __name__ == '__main__':
    main()