import sys
import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from urllib.parse import parse_qsl
import base64
import importlib.abc
import importlib.util

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

# --- DECRYPT ON THE FLY ---
class PalantirLoader(importlib.abc.SourceLoader):
    def __init__(self, path):
        self.path = path
    def get_filename(self, fullname):
        return self.path
    def get_data(self, path):
        with open(path, 'rb') as f:
            encrypted_data = f.read()
        length = len(encrypted_data)
        part_size = length // 3
        part_C = encrypted_data[length - part_size:]
        remaining = encrypted_data[:length - part_size]
        part_A = remaining[:part_size]
        part_B = remaining[part_size:][::-1]
        shuffled_data = part_C + part_A + part_B
        return base64.b85decode(shuffled_data)

class PalantirFinder(importlib.abc.MetaPathFinder):
    def __init__(self, libs_path):
        self.libs_path = libs_path
    def find_spec(self, fullname, path, target=None):
        module_name = fullname.split('.')[-1]
        md_path = os.path.join(self.libs_path, f"{module_name}.md")
        if os.path.exists(md_path):
            return importlib.util.spec_from_file_location(fullname, md_path, loader=PalantirLoader(md_path))
        return None

libs_dir = os.path.join(palantir_path, 'libs')
bridge_finder = PalantirFinder(libs_dir)
sys.meta_path.insert(0, bridge_finder)

try:
    from libs.ioI1iII import P3Item
except ImportError:
    sys.path.append(libs_dir)
    from ioI1iII import P3Item

sys.meta_path.remove(bridge_finder)

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
