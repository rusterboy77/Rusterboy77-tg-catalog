# -*- coding: utf-8 -*-
import os
import xbmcgui
import xbmcplugin

SECTION_PLOTS = {
    'peliculas': 'Prepara las palomitas. Descubre desde los últimos taquillazos de Hollywood hasta clásicos inolvidables para una sesión de cine perfecta.',
    'series_tv': 'Maratones que atrapan. Sumérgete en temporadas repletas de intriga, comedia y acción con las series más aclamadas del momento.',
    'documentales': 'La realidad supera a la ficción. Explora los misterios de la naturaleza, crímenes reales y los secretos más profundos de nuestra historia.',
    'series_documental': 'La realidad supera a la ficción. Explora los misterios de la naturaleza, crímenes reales y los secretos más profundos de nuestra historia.',
    'anime': '¡Kame Hame Ha! Viaja a universos épicos y llenos de poder con nuestra brutal selección de animación japonesa.',
    'dibujos': 'Risas y aventuras para los peques (y no tan peques). Un espacio mágico repleto de color y animación para toda la familia.',
    'retro': '¡Directo a la nostalgia! Saca a pasear tu espíritu ochentero y noventero y revive esas joyas míticas.',
    'novedades': 'Lo último de lo último. Mantente al día con los estrenos más frescos que acaban de aterrizar en el catálogo.',
    'seguir_viendo': '¿Por dónde íbamos? Retoma tus capítulos y películas exactamente en el segundo que las dejaste.',
    'favoritos': 'Tu cámara acorazada personal. Todo el contenido que te ha robado el corazón, guardado a buen recaudo.',
    'buscar': 'Encuentra exactamente lo que te apetece ver. Busca por título, actor o director en todo nuestro catálogo.',
    'ajustes': 'Configura RusterWolf a tu gusto. Opciones de reproducción, cuentas premium, interfaz y mucho más.'
}

def _add_menu_item(handle, addon, addon_fanart, get_icon, get_logo, build_url, label, params, safe_id, is_folder=True):
    li = xbmcgui.ListItem(label)
    try:
        info = li.getVideoInfoTag()
        info.setTitle(label)
        info.setPlot(SECTION_PLOTS.get(safe_id, ''))
    except Exception: pass
    
    icon = get_icon(safe_id) or os.path.join(addon.getAddonInfo('path'), 'resources', 'media', 'icon.png')
    logo = get_logo(safe_id)
    art = {'fanart': addon_fanart, 'icon': icon, 'thumb': icon}
    if logo: art.update({'clearlogo': logo, 'logo': logo})
    try: li.setArt(art)
    except Exception: pass
    xbmcplugin.addDirectoryItem(handle, build_url(params), li, is_folder)

def build_root_menu(handle, addon, addon_fanart, get_icon, get_logo, build_url):
    items = [
        ('Novedades', {'action':'novedades_menu'}, 'novedades'),
        ('Favoritos', {'action':'favorites'}, 'favoritos'),
        ('Seguir Viendo...', {'action':'continue_watching'}, 'seguir_viendo'), 
        ('Películas', {'action':'movie_menu'}, 'peliculas'),
        ('Series TV', {'action':'tv_menu'}, 'series_tv'),
    ]
    
    try:
        if addon.getSettingBool('show_documentaries'):
            items.append(('Documentales', {'action':'documentary_main_menu'}, 'documentales'))
        if addon.getSettingBool('show_dibujos'):
            items.append(('Dibujos', {'action':'dibujos_main_menu'}, 'dibujos'))
        if addon.getSettingBool('show_anime'):
            items.append(('Anime', {'action':'anime_main_menu'}, 'anime'))
        if addon.getSettingBool('show_retro'):
            items.append(('Retro', {'action':'retro_main_menu'}, 'retro'))
    except Exception: pass
    
    items.extend([
        ('Buscar', {'action':'search'}, 'buscar'),
        ('Ajustes', {'action':'settings'}, 'ajustes'),
    ])
    
    xbmcplugin.setContent(handle, 'files')
    for label, params, safe_id in items:
        _add_menu_item(handle, addon, addon_fanart, get_icon, get_logo, build_url, label, params, safe_id)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)

def build_standard_menu(handle, addon, addon_fanart, get_icon, get_logo, build_url, filter_type, label_novedades, safe_id, show_collections=True, show_genres=True, show_years=True):
    entries = []
    sub = filter_type
    if filter_type == 'movie': sub = 'movies'
    elif filter_type == 'tv': sub = 'series'
    
    entries.append((f'Novedades {label_novedades}'.strip(), {'action': 'novedades', 'sub': sub, 'origin': filter_type, 'sort_by': 'novedades'}))
    entries.append(('Añadidos Recientemente', {'action': 'novedades', 'sub': sub, 'origin': filter_type, 'sort_by': 'date_added'}))
    entries.append(('Título', {'action': 'list', 'filter': filter_type, 'group': 'letter', 'origin': filter_type}))
    if show_collections: entries.append(('Colecciones', {'action': 'list', 'filter': filter_type, 'group': 'collection', 'origin': filter_type}))
    if show_genres: entries.append(('Género', {'action': 'list', 'filter': filter_type, 'group': 'genre', 'origin': filter_type}))
    entries.append(('Calidad', {'action': 'list', 'filter': filter_type, 'group': 'quality', 'origin': filter_type}))
    if show_years: entries.append(('Año', {'action': 'list', 'filter': filter_type, 'group': 'year', 'origin': filter_type}))

    xbmcplugin.setContent(handle, 'files')
    for label, params in entries:
        _add_menu_item(handle, addon, addon_fanart, get_icon, get_logo, build_url, label, params, safe_id)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)

def build_genre_sub_menu(handle, addon, addon_fanart, get_icon, get_logo, build_url, filter_type, genre_name, safe_id):
    entries = []
    if genre_name != 'Retro':
        entries.append(('Novedades', {'action': 'novedades', 'sub': 'movies' if filter_type=='movie' else 'series', 'genre': genre_name, 'origin': filter_type, 'sort_by': 'novedades'}))
        
    entries.append(('Añadidos Recientemente', {'action': 'novedades', 'sub': 'movies' if filter_type=='movie' else 'series', 'genre': genre_name, 'origin': filter_type, 'sort_by': 'date_added'}))
    entries.append(('Título', {'action': 'list', 'filter': filter_type, 'genre': genre_name, 'group': 'letter', 'origin': filter_type}))
    
    if filter_type == 'movie':
        entries.append(('Colecciones', {'action': 'list', 'filter': filter_type, 'genre': genre_name, 'group': 'collection', 'origin': filter_type}))
        
    if genre_name == 'Retro':
        entries.append(('Género', {'action': 'list', 'filter': filter_type, 'genre': genre_name, 'group': 'genre', 'origin': filter_type}))
        
    entries.append(('Calidad', {'action': 'list', 'filter': filter_type, 'genre': genre_name, 'group': 'quality', 'origin': filter_type}))
    entries.append(('Año', {'action': 'list', 'filter': filter_type, 'genre': genre_name, 'group': 'year', 'origin': filter_type}))
    
    xbmcplugin.setContent(handle, 'files')
    for label, params in entries:
        _add_menu_item(handle, addon, addon_fanart, get_icon, get_logo, build_url, label, params, safe_id)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)

def build_generic_main_menu(handle, addon, addon_fanart, get_icon, get_logo, build_url, title, genre_name, safe_id):
    entries = [
        (f'Películas {title}', {'action':'genre_movie_menu', 'genre': genre_name, 'safe_id': safe_id}),
        (f'Series {title}', {'action':'genre_tv_menu', 'genre': genre_name, 'safe_id': safe_id})
    ]
    xbmcplugin.setContent(handle, 'files')
    for label, params in entries:
        is_folder = False if safe_id == 'ajustes' else True
        _add_menu_item(handle, addon, addon_fanart, get_icon, get_logo, build_url, label, params, safe_id, is_folder)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)