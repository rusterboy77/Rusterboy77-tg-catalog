#!/usr/bin/env python3
import os, json, urllib.request, sys
KEY = os.environ.get('TMDB_API_KEY')
if not KEY:
    print('ERROR: TMDB_API_KEY not set in environment')
    sys.exit(2)

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'tg-catalog-check'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

ID = 259909
IMG_W500 = 'https://image.tmdb.org/t/p/w500'
IMG_ORIG = 'https://image.tmdb.org/t/p/original'

for kind in ('movie','tv'):
    print('\n===', kind, '===')
    try:
        url = f'https://api.themoviedb.org/3/{kind}/{ID}?api_key={KEY}&language=es-ES'
        d = get_json(url)
        title = d.get('title') or d.get('name')
        print('title:', title)
        poster_path = d.get('poster_path')
        backdrop_path = d.get('backdrop_path')
        print('poster_path:', poster_path)
        print('poster_url:', IMG_W500 + poster_path if poster_path else None)
        print('backdrop_path:', backdrop_path)
        print('backdrop_url:', IMG_ORIG + backdrop_path if backdrop_path else None)
    except Exception as e:
        print('details error:', e)
    try:
        url2 = f'https://api.themoviedb.org/3/{kind}/{ID}/images?api_key={KEY}&include_image_language=es,null'
        j2 = get_json(url2)
        logos = j2.get('logos') or []
        bds = j2.get('backdrops') or []
        posters = j2.get('posters') or []
        print('logos count:', len(logos))
        if logos:
            print('logo[0].file_path:', logos[0].get('file_path'))
            print('logo[0].full_url:', IMG_ORIG + logos[0].get('file_path'))
        print('backdrops count:', len(bds))
        if bds:
            print('backdrop[0].file_path:', bds[0].get('file_path'))
            print('backdrop[0].full_url:', IMG_ORIG + bds[0].get('file_path'))
        print('posters count:', len(posters))
        if posters:
            print('poster[0].file_path:', posters[0].get('file_path'))
            print('poster[0].full_url:', IMG_W500 + posters[0].get('file_path'))
    except Exception as e:
        print('images error:', e)

print('\nDone')
