#!/usr/bin/env python3
import os, json, sqlite3, datetime, urllib.request, tempfile

KEY = os.environ.get('TMDB_API_KEY')
if not KEY:
    print('TMDB_API_KEY not set in env; abort')
    raise SystemExit(2)

IMG_W500 = 'https://image.tmdb.org/t/p/w500'
IMG_ORIG = 'https://image.tmdb.org/t/p/original'

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'tg-catalog-sim'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def build_tm_for_id(tmdb_id, kind_prefer='movie'):
    # Simulate enrich_with_tmdb_if_needed: try kinds order depending on prefer
    kinds = (('movie','tv') if kind_prefer=='movie' else ('tv','movie'))
    for kind in kinds:
        # search not needed if we have id; directly call detail
        try:
            item_full = get_json(f'https://api.themoviedb.org/3/{kind}/{tmdb_id}?api_key={KEY}&language=es-ES')
        except Exception as e:
            print('detail error', kind, e)
            continue
        try:
            rc = get_json(f'https://api.themoviedb.org/3/{kind}/{tmdb_id}/images?api_key={KEY}&include_image_language=es,null')
        except Exception as e:
            print('images error', kind, e); rc = {}
        # build tm object like main.py
        tmdb_top = {}
        tmdb_top['id'] = item_full.get('id')
        tmdb_top['title'] = item_full.get('title') or item_full.get('name')
        tmdb_top['overview'] = item_full.get('overview')
        # prefer item_full paths
        poster_path_used = item_full.get('poster_path')
        backdrop_path_used = item_full.get('backdrop_path')
        poster_url = IMG_W500 + (poster_path_used or '')
        backdrop_url = IMG_ORIG + (backdrop_path_used or '')
        genres = [g.get('name') for g in (item_full.get('genres') or [])]
        # cast
        try:
            credits = get_json(f'https://api.themoviedb.org/3/{kind}/{tmdb_id}/credits?api_key={KEY}&language=es-ES')
            cast = [c.get('name') for c in (credits.get('cast') or [])[:10] if c.get('name')]
        except Exception:
            cast = []
        clearlogo = ''
        banner = ''
        try:
            logos = rc.get('logos') or []
            if logos and logos[0].get('file_path'):
                clearlogo = IMG_ORIG + logos[0].get('file_path')
            bds = rc.get('backdrops') or []
            if bds and bds[0].get('file_path'):
                banner = IMG_ORIG + bds[0].get('file_path')
            clearart = poster_url or ''
        except Exception:
            clearlogo=''; banner=''; clearart=poster_url or ''
        tmdb_top['poster_url'] = poster_url
        tmdb_top['backdrop_url'] = backdrop_url
        tmdb_top['genres'] = genres
        tmdb_top['cast'] = cast
        tmdb_top['clearlogo'] = clearlogo
        tmdb_top['banner'] = banner
        tmdb_top['clearart'] = clearart
        # return tm and which kind succeeded
        return tmdb_top, kind
    return {}, None


def simulate_upsert(tm, title, existing_row=None):
    # replicate the upsert logic from main.py for movie, preserving existing values
    existing = existing_row or {}
    poster = tm.get('poster_url') if tm.get('poster_url') else (existing.get('poster') if existing else '')
    fanart = tm.get('backdrop_url') if tm.get('backdrop_url') else (existing.get('fanart') if existing else '')
    clearlogo = tm.get('clearlogo') if tm.get('clearlogo') else (existing.get('clearlogo') if existing else '')
    banner = tm.get('banner') if tm.get('banner') else (existing.get('banner') if existing else '')
    clearart = tm.get('clearart') if tm.get('clearart') else (existing.get('clearart') if existing else '')
    overview = tm.get('overview') if tm.get('overview') else (existing.get('overview') if existing else '')
    genres = tm.get('genres') if tm.get('genres') is not None else (json.loads(existing.get('genres')) if existing and existing.get('genres') else [])
    cast = tm.get('cast') if tm.get('cast') is not None else (json.loads(existing.get('cast')) if existing and existing.get('cast') else [])
    item = {
        'title': title,
        'type': 'movie',
        'year':'',
        'tmdb_id': tm.get('id') or '',
        'poster': poster or '',
        'fanart': fanart or '',
        'clearlogo': clearlogo or '',
        'banner': banner or '',
        'clearart': clearart or '',
        'overview': overview or '',
        'genres': json.dumps(genres, ensure_ascii=False),
        'cast': json.dumps(cast, ensure_ascii=False),
        'torrents': json.dumps([]),
        'date_added': datetime.datetime.utcnow().isoformat(),
        'enriched': 1
    }
    return item


def run_sim():
    tm, kind = build_tm_for_id(259909, kind_prefer='movie')
    print('TM kind used:', kind)
    print('tm clearlogo:', tm.get('clearlogo'))
    # create temp DB and insert an existing row with clearlogo set
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    db = tmp.name
    print('Using temp DB:', db)
    conn = sqlite3.connect(db); c = conn.cursor()
    c.executescript('''CREATE TABLE items ("key" TEXT PRIMARY KEY, title TEXT, type TEXT, year TEXT, season TEXT, episode TEXT, tmdb_id TEXT, poster TEXT, fanart TEXT, clearlogo TEXT, banner TEXT, clearart TEXT, overview TEXT, episode_title TEXT, episode_overview TEXT, still_path TEXT, genres TEXT, "cast" TEXT, torrents TEXT, date_added TEXT, enriched INTEGER DEFAULT 0);''')
    # insert existing row with clearlogo
    existing = ('movie_test', 'Test Movie', 'movie', '2020', None, None, '259909', 'https://example/poster.jpg', 'https://example/backdrop.jpg', 'https://example/clearlogo.png', 'https://example/banner.jpg', 'https://example/clearart.jpg', 'overview', '', '', '', json.dumps(['Drama']), json.dumps(['Actor']), json.dumps([]), datetime.datetime.utcnow().isoformat(), 1)
    c.execute('INSERT INTO items ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, overview, episode_title, episode_overview, still_path, genres, "cast", torrents, date_added, enriched) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', existing)
    conn.commit()
    # read back existing
    c.execute('SELECT * FROM items WHERE "key"=?', ('movie_test',))
    row = c.fetchone(); print('Existing row clearlogo:', row[9])
    # simulate upsert using tm
    item = simulate_upsert(tm, 'Test Movie', existing_row={'poster':row[7],'fanart':row[8],'clearlogo':row[9],'banner':row[10],'clearart':row[11],'overview':row[12],'genres':row[16],'cast':row[17]})
    print('Upsert item clearlogo:', item['clearlogo'])
    # perform DB INSERT OR REPLACE
    c.execute('INSERT OR REPLACE INTO items ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, overview, episode_title, episode_overview, still_path, genres, "cast", torrents, date_added, enriched) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
        'movie_test', item['title'], item['type'], item['year'], None, None, item['tmdb_id'], item['poster'], item['fanart'], item['clearlogo'], item['banner'], item['clearart'], item['overview'], '', '', '', item['genres'], item['cast'], item['torrents'], item['date_added'], item['enriched']
    ))
    conn.commit()
    c.execute('SELECT * FROM items WHERE "key"=?', ('movie_test',))
    newrow = c.fetchone(); print('After upsert clearlogo:', newrow[9])
    conn.close()

if __name__ == '__main__':
    run_sim()
