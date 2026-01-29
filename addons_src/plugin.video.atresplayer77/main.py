import sys
from urllib.parse import parse_qsl
from resources.lib import navigation, player, search, auth


def router(paramstring):
    params = dict(parse_qsl(paramstring))
    
    if not params:
        navigation.list_categories()
        return

    action = params.get('action')

    if action == 'settings':
        auth.open_settings()
    elif action == 'list_section':
        navigation.list_section(params.get('category_id'), params.get('category_name'), int(params.get('page', 0)))
    elif action == 'open_item':
        navigation.open_item(params.get('href'))
    elif action == 'login':
        auth.do_login()
    elif action == 'list_live':
        navigation.list_live()
    elif action == 'play':
        player.play(params.get('href'))
    elif action == 'bridge_palantir':
        search.search_palantir_bridge(params.get('q'))
    elif action == 'search':
        search.do_search(params.get('query'))

if __name__ == '__main__':
    router(sys.argv[2][1:])