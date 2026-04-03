# -*- coding: utf-8 -*-
import sys
import os
from urllib.parse import parse_qsl
from resources.lib.router import Router
from resources.lib.utils.tools import log
from resources.lib.database import init_db, update_db_from_remote, ensure_session_db, _is_db_valid
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

def run_one_time_cleanup():
    try:
        import xbmcvfs
        profile_dir = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON.getAddonInfo('id')}")
        flag_file = os.path.join(profile_dir, 'v3_db_migration.flag')
        if not os.path.exists(flag_file):
            old_db = os.path.join(profile_dir, 'cache.db')
            if os.path.exists(old_db):
                try: os.remove(old_db)
                except: pass
                
            # --- MIGRACIÓN DE HISTORIAL ANTIGUO AL JSON ---
            try:
                import glob, sqlite3, time
                from urllib.parse import urlparse, parse_qs
                from resources.lib.gui.listings import load_progress_override, save_progress_override, _normalize_title_for_match
                
                po = load_progress_override()
                kodi_db_dir = os.path.join(xbmcvfs.translatePath('special://profile/'), 'Database')
                kodi_dbs = glob.glob(os.path.join(kodi_db_dir, 'MyVideos*.db'))
                if kodi_dbs:
                    kodi_db = sorted(kodi_dbs, key=lambda p: os.path.getmtime(p), reverse=True)[0]
                    conn = sqlite3.connect(kodi_db)
                    cur = conn.cursor()
                    cur.execute("SELECT strFilename FROM files WHERE strFilename LIKE 'plugin://plugin.video.choloretro/%' AND (playCount > 0 OR idFile IN (SELECT idFile FROM bookmark WHERE type=1))")
                    changed = False
                    for row in cur.fetchall():
                        qs = parse_qs(urlparse(row[0]).query)
                        title = qs.get('title', [''])[0]
                        tvshow = qs.get('tvshowtitle', [''])[0]
                        target_title = tvshow if tvshow else title
                        wtype = 'tv' if tvshow else 'movie'
                        if target_title:
                            norm_title = _normalize_title_for_match(target_title)
                            val = norm_title if wtype == 'tv' else f"movie_{norm_title}"
                            if val not in po['manual'] and val not in po['hidden']:
                                po['manual'][val] = {'wtype': wtype, 'title': target_title, 'added': time.time()}
                                changed = True
                    conn.close()
                    if changed: save_progress_override(po)
            except Exception as e:
                log(f"Choloretro: Error migrando bookmarks a JSON: {e}")
            # ----------------------------------------------
            
            with open(flag_file, 'w') as f:
                f.write('done')
    except: pass

def main():
    # Parsear argumentos de Kodi
    url = sys.argv[0]
    handle = int(sys.argv[1])
    params_str = sys.argv[2][1:] if len(sys.argv) > 2 and sys.argv[2] else ''
    params = dict(parse_qsl(params_str))
    
    run_one_time_cleanup()

    # Inicializar DB si es la raíz (sin params)
    if not params:
        ensure_session_db()
        init_db()
        # Descargar base de datos precompilada desde GitHub
        try:
            if update_db_from_remote():
                # Usar helper de notificaciones
                notify('Choloretro', 'Catálogo actualizado', 2000)
        except Exception as e:
            log(f"Main: Error en update_db_from_remote: {e}")
    else:
        ensure_session_db()
    # Si la BD no existe en Temp (Android TV limpió caché), forzar la descarga para los widgets
    if not _is_db_valid():
        update_db_from_remote()

    # Instanciar enrutador y despachar
    router = Router(url, handle)
    router.dispatch(params)

if __name__ == '__main__':
    main()