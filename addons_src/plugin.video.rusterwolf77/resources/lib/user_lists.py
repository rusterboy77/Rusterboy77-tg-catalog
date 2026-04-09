# -*- coding: utf-8 -*-
import os, glob, sqlite3, urllib.parse, time, json
import xbmc, xbmcgui, xbmcplugin, xbmcvfs, xbmcaddon

SECTION_PLOTS = {
    'seguir_viendo': '¿Por dónde íbamos? Retoma tus capítulos y películas exactamente en el segundo que las dejaste.',
    'favoritos': 'Tu cámara acorazada personal. Todo el contenido que te ha robado el corazón, guardado a buen recaudo.'
}

def _render_empty_state(handle, addon_fanart, icon_path, section_logo, label_text, plot_key):
    li = xbmcgui.ListItem(label=label_text)
    try:
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(label_text)
        info_tag.setPlot(SECTION_PLOTS.get(plot_key, ''))
    except Exception: pass
    art_dict = {'fanart': addon_fanart, 'icon': icon_path, 'thumb': icon_path}
    if section_logo: art_dict['clearlogo'] = section_logo; art_dict['logo'] = section_logo
    try: li.setArt(art_dict)
    except Exception: pass
    xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=False)

def render_continue_watching(handle, addon_fanart, icon_path, section_logo,
                             po, played_keys, resume_points,
                             build_url, apply_info_tag, apply_art, generate_cm,
                             get_item_type, get_item_title, normalize_title):
    
    from resources.lib.db import _connect, load_items_by_keys
    
    xbmcplugin.setContent(handle, 'movies')
    hidden_items = po.get('hidden', [])
    manual_items = po.get('manual', {})
    
    conn = _connect()
    c = conn.cursor()
    
    display_items = []
    json_changed = False
    
    def _parse_sort_time(t_str):
        if not t_str: return 0.0
        try: return float(t_str)
        except Exception: pass
        try:
            return time.mktime(time.strptime(str(t_str), "%Y-%m-%d %H:%M:%S"))
        except Exception: return 0.0
        
    try:
        all_active_keys = list(played_keys.keys()) + list(resume_points.keys())
        active_tv_titles = set()
        active_movie_keys = set()
        
        if all_active_keys:
            for i in range(0, len(all_active_keys), 900):
                batch = all_active_keys[i:i+900]
                placeholders = ','.join('?' for _ in batch)
                c.execute(f'SELECT "key", title, type FROM items WHERE "key" IN ({placeholders})', batch)
                for r in c.fetchall():
                    k, t, itype = r
                    if itype in ('tv', 'series_documentary'):
                        if t: active_tv_titles.add(t)
                    else:
                        active_movie_keys.add(k)
                        
        for k, v in manual_items.items():
            if v.get('wtype') == 'tv': active_tv_titles.add(v.get('title'))
            elif v.get('wtype') == 'movie' and k not in hidden_items: active_movie_keys.add(k)
                    
        active_tv_titles = {t for t in active_tv_titles if normalize_title(t) not in hidden_items}

        series_data = {}
        if active_tv_titles:
            titles_list = list(active_tv_titles)
            for i in range(0, len(titles_list), 900):
                batch = titles_list[i:i+900]
                placeholders = ','.join('?' for _ in batch)
                c.execute(f'SELECT "key", title, season, episode FROM items WHERE title IN ({placeholders})', batch)
                
                for r in c.fetchall():
                    key, t, season, episode = r
                    if not t: continue
                    tn = normalize_title(t)
                    if tn not in series_data:
                        series_data[tn] = {'title': t, 'episodes': []}
                    series_data[tn]['episodes'].append({'key': key, 'season': int(season) if season and str(season).isdigit() else 0, 'episode': int(episode) if episode and str(episode).isdigit() else 0})
            
        target_keys = []
        display_episodes_meta = {}
        
        for tn, s_data in series_data.items():
            eps = sorted(s_data['episodes'], key=lambda x: (int(x.get('season') or 0), int(x.get('episode') or 0)))
            bookmarked = []
            watched = []
            for ep in eps:
                ident = ep.get('key')
                if ident in resume_points: 
                    bookmarked.append(ep)
                elif ident in played_keys: 
                    watched.append(ep)
            
            target_ep = None
            if bookmarked:
                target_ep = bookmarked[-1]
            elif watched:
                last_watched = watched[-1]
                try:
                    idx = eps.index(last_watched)
                    if idx + 1 < len(eps): target_ep = eps[idx + 1]
                except Exception: pass
            elif tn in manual_items:
                target_ep = eps[0] if eps else None
                
            if target_ep is None and tn in manual_items and watched:
                del po['manual'][tn]
                json_changed = True
                
            if target_ep:
                ident = target_ep.get('key')
                sort_time = "0.0"
                if ident in resume_points: sort_time = resume_points[ident].get('last_played') or "0.0"
                elif watched:
                    last_ident = watched[-1].get('key')
                    sort_time = played_keys.get(last_ident, "0.0")
                elif tn in manual_items: sort_time = str(manual_items[tn].get('added', 0))
                    
                target_keys.append(ident)
                display_episodes_meta[ident] = {'series_info': s_data, 'tn': tn, 'sort_time': sort_time}
    except Exception as e:
        import xbmc
        xbmc.log(f"RusterWolf: Error procesando Up Next series: {e}", xbmc.LOGERROR)

    try:
        needed_movie_keys = list(active_movie_keys)
    except Exception as e:
        import xbmc
        xbmc.log(f"RusterWolf: Error procesando Up Next movies: {e}", xbmc.LOGERROR)
        
    conn.close()
    
    all_needed_keys = target_keys + needed_movie_keys
    items_full = load_items_by_keys(all_needed_keys) if all_needed_keys else []
    
    for item in items_full:
        ident = item.get('key')
        itype = get_item_type(item)
        
        if itype in ('tv', 'series_documentary'):
            meta = display_episodes_meta.get(ident)
            if not meta: continue
            display_items.append({
                'type': 'episode',
                'item': item,
                'series_info': meta['series_info'],
                'tn': meta['tn'],
                'sort_time': meta['sort_time']
            })
        else:
            is_manual = ident in manual_items
            is_resumed = ident in resume_points
            if ident in played_keys and not is_resumed:
                if is_manual:
                    del po['manual'][ident]
                    json_changed = True
                continue
                
            sort_time = str(resume_points[ident].get('last_played') or "0.0") if is_resumed else str(manual_items.get(ident, {}).get('added', 0))
            display_items.append({
                'type': 'movie',
                'item': item,
                'ident': ident,
                'sort_time': sort_time
            })
            
    if json_changed:
        pf = os.path.join(xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile')), 'progress_override.json')
        try:
            with open(pf, 'w', encoding='utf-8') as f:
                json.dump(po, f, ensure_ascii=False, indent=2)
        except Exception:
            try:
                vf = xbmcvfs.File(pf, 'w')
                vf.write(json.dumps(po, ensure_ascii=False, indent=2))
                vf.close()
            except Exception: pass
    
    display_items.sort(key=lambda x: _parse_sort_time(x['sort_time']), reverse=True)
    
    if not display_items:
        _render_empty_state(handle, addon_fanart, icon_path, section_logo, 'No hay contenido en progreso', 'seguir_viendo')
        return
        
    dir_items = []
    for di in display_items:
        if di['type'] == 'episode':
            ep = di['item']
            series = di['series_info']
            tn = di['tn']
            season = ep.get('season') or 0
            episode = ep.get('episode') or 0
            
            ep_title = ep.get('episode_title') or ep.get('title') or f"Episodio {episode}"
            display_title = f"{series['title']} S{str(season).zfill(2)}E{str(episode).zfill(2)}"
            
            li = xbmcgui.ListItem(label=display_title)
            info = {
                'title': ep_title,
                'tvshowtitle': series['title'],
                'season': int(season) if str(season).isdigit() else None,
                'episode': int(episode) if str(episode).isdigit() else None,
                'plot': ep.get('episode_overview') or ep.get('overview') or series.get('overview', ''),
                'mediatype': 'episode'
            }
            
            ident = ep.get('key')
            is_watched = False
            if ident in played_keys:
                info['playcount'] = 1
                is_watched = True
            if ident in resume_points:
                info['resume_time'] = resume_points[ident]['time']
                info['resume_total'] = resume_points[ident]['total']
                
            apply_info_tag(li, info)
            
            art = {'fanart': addon_fanart}
            poster = ep.get('still_path') or ep.get('poster') or series.get('poster')
            if poster: art['poster'] = poster; art['thumb'] = poster
            fanart = ep.get('fanart') or series.get('fanart')
            if fanart: art['fanart'] = fanart
            clearlogo = ep.get('clearlogo') or series.get('clearlogo')
            if clearlogo: art['clearlogo'] = clearlogo; art['logo'] = clearlogo
            
            try: li.setArt(art)
            except Exception: pass
            
            li.setProperty('IsPlayable', 'true')
            
            cm = generate_cm('tv', tn, series['title'], is_watched, watched_eps=1, total_eps=2, item_key=ident)
            if cm: li.addContextMenuItems(cm)
            
            url = build_url({'action': 'select', 'key': ident})
            dir_items.append((url, li, False))
            
        else:
            m = di['item']
            ident = di['ident']
            
            li = xbmcgui.ListItem(label=m.get('title'))
            info = {
                'title': m.get('title'),
                'year': int(m.get('year')) if m.get('year') and str(m.get('year')).isdigit() else 0,
                'plot': m.get('overview'),
                'mediatype': 'movie'
            }
            
            is_watched = False
            if ident in played_keys:
                info['playcount'] = 1
                is_watched = True
            if ident in resume_points:
                info['resume_time'] = resume_points[ident]['time']
                info['resume_total'] = resume_points[ident]['total']
                
            apply_info_tag(li, info)
            apply_art(li, m, addon_fanart)
            li.setProperty('IsPlayable', 'true')
            
            cm = generate_cm('movie', ident, m.get('title'), is_watched, item_key=ident)
            if cm: li.addContextMenuItems(cm)
            
            url = build_url({'action': 'select', 'key': ident})
            dir_items.append((url, li, False))
    
    xbmcplugin.addDirectoryItems(handle, dir_items)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True)

def render_favorites(handle, addon_fanart, icon_path, section_logo,
                     wl, played_keys, build_url, apply_info_tag, apply_art, generate_cm):
                     
    from resources.lib.db import load_items_by_keys, get_series_episodes, _connect, _row_to_item
    
    xbmcplugin.setContent(handle, 'movies')
    
    
    if not wl:
        _render_empty_state(handle, addon_fanart, icon_path, section_logo, 'No hay elementos en Favoritos', 'favoritos')
        return

    movie_keys = [witem.get('val') for uid, witem in wl.items() if witem.get('wtype') == 'movie']
    tv_titles = [witem.get('title') for uid, witem in wl.items() if witem.get('wtype') == 'tv']
    
    movies_data = {m['key']: m for m in load_items_by_keys(movie_keys)} if movie_keys else {}
    
    tv_reps = {}
    if tv_titles:
        conn = _connect()
        try:
            c = conn.cursor()
            for i in range(0, len(tv_titles), 900):
                batch = tv_titles[i:i+900]
                placeholders = ','.join('?' for _ in batch)
                c.execute(f'SELECT "key", title, type, year, season, episode, tmdb_id, poster, fanart, overview, episode_title, episode_overview, still_path, clearlogo, banner, clearart, genres, "cast", torrents, date_added, enriched, collection_name, collection_poster, collection_fanart FROM items WHERE type IN ("tv", "series_documentary") AND title IN ({placeholders})', batch)
                for r in c.fetchall():
                    it = _row_to_item(r)
                    t = it.get('title')
                    if t not in tv_reps or (not tv_reps[t].get('poster') and it.get('poster')):
                        tv_reps[t] = it
        finally:
            conn.close()

    dir_items = []
    for uid, witem in sorted(wl.items(), key=lambda x: x[1].get('added', 0), reverse=True):
        try:
            wtype = witem.get('wtype')
            val = witem.get('val')
            wtitle = witem.get('title')
            
            li = None
            url = None
            isFolder = True
            
            if wtype == 'tv':
                rep = tv_reps.get(wtitle)
                if not rep: 
                    li = xbmcgui.ListItem(label=wtitle)
                    apply_info_tag(li, {'title': wtitle, 'mediatype': 'tvshow'})
                else:
                    li = xbmcgui.ListItem(label=rep.get('title') or wtitle)
                    apply_art(li, rep, addon_fanart)
                    apply_info_tag(li, {'title': rep.get('title'), 'plot': rep.get('overview'), 'mediatype': 'tvshow'})
                url = build_url({'action': 'list_seasons', 'series': wtitle})
            
            elif wtype == 'movie':
                it = movies_data.get(val)
                if it:
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
                cm = generate_cm(wtype, val, wtitle, is_watched, item_key=val if wtype=='movie' else None)
                if cm: li.addContextMenuItems(cm)
                dir_items.append((url, li, isFolder))
        except Exception as e:
            xbmc.log(f"RusterWolf: error en favoritos item: {e}", xbmc.LOGERROR)
            
    xbmcplugin.addDirectoryItems(handle, dir_items)
    xbmcplugin.setPluginFanart(handle, addon_fanart)
    xbmcplugin.endOfDirectory(handle)