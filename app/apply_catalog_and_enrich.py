#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply catalog magnets to cache.db and enrich TMDB metadata (es-ES).

Behaviour:
 - Creates a backup copy of cache.db before modifying it.
 - Scans `catalog.json` and for each entry merges missing magnets into the DB row identified by the computed key.
 - Then, for rows that have a tmdb_id, queries TMDB (language es-ES) and writes genres (names), cast (top 10 names), poster/fanart and attempts to pick a clearlogo (first logo) and banner (backdrop) and clearart (poster).
 - Does not remove existing torrents; merges deduplicating by magnet/infohash.

Use from addon root:
  python resources\tools\apply_catalog_and_enrich.py

Warning: this script performs network calls to TMDB and will modify cache.db (backup created).
"""

import os
import sys
import json
import sqlite3
import shutil
import time
import argparse
import urllib.request
import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CATALOG = os.path.join(ROOT, 'catalog.json')
DB_PATH = os.path.join(ROOT, 'cache.db')
SETTINGS_XML = os.path.join(ROOT, 'resources', 'settings.xml')

IMG_W500 = 'https://image.tmdb.org/t/p/w500'
IMG_ORIG = 'https://image.tmdb.org/t/p/original'
LANG = 'es-ES'


def log(msg):
    ts = datetime.datetime.utcnow().isoformat()
    try:
        print(f"[{ts}] {msg}")
    except Exception:
        # fallback
        print(msg)


def read_api_from_settings_xml():
    try:
        if not os.path.exists(SETTINGS_XML):
            return None
        with open(SETTINGS_XML, 'r', encoding='utf-8') as f:
            s = f.read()
        import re
        m = re.search(r'id=["\']tmdb_api_key["\'][^>]*default=["\']([^"\']+)["\']', s)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def tmdb_get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Kodi RusterWolf Addon'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_movie(tmdb_id, api_key):
    url = f'https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}&language={LANG}'
    return tmdb_get_json(url)


def fetch_tv(tmdb_id, api_key):
    url = f'https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={api_key}&language={LANG}'
    return tmdb_get_json(url)


def fetch_credits(kind, tmdb_id, api_key):
    url = f'https://api.themoviedb.org/3/{kind}/{tmdb_id}/credits?api_key={api_key}&language={LANG}'
    return tmdb_get_json(url)


def fetch_episode(tmdb_id, season, episode, api_key):
    url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season}/episode/{episode}?api_key={api_key}&language={LANG}'
    return tmdb_get_json(url)


def fetch_images(kind, tmdb_id, api_key):
    url = f'https://api.themoviedb.org/3/{kind}/{tmdb_id}/images?api_key={api_key}&include_image_language=es,null'
    return tmdb_get_json(url)


def try_translations(kind, tmdb_id, season=None, episode=None, api_key=None):
    try:
        if kind == 'movie':
            url = f'https://api.themoviedb.org/3/movie/{tmdb_id}/translations?api_key={api_key}'
        elif kind == 'tv' and season is None:
            url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/translations?api_key={api_key}'
        else:
            url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season}/episode/{episode}/translations?api_key={api_key}'
        data = tmdb_get_json(url)
        translations = data.get('translations') or []
        for t in translations:
            if t.get('iso_639_1') == 'es' and isinstance(t.get('data'), dict):
                return t.get('data')
    except Exception:
        pass
    return {}


def clean_title_for_key(title):
    import re
    if not title:
        return ''
    s = str(title)
    s = re.sub(r'\b(1080p|720p|2160p|4k|hd|hdtv|bluray|webrip|webdl|remux|subesp|latam|multi)\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[\[\]\(\)\{\}]', '', s)
    s = s.strip()
    s = s.replace('/', ' ')
    s = re.sub(r'[^0-9a-zA-Z\- ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def make_key_for_row(parsed, tmdb_top=None):
    # parsed: dict with keys like type, season, episode, title, year
    title = parsed.get('title') or parsed.get('series') or ''
    title = clean_title_for_key(title)
    if parsed.get('type') in ('series', 'tv') or ('season' in parsed or 'episode' in parsed):
        season = str(parsed.get('season') or '')
        episode = str(parsed.get('episode') or '')
        return f"tv_{title}_{season}_{episode}"
    else:
        year = str(parsed.get('year') or '')
        return f"movie_{title}_{year}"


def normalize_catalog_torrents(torrents):
    out = []
    for t in (torrents or []):
        if isinstance(t, dict):
            q = t.get('quality') or t.get('quality_label') or ''
            m = t.get('magnet') or t.get('uri') or t.get('url') or ''
            ih = t.get('infohash') or ''
            if not m and ih:
                m = f'magnet:?xt=urn:btih:{ih}'
            out.append({'quality': q or '', 'magnet': m or '', 'infohash': ih or ''})
    return out


def merge_torrents(existing, new):
    # existing/new: lists of dicts with 'magnet' or 'infohash'
    seen = set()
    merged = []
    def key_of(t):
        return (t.get('magnet') or t.get('infohash') or '').strip()
    for t in (existing or []) + (new or []):
        if not isinstance(t, dict):
            continue
        k = key_of(t)
        if not k:
            # keep items without magnet/infohash (rare)
            merged.append(t)
            continue
        if k in seen:
            continue
        seen.add(k)
        merged.append(t)
    return merged


def backup_db(db_path):
    if not os.path.exists(db_path):
        return None
    ts = time.strftime('%Y%m%d%H%M%S')
    dst = db_path + f'.bak.{ts}'
    shutil.copy2(db_path, dst)
    return dst


def apply_magnets_from_catalog(catalog_path, db_path, out_no_tmdb=None):
    if not os.path.exists(catalog_path):
        log('catalog.json not found at ' + catalog_path)
        return 0, []
    with open(catalog_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results') if isinstance(data, dict) else []

    # Split results: those with tmdb_id and those without
    with_tmdb = []
    without_tmdb = []
    for entry in results:
        tm = (entry.get('tmdb_top') or {}).get('id')
        if tm:
            with_tmdb.append(entry)
        else:
            without_tmdb.append(entry)

    # write no-tmdb items to separate json if requested
    if out_no_tmdb:
        try:
            with open(out_no_tmdb, 'w', encoding='utf-8') as f:
                json.dump(without_tmdb, f, ensure_ascii=False, indent=2)
            log(f'Wrote {len(without_tmdb)} items without tmdb to {out_no_tmdb}')
        except Exception as e:
            log('Failed writing no-tmdb file: ' + str(e))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    updated = 0
    total = len(with_tmdb)
    log(f'Applying magnets from catalog for items WITH tmdb: {total} entries')
    for i, entry in enumerate(with_tmdb, 1):
        parsed = entry.get('parsed') or {}
        key = entry.get('key') or make_key_for_row(parsed)
        # normalize catalog torrents
        catalog_torrents = normalize_catalog_torrents(entry.get('torrents') or [])
        if not catalog_torrents:
            continue
        cur.execute('SELECT torrents FROM items WHERE "key"=?', (key,))
        row = cur.fetchone()
        if not row:
            # no DB row for this key; skip
            continue
        try:
            existing = json.loads(row[0]) if row[0] else []
        except Exception:
            existing = []
        merged = merge_torrents(existing, catalog_torrents)
        if len(merged) != len(existing):
            cur.execute('UPDATE items SET torrents=? WHERE "key"=?', (json.dumps(merged, ensure_ascii=False), key))
            updated += 1
        if i % 500 == 0:
            conn.commit()
            log(f'  processed {i}/{total} catalog entries, magnets updated so far: {updated}')
    conn.commit()
    conn.close()
    log(f'Finished applying magnets: {updated} rows updated, {len(without_tmdb)} items without tmdb moved')
    return updated, without_tmdb


def enrich_from_tmdb(db_path, api_key, delay=0.25):
    if not api_key:
        print('TMDB API key required')
        return 0
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # select rows that have tmdb_id (non-empty)
    cur.execute('SELECT "key", type, season, episode, tmdb_id FROM items WHERE tmdb_id IS NOT NULL AND TRIM(tmdb_id)<>""')
    rows = cur.fetchall()
    total = len(rows)
    log(f'Enriching {total} items from TMDB (es-ES)')
    processed = 0
    updated = 0
    for r in rows:
        key, typ, season, episode, tmdb_id = r
        processed += 1
        # check existing metadata and skip if already complete
        try:
            cur2 = conn.cursor()
            cur2.execute('SELECT overview, poster, fanart, genres, "cast", clearlogo, banner, clearart, episode_title, episode_overview, still_path FROM items WHERE "key"=?', (key,))
            existing_row = cur2.fetchone()
            if existing_row:
                overview_e, poster_e, fanart_e, genres_e, cast_e, clearlogo_e, banner_e, clearart_e, ep_title_e, ep_overview_e, still_e = existing_row
                has_overview = bool(overview_e and str(overview_e).strip())
                has_poster = bool(poster_e and str(poster_e).strip())
                has_fanart = bool(fanart_e and str(fanart_e).strip())
                try:
                    has_genres = bool(json.loads(genres_e)) if genres_e else False
                except Exception:
                    has_genres = bool(genres_e)
                try:
                    has_cast = bool(json.loads(cast_e)) if cast_e else False
                except Exception:
                    has_cast = bool(cast_e)
                has_logo = bool(clearlogo_e or banner_e or clearart_e)
                # for TV also check episode metadata
                has_episode = True
                if typ == 'tv' and season is not None and episode is not None:
                    has_episode = bool(ep_title_e and str(ep_title_e).strip()) and bool(ep_overview_e and str(ep_overview_e).strip())
                # if all fields present, skip this item
                if has_overview and has_poster and has_fanart and has_genres and has_cast and has_logo and has_episode:
                    if processed % 200 == 0:
                        log(f'  skipped {processed}/{total} (already complete)')
                    continue
        except Exception:
            pass
        try:
            if typ == 'movie':
                data = fetch_movie(tmdb_id, api_key)
                genres = [g.get('name') for g in (data.get('genres') or [])]
                credits = fetch_credits('movie', tmdb_id, api_key)
                cast = [c.get('name') for c in (credits.get('cast') or [])[:10]]
                poster = IMG_W500 + data.get('poster_path') if data.get('poster_path') else ''
                fanart = IMG_ORIG + data.get('backdrop_path') if data.get('backdrop_path') else ''
                # try translations if overview missing
                overview = data.get('overview')
                if not overview:
                    tr = try_translations('movie', tmdb_id, api_key=api_key)
                    overview = tr.get('overview') or overview
                # images
                try:
                    imgs = fetch_images('movie', tmdb_id, api_key)
                    clearlogo = ''
                    banner = ''
                    # logos
                    logos = imgs.get('logos') or []
                    for l in logos:
                        if l.get('file_path'):
                            clearlogo = IMG_ORIG + l.get('file_path')
                            break
                    # backdrops
                    bds = imgs.get('backdrops') or []
                    if bds and bds[0].get('file_path'):
                        banner = IMG_ORIG + bds[0].get('file_path')
                except Exception:
                    clearlogo = ''
                    banner = ''
                clearart = poster or ''
                # update only non-empty fields and preserve others
                cur.execute('''UPDATE items SET genres=?, "cast"=?, poster=?, fanart=?, clearlogo=?, banner=?, clearart=?, overview=? WHERE "key"=?''', (
                    json.dumps(genres, ensure_ascii=False), json.dumps(cast, ensure_ascii=False), poster, fanart, clearlogo, banner, clearart, overview or '', key
                ))
                updated += 1
            else:
                data = fetch_tv(tmdb_id, api_key)
                genres = [g.get('name') for g in (data.get('genres') or [])]
                credits = fetch_credits('tv', tmdb_id, api_key)
                cast = [c.get('name') for c in (credits.get('cast') or [])[:10]]
                poster = IMG_W500 + data.get('poster_path') if data.get('poster_path') else ''
                fanart = IMG_ORIG + data.get('backdrop_path') if data.get('backdrop_path') else ''
                # images
                try:
                    imgs = fetch_images('tv', tmdb_id, api_key)
                    clearlogo = ''
                    banner = ''
                    for l in (imgs.get('logos') or []):
                        if l.get('file_path'):
                            clearlogo = IMG_ORIG + l.get('file_path')
                            break
                    bds = imgs.get('backdrops') or []
                    if bds and bds[0].get('file_path'):
                        banner = IMG_ORIG + bds[0].get('file_path')
                except Exception:
                    clearlogo = ''
                    banner = ''
                clearart = poster or ''
                # episode specific
                ep_title = ''
                ep_overview = ''
                still = ''
                if season is not None and episode is not None:
                    try:
                        ep = fetch_episode(tmdb_id, int(season), int(episode), api_key)
                        ep_title = ep.get('name') or ''
                        ep_overview = ep.get('overview') or ''
                        if not ep_overview:
                            ttr = try_translations('tv', tmdb_id, season=int(season), episode=int(episode), api_key=api_key)
                            ep_overview = ttr.get('overview') or ep_overview
                        if ep.get('still_path'):
                            still = IMG_W500 + ep.get('still_path')
                    except Exception:
                        pass
                cur.execute('''UPDATE items SET genres=?, "cast"=?, poster=?, fanart=?, clearlogo=?, banner=?, clearart=?, episode_title=?, episode_overview=?, still_path=?, overview=? WHERE "key"=?''', (
                    json.dumps(genres, ensure_ascii=False), json.dumps(cast, ensure_ascii=False), poster, fanart, clearlogo, banner, clearart, ep_title, ep_overview, still, data.get('overview') or '', key
                ))
                updated += 1
        except Exception as e:
            log(f'Error enriching {key}: {e}')
        if processed % 50 == 0:
            conn.commit()
            log(f'  enriched {processed}/{total}, updated {updated}')
        time.sleep(delay)
    conn.commit()
    conn.close()
    log(f'Enrichment done: processed={processed} updated={updated}')
    return updated


def enrich_catalog_json_posters(catalog_path, api_key, delay=0.25):
    """Rellena poster_url/backdrop_url/overview en catalog.json para items que tengan tmdb_top.id pero no poster/backdrop."""
    if not os.path.exists(catalog_path):
        log('catalog.json not found at ' + catalog_path)
        return 0
    with open(catalog_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = data.get('results') or []
    updated = 0
    for i, entry in enumerate(results, 1):
        tmdb_top = entry.get('tmdb_top') or {}
        tid = tmdb_top.get('id')
        if not tid:
            continue
        poster = tmdb_top.get('poster_url') or tmdb_top.get('poster_path')
        backdrop = tmdb_top.get('backdrop_url') or tmdb_top.get('backdrop_path')
        # normalize
        if poster and poster.startswith('/'):
            poster = IMG_W500 + poster
        if backdrop and backdrop.startswith('/'):
            backdrop = IMG_ORIG + backdrop
        if poster and backdrop:
            continue
        # fetch details from TMDB
        try:
            kind = 'movie' if (entry.get('parsed') or {}).get('type') == 'movie' else 'tv'
            if kind == 'movie':
                data_tm = fetch_movie(tid, api_key)
            else:
                data_tm = fetch_tv(tid, api_key)
            if not data_tm:
                continue
            if not poster and data_tm.get('poster_path'):
                tmdb_top['poster_path'] = data_tm.get('poster_path')
                tmdb_top['poster_url'] = IMG_W500 + data_tm.get('poster_path')
                poster = tmdb_top['poster_url']
            if not backdrop and data_tm.get('backdrop_path'):
                tmdb_top['backdrop_path'] = data_tm.get('backdrop_path')
                tmdb_top['backdrop_url'] = IMG_ORIG + data_tm.get('backdrop_path')
                backdrop = tmdb_top['backdrop_url']
            # try translations for overview in spanish if missing
            if not tmdb_top.get('overview'):
                tr = try_translations(kind, tid, api_key=api_key)
                if tr and tr.get('overview'):
                    tmdb_top['overview'] = tr.get('overview')
            entry['tmdb_top'] = tmdb_top
            updated += 1
        except Exception as e:
            print('Error fetching tmdb for', tid, e)
        if i % 200 == 0:
            # periodic save
            with open(catalog_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log(f'  progress: processed {i}/{len(results)} entries, updated so far: {updated}')
        time.sleep(delay)
    # final save
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log('Catalog enrichment done, updated: ' + str(updated))
    return updated


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', default=CATALOG)
    p.add_argument('--db', default=DB_PATH)
    p.add_argument('--api-key', default=None)
    p.add_argument('--delay', type=float, default=0.25)
    args = p.parse_args()

    if not os.path.exists(args.db):
        print('DB not found at', args.db)
        sys.exit(1)

    bak = backup_db(args.db)
    if bak:
        print('DB backed up to', bak)

    # Apply magnets but separate items without tmdb
    out_no_tmdb = os.path.join(os.path.dirname(args.catalog), 'no_tmdb_items.json')
    n1, without_tmdb = apply_magnets_from_catalog(args.catalog, args.db, out_no_tmdb)

    api = args.api_key or read_api_from_settings_xml()
    if not api:
        print('TMDB API key not found in settings.xml and not provided with --api-key; skipping TMDB enrichment')
        sys.exit(0)

    # First enrich catalog.json posters/backdrops (so both catalog.json and DB get same info)
    n_catalog_updates = enrich_catalog_json_posters(args.catalog, api, delay=args.delay)

    # Now update DB using existing enrichment (this will set genres, cast, poster, fanart, etc.)
    n2 = enrich_from_tmdb(args.db, api, delay=args.delay)

    print(f'Done. magnets_added_rows={n1}, catalog_tmdb_updates={n_catalog_updates}, tmdb_updated_rows={n2}, no_tmdb_moved={len(without_tmdb)}')


if __name__ == '__main__':
    main()
