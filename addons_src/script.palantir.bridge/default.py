import sys
import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from urllib.parse import parse_qsl

if not hasattr(xbmc, '_palantir_addon_patched'):
    _original_Addon = xbmcaddon.Addon
    def AddonProxy(id=None):
        if not id: 
            id = 'plugin.video.palantir3'
        return _original_Addon(id)
    xbmcaddon.Addon = AddonProxy
    xbmc._palantir_addon_patched = True

palantir_id = 'plugin.video.palantir3'
palantir_path = xbmcvfs.translatePath(f'special://home/addons/{palantir_id}/')

for module in list(sys.modules.keys()):
    if 'plugin.video.palantir3' in module or ('libs.' in module and 'script.palantir.bridge' not in module):
        del sys.modules[module]

if palantir_path not in sys.path:
    sys.path.append(palantir_path)

try:
    from libs.ioI1iII import P3Item
except ImportError:
    sys.path.append(os.path.join(palantir_path, 'libs'))
    from ioI1iII import P3Item

def get_params():
    try:
        if len(sys.argv) >= 2:
            return dict(parse_qsl(sys.argv[2].lstrip('?')))
    except:
        pass
    return {}

params = get_params()
query = params.get('query')
mode = params.get('mode', 'movie')

if query:
    if mode == 'tv':
        sql_command = f"SELECT titulo,fecha,plot,poster,fondo,tmdb,audio,mpaa,genero, trailer, clearlogo, rating, categoria FROM v_series where iREGEXP ('{query}', titulo) ORDER by titulo COLLATE latin1"
        action_target = 'listado_serieS'
    else:
        sql_command = f"SELECT titulo,fecha,plot,poster,fondo,audio,calidad,tmdb,duration,mpaa,genero, trailer, clearlogo, rating, categoria FROM v_pelis where iREGEXP ('{query}', titulo) ORDER by titulo COLLATE latin1"
        action_target = 'listado_peliculaS'
    
    item_palantir = P3Item(
        action=action_target, 
        sql=sql_command,
        label=f'Buscando: {query}'
    )
    
    encrypted_query = item_palantir.tourl()
    
    sys.argv = [
        f'plugin://{palantir_id}/',
        sys.argv[1],
        '?' + encrypted_query
    ]
    
    palantir_default = os.path.join(palantir_path, 'default.py')
    
    try:
        with open(palantir_default, 'r', encoding='utf-8') as f:
            code = compile(f.read(), palantir_default, 'exec')
            exec(code, {'__name__': '__main__', '__file__': palantir_default})
            
    except Exception:
        xbmcgui.Dialog().notification('Palantir Bridge', 'Error interno', xbmcgui.NOTIFICATION_ERROR)

else:
    xbmcgui.Dialog().notification('Palantir Bridge', 'Falta query', xbmcgui.NOTIFICATION_INFO)
