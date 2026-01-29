import sys
import urllib.parse
from urllib.parse import parse_qsl

# Importar módulos propios
from resources.lib.common import open_settings
from resources.lib.navigation import list_categories, list_section, open_item, list_live
from resources.lib.player import play
from resources.lib.search import search_palantir_bridge, do_search
from resources.lib.auth import do_login

def router(paramstring):
    params = dict(parse_qsl(paramstring))
    
    if not params:
        list_categories()
        return

    action = params.get('action')

    if action == 'settings':
        open_settings()
    elif action == 'list_section':
        list_section(params.get('category_id'), params.get('category_name'), int(params.get('page', 0)))
    elif action == 'open_item':
        open_item(params.get('href'))
    elif action == 'login':
        do_login()
    elif action == 'list_live':
        list_live()
    elif action == 'play':
        play(params.get('href'))
    elif action == 'bridge_palantir':
        search_palantir_bridge(params.get('q'))
    elif action == 'search':
        do_search(params.get('query'))

if __name__ == '__main__':
    router(sys.argv[2][1:])