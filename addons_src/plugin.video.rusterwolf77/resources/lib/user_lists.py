# -*- coding: utf-8 -*-
import os, glob, sqlite3, urllib.parse
import xbmc, xbmcgui, xbmcplugin, xbmcvfs

SECTION_PLOTS = {
    'seguir_viendo': '¿Por dónde íbamos? Retoma tus capítulos y películas exactamente en el segundo que las dejaste.',
    'favoritos': 'Tu cámara acorazada personal. Todo el contenido que te ha robado el corazón, guardado a buen recaudo.'
}

def render_continue_watching(handle, addon_fanart, icon_path, section_logo,
                             po, played_keys, resume_points,
                             build_url, apply_info_tag, apply_art, generate_cm,
                             get_item_type, get_item_title, normalize_title):
    
    from resources.lib.db import get_series_representative, load_items_by_keys, count_episodes_for_series
    
    xbmcplugin.setContent(handle, 'movies')
    hidden_items = po.get('hidden', [])
    manual_items = po.get('manual', {})
    shown = 0

    # 0. Inyectar ítems añadidos manualmente
    for val, m_item in sorted(manual_items.items(), key=lambda x: x[1].get('added', 0), reverse=True):
        try:
            wtype = m_item.get('wtype')
            wtitle = m_item.get('title')
            
            li = None
            url = None
            isFolder = True
            
            if wtype == 'tv':
                rep = get_series_representative(val)
                if not rep: 
                    li = xbmcgui.ListItem(label=wtitle)
                    apply_info_tag(li, {'title': wtitle, 'mediatype': 'tvshow'})
                else:
                    li = xbmcgui.ListItem(label=rep.get('title') or wtitle)
                    apply_art(li, rep, addon_fanart)
                    apply_info_tag(li, {'title': rep.get('title'), 'plot': rep.get('overview'), 'mediatype': 'tvshow'})
                url = build_url({'action': 'list_seasons', 'series': val})
            elif wtype == 'movie':
                found = load_items_by_keys([val])
                if found:
                    it = found[0]
                    li = xbmcgui.ListItem(label=it.get('title'))
                    apply_art(li, it, addon_fanart)
                    apply_info_tag(li, {'title': it.get('title'), 'plot': it.get('overview'), 'mediatype': 'movie'})
                    url = build_url({'action': 'select', 'key': val})
                    isFolder = False
            
            if li and url:
                is_watched = (wtype == 'movie' and val in played_keys)
                cm = generate_cm(wtype, val, wtitle, is_watched, item_key=val if wtype=='movie' else None)
                if cm: li.addContextMenuItems(cm)
                xbmcplugin.addDirectoryItem(handle, url, li, isFolder)
                shown += 1
        except Exception: pass

    # 1.5. Series en progreso
    try:
        played_items = load_items_by_keys(list(played_keys.keys()))
    except Exception:
        played_items = []

    series_progress = {}
    for it in played_items:
        if get_item_type(it) in ('tv', 'series_documentary'):
            raw_title = get_item_title(it)
            title_norm = normalize_title(raw_title)
            if not title_norm: continue
            
            if title_norm not in series_progress:
                series_progress[title_norm] = {'total': 0, 'watched': 0, 'raw_title': raw_title, 'rep': it, 'last_played': ''}
            
            series_progress[title_norm]['total'] += 1
            item_key = it.get('key')
            if item_key and item_key in played_keys:
                series_progress[title_norm]['watched'] += 1
                lp = played_keys[item_key]
                if lp and lp > series_progress[title_norm]['last_played']:
                    series_progress[title_norm]['last_played'] = lp
                
            if bool(it.get('poster')) and not bool(series_progress[title_norm]['rep'].get('poster')):
                series_progress[title_norm]['rep'] = it

    in_progress_series = []
    for data in series_progress.values():
        total_eps = count_episodes_for_series(data['raw_title'])
        if 0 < data['watched'] < total_eps:
            data['total'] = total_eps
            in_progress_series.append(data)
    
    in_progress_series.sort(key=lambda x: x['raw_title'])
    in_progress_series.sort(key=lambda x: x['last_played'] or '', reverse=True)
    for data in in_progress_series:
        rep = data['rep']
        raw_title = data['raw_title']
        
        if raw_title in hidden_items: continue
        if raw_title in manual_items: continue
        
        li = xbmcgui.ListItem(label=raw_title)
        apply_art(li, rep, addon_fanart)
        
        info = {'title': raw_title, 'plot': rep.get('overview'), 'mediatype': 'tvshow'}
        li.setProperty('TotalEpisodes', str(data['total']))
        li.setProperty('WatchedEpisodes', str(data['watched']))
        li.setProperty('UnWatchedEpisodes', str(data['total'] - data['watched']))
        apply_info_tag(li, info)
        
        is_watched = data['watched'] >= data['total']
        cm = generate_cm('tv', raw_title, raw_title, is_watched, watched_eps=data['watched'], total_eps=data['total'])
        if cm: li.addContextMenuItems(cm)

        url = build_url({'action': 'list_seasons', 'series': raw_title})
        xbmcplugin.addDirectoryItem(handle, url, li, isFolder=True)

    # Bookmarks
    db_path = None
    try:
        try: profile = xbmcvfs.translatePath('special://profile/')
        except Exception: profile = ''
        db_dir = os.path.join(profile, 'Database')
        db_candidates = glob.glob(os.path.join(db_dir, 'MyVideos*.db'))
        if not db_candidates:
            db_candidates = glob.glob(os.path.join(db_dir, '*.db'))
        db_path = sorted(db_candidates, key=lambda p: os.path.getmtime(p), reverse=True)[0] if db_candidates else None
    except Exception as e:
        xbmc.log(f"RusterWolf: error localizando Database de Kodi: {e}", xbmc.LOGERROR)

    bookmarks = []
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT b.idBookmark, b.idFile, b.timeInSeconds, b.totalTimeInSeconds, f.strFilename FROM bookmark b JOIN files f ON b.idFile = f.idFile WHERE f.strFilename LIKE 'plugin://plugin.video.rusterwolf77/%' AND b.type = 1 ORDER BY b.idBookmark DESC LIMIT 200")
            rows = cur.fetchall()
            for row in rows:
                try:
                    idBookmark, idFile, timeInSeconds, totalTimeInSeconds, strFilename = row
                    bookmarks.append({'idBookmark': idBookmark, 'idFile': idFile, 'time': timeInSeconds, 'total': totalTimeInSeconds, 'filename': strFilename})
                except Exception: continue
            conn.close()
        except Exception as e:
            xbmc.log(f"RusterWolf: error leyendo bookmarks de {db_path}: {e}", xbmc.LOGERROR)

    if not bookmarks and not in_progress_series and not manual_items:
        li = xbmcgui.ListItem(label='No hay contenido en progreso')
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle('No hay contenido en progreso')
            info_tag.setPlot(SECTION_PLOTS.get('seguir_viendo', ''))
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo: art_dict['clearlogo'] = section_logo; art_dict['logo'] = section_logo
        try: li.setArt(art_dict)
        except Exception: pass
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.setPluginFanart(handle, addon_fanart)
        xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=False)
        return

    for bm in bookmarks[:50]:
        try:
            filename = bm.get('filename') or ''
            display_title = filename
            catalog_item = None

            try:
                parsed = urllib.parse.urlparse(filename)
                if parsed.scheme == 'plugin' or (parsed.scheme in ('http', 'https') and 'plugin.video.rusterwolf77' in filename):
                    qs = urllib.parse.parse_qs(parsed.query)
                    if 'key' in qs:
                        k = qs.get('key')[0]
                        items = load_items_by_keys([k]) or []
                        catalog_item = items[0] if items else None
            except Exception: pass

            if catalog_item:
                c_key = catalog_item.get('key')
                if c_key in hidden_items or catalog_item.get('title') in hidden_items: continue
                if c_key in manual_items: continue
                display_title = catalog_item.get('title') or display_title
            else:
                continue

            li = xbmcgui.ListItem(label=display_title)
            try:
                art = {'fanart': addon_fanart}
                if isinstance(catalog_item, dict):
                    poster = catalog_item.get('poster') or catalog_item.get('poster_path') or ''
                    if poster: art['poster'] = poster; art['thumb'] = poster
                    fanart = catalog_item.get('fanart') or catalog_item.get('backdrop_path') or ''
                    if fanart: art['fanart'] = fanart
                    clearlogo = catalog_item.get('clearlogo') or catalog_item.get('logo') or ''
                    if clearlogo: art['clearlogo'] = clearlogo; art['logo'] = clearlogo
                li.setArt(art)
            except Exception: pass

            try:
                if isinstance(catalog_item, dict):
                    tag = li.getVideoInfoTag()
                    if catalog_item.get('title'): tag.setTitle(catalog_item.get('title'))
                    plot = catalog_item.get('overview') or catalog_item.get('episode_overview')
                    if plot: tag.setPlot(plot)
                    if catalog_item.get('year'): tag.setYear(int(catalog_item.get('year')))
                    if catalog_item.get('rating'): tag.setRating(float(catalog_item.get('rating')))
            except Exception: pass
            
            li.setProperty('IsPlayable', 'true')

            rm_val = catalog_item.get('key') if catalog_item else filename
            is_watched = catalog_item and catalog_item.get('key') in played_keys
            cm = generate_cm('movie', rm_val, display_title, is_watched, item_key=rm_val)
            if cm: li.addContextMenuItems(cm)

            play_url = filename or ''
            if play_url: xbmcplugin.addDirectoryItem(handle, play_url, li, False)
            else: xbmcplugin.addDirectoryItem(handle, '', li, False)

            shown += 1
            if shown >= 50: break
        except Exception as e:
            xbmc.log(f"RusterWolf: error mostrando bookmark: {e}", xbmc.LOGERROR)

    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True)

def render_favorites(handle, addon_fanart, icon_path, section_logo,
                     wl, played_keys, build_url, apply_info_tag, apply_art, generate_cm):
                     
    from resources.lib.db import get_series_representative, load_items_by_keys, get_series_episodes
    
    xbmcplugin.setContent(handle, 'movies')
    
    if not wl:
        li = xbmcgui.ListItem(label='No hay elementos en Favoritos')
        try:
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle('No hay elementos en Favoritos')
            info_tag.setPlot(SECTION_PLOTS.get('favoritos', ''))
        except Exception: pass
        art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
        if section_logo: art_dict['clearlogo'] = section_logo; art_dict['logo'] = section_logo
        try: li.setArt(art_dict)
        except Exception: pass
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.setPluginFanart(handle, addon_fanart)
        xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=False)
        return

    for uid, witem in sorted(wl.items(), key=lambda x: x[1].get('added', 0), reverse=True):
        try:
            wtype = witem.get('wtype')
            val = witem.get('val')
            wtitle = witem.get('title')
            
            li = None
            url = None
            isFolder = True
            
            if wtype == 'tv':
                rep = get_series_representative(val)
                if not rep: 
                    li = xbmcgui.ListItem(label=wtitle)
                    apply_info_tag(li, {'title': wtitle, 'mediatype': 'tvshow'})
                else:
                    li = xbmcgui.ListItem(label=rep.get('title') or wtitle)
                    apply_art(li, rep, addon_fanart)
                    apply_info_tag(li, {'title': rep.get('title'), 'plot': rep.get('overview'), 'mediatype': 'tvshow'})
                url = build_url({'action': 'list_seasons', 'series': val})
            
            elif wtype == 'movie':
                found = load_items_by_keys([val])
                if found:
                    it = found[0]
                    li = xbmcgui.ListItem(label=it.get('title'))
                    apply_art(li, it, addon_fanart)
                    apply_info_tag(li, {'title': it.get('title'), 'plot': it.get('overview'), 'mediatype': 'movie'})
                    url = build_url({'action': 'select', 'key': val})
                    isFolder = False
                else:
                    li = xbmcgui.ListItem(label=wtitle)
                    url = build_url({'action': 'select', 'key': val})
                    isFolder = False
            
            if li and url:
                is_watched = False
                if wtype == 'movie' and val in played_keys:
                    is_watched = True
                elif wtype == 'tv':
                    try:
                        eps = get_series_episodes(val)
                        if eps and all(e.get('key') in played_keys for e in eps):
                            is_watched = True
                    except: pass
                    
                cm = generate_cm(wtype, val, wtitle, is_watched, item_key=val if wtype=='movie' else None)
                if cm: li.addContextMenuItems(cm)
                xbmcplugin.addDirectoryItem(handle, url, li, isFolder)
        except Exception as e:
            xbmc.log(f"RusterWolf: error en favoritos item: {e}", xbmc.LOGERROR)
            
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)