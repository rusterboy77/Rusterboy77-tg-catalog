#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import requests
import re
import sys
import datetime
import sqlite3
import unicodedata

# Importar rename.py desde el mismo directorio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import rename

# Configuración desde Secrets
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
# Cuentas 1fichier (Soporte multi-cuenta)
ONEFICHIER_ACCOUNTS = []
if os.environ.get('ONEFICHIER_API_KEY') and os.environ.get('ONEFICHIER_FOLDER_ID'):
    ONEFICHIER_ACCOUNTS.append({'key': os.environ.get('ONEFICHIER_API_KEY'), 'folder': os.environ.get('ONEFICHIER_FOLDER_ID')})
if os.environ.get('ONEFICHIER_API_KEY_2') and os.environ.get('ONEFICHIER_FOLDER_ID_2'):
    ONEFICHIER_ACCOUNTS.append({'key': os.environ.get('ONEFICHIER_API_KEY_2'), 'folder': os.environ.get('ONEFICHIER_FOLDER_ID_2')})

# Rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(BASE_DIR, "catalog_choloretro.json")
CACHE_DB_PATH = os.path.join(BASE_DIR, "cache_choloretro.db")

def parse_filename_with_rename(filename):
    """Usa la lógica de rename.py para extraer metadatos."""
    # LIMPIEZA: Eliminar marcas de canales que confunden al parser
    filename = re.sub(r'[@\[\(]?\s*canales?[\s._-]*locos?\s*[\]\)]?', '', filename, flags=re.IGNORECASE)
    # LIMPIEZA: Eliminar sufijos numéricos tipo -021 (ej: Pelicula (1999)-021.mkv)
    filename = re.sub(r'-\d{3}(?=\.\w+$)', '', filename)

    # Reemplazar puntos por espacios para mejorar detección de rename.py
    base = rename.safe_norm(filename.rsplit(".", 1)[0].replace(".", " "))
    base = re.sub(r"wolfmax4k\.com|wolfmax4k\.net", " ", base, flags=re.IGNORECASE)
    base = rename.MULTI_SPACES_RE.sub(" ", base).strip()

    se_match = rename.SEASON_EPISODE_RE.search(base)
    cap_num = None
    if not se_match:
        cap_num = rename.detect_cap_number(base)

    is_series_se = (se_match is not None)
    is_series_cap = (cap_num is not None and cap_num >= 100)
    
    quality = rename.detect_quality(filename)
    
    if is_series_se:
        if se_match.group(1):
            season = int(se_match.group(1))
            episode = int(se_match.group(2))
        else:
            season = int(se_match.group(3))
            episode = int(se_match.group(4))
        title_part = base[:se_match.start()]
        # Si el título está vacío antes del patrón (ej: 1x04 Titulo), no usamos lo que sigue
        # como nombre de serie, ya que probablemente sea el título del episodio.
        title_clean = rename.remove_tokens(title_part).strip()
        year, title_clean = rename.extract_year_and_clean(title_clean)
        return {"type": "series", "series": title_clean, "season": season, "episode": episode, "quality": quality, "year": year}
    elif is_series_cap:
        # Lógica simple para capítulos numéricos (ej. 101 -> S1 E1)
        series_clean = ""
        match = re.search(r'\b' + str(cap_num) + r'\b', base)
        if match:
            title_part = base[:match.start()]
            series_clean = rename.remove_tokens(title_part).strip()
        year, series_clean = rename.extract_year_and_clean(series_clean)
        return {"type": "series", "series": series_clean, "season": cap_num // 100, "episode": cap_num % 100, "quality": quality, "year": year}
    else:
        cleaned = rename.remove_tokens(base)
        year, cleaned_no_year = rename.extract_year_and_clean(cleaned)
        # Devolvemos el título sin normalizar para mejorar la búsqueda en TMDB. La normalización se hará después si es necesaria.
        movie_title = cleaned_no_year.strip()
        return {"type": "movie", "title": movie_title, "year": year or "", "quality": quality}

def get_tmdb_meta(query, is_tv, year=None, manual_id=None):
    """Busca en TMDB y retorna metadatos."""
    if not TMDB_API_KEY: return {}
    
    type_str = 'tv' if is_tv else 'movie'
    tmdb_id = None
    item_basic = {}
    
    try:
        if manual_id:
            tmdb_id = manual_id
            # print(f"  -> Usando ID manual: {tmdb_id}")
        else:
            url = f"https://api.themoviedb.org/3/search/{type_str}"
            params = {'api_key': TMDB_API_KEY, 'query': query, 'language': 'es-ES'}
            if year:
                if is_tv: params['first_air_date_year'] = year
                else: params['year'] = year
            
            # print(f"  -> Buscando en TMDB: query='{query}' year='{year}'")
            r = requests.get(url, params=params)
            results = r.json().get('results', [])
            
            # Fallback: Si no hay resultados, intentar buscando sin acentos/caracteres especiales
            if not results:
                norm_query = ''.join(c for c in unicodedata.normalize('NFD', query) if unicodedata.category(c) != 'Mn')
                if norm_query != query:
                    params['query'] = norm_query
                    r = requests.get(url, params=params)
                    results = r.json().get('results', [])

            if results:
                item_basic = results[0]
                tmdb_id = item_basic.get('id')
            
        if tmdb_id:
            # --- ENRIQUECIMIENTO EXTRA (Detalles, Créditos, Imágenes) ---
            # Esto recupera géneros, actores y clearlogo que faltaban
            genres = []
            cast = []
            clearlogo = ""
            collection = {}
            try:
                details_url = f"https://api.themoviedb.org/3/{type_str}/{tmdb_id}"
                details_params = {'api_key': TMDB_API_KEY, 'language': 'es-ES', 'append_to_response': 'credits,images'}
                r_det = requests.get(details_url, params=details_params, timeout=5)
                if r_det.ok:
                    det = r_det.json()
                    genres = det.get('genres', [])
                    # Cast (Top 10)
                    raw_cast = det.get('credits', {}).get('cast', [])
                    cast = [{'name': c['name'], 'role': c['character'], 'thumbnail': f"https://image.tmdb.org/t/p/w185{c['profile_path']}" if c.get('profile_path') else ""} for c in raw_cast[:10]]
                    # Clearlogo (buscar en imágenes)
                    logos = det.get('images', {}).get('logos', [])
                    # Preferir logo en español, sino el primero
                    logo_match = next((l for l in logos if l.get('iso_639_1') == 'es'), logos[0] if logos else None)
                    if logo_match:
                        clearlogo = f"https://image.tmdb.org/t/p/original{logo_match['file_path']}"
                    
                    if det.get('belongs_to_collection'):
                        coll_data = det['belongs_to_collection']
                        coll_id = coll_data.get('id')
                        coll_logo = ""
                        coll_backdrop = coll_data.get('backdrop_path')
                        try:
                            r_coll = requests.get(f"https://api.themoviedb.org/3/collection/{coll_id}/images", params={'api_key': TMDB_API_KEY})
                            if r_coll.ok:
                                coll_images = r_coll.json()
                                logos = coll_images.get('logos', [])
                                logo_match = next((l for l in logos if l.get('iso_639_1') == 'es'), logos[0] if logos else None)
                                if logo_match:
                                    coll_logo = f"https://image.tmdb.org/t/p/original{logo_match['file_path']}"
                                
                                if not coll_backdrop:
                                    backdrops = coll_images.get('backdrops', [])
                                    if backdrops:
                                        coll_backdrop = backdrops[0]['file_path']
                        except: pass

                        collection = {
                            'id': str(coll_id),
                            'name': coll_data.get('name'),
                            'poster': f"https://image.tmdb.org/t/p/w500{coll_data.get('poster_path')}" if coll_data.get('poster_path') else "",
                            'fanart': f"https://image.tmdb.org/t/p/original{coll_backdrop}" if coll_backdrop else "",
                            'clearlogo': coll_logo
                        }
            except Exception as e:
                print(f"Error enriqueciendo TMDB {tmdb_id}: {e}")

            return {
                'tmdb_id': tmdb_id,
                'title': det.get('name') if is_tv else det.get('title'), # Título oficial desde detalles
                'original_title': det.get('original_name') if is_tv else det.get('original_title'),
                'overview': det.get('overview'),
                'poster_url': f"https://image.tmdb.org/t/p/w500{det.get('poster_path')}" if det.get('poster_path') else "",
                'backdrop_url': f"https://image.tmdb.org/t/p/original{det.get('backdrop_path')}" if det.get('backdrop_path') else "",
                # Campos extra para igualar a RusterWolf
                'vote_average': det.get('vote_average'),
                'release_date': det.get('first_air_date') if is_tv else det.get('release_date'),
                'year': (det.get('first_air_date') if is_tv else det.get('release_date') or "")[:4],
                # Nuevos campos enriquecidos
                'genres': genres,
                'cast': cast,
                'clearlogo': clearlogo,
                'banner': '', 
                'clearart': '',
                'collection': collection
            }
    except Exception as e:
        print(f"Error TMDB: {e}")
    return {}

def get_1fichier_files_recursive(folder_id, headers, ancestors=None, special_root=None):
    """Función auxiliar para recorrer carpetas recursivamente."""
    if ancestors is None:
        ancestors = []
    
    # Detectar si estamos entrando en la carpeta Anime (19385669)
    current_special = special_root
    if str(folder_id) == '19385669':
        current_special = '19385669'
    
    all_files = []
    parent_folder_name = ancestors[-1] if ancestors else None
    
    # 1. Obtener archivos de la carpeta actual
    try:
        r = requests.post("https://api.1fichier.com/v1/file/ls.cgi", json={'folder_id': folder_id}, headers=headers)
        if r.ok:
            items = r.json().get('items', [])
            for item in items:
                item['folder_name'] = parent_folder_name
                item['ancestors'] = ancestors
                # Si estamos bajo la estructura de Anime, forzamos el ID principal
                if current_special == '19385669':
                    item['folder_id'] = '19385669'
                else:
                    item['folder_id'] = str(folder_id)
            all_files.extend(items)
    except Exception as e:
        print(f"Error leyendo archivos en carpeta {folder_id}: {e}")

    # 2. Buscar subcarpetas y entrar en ellas
    try:
        r = requests.post("https://api.1fichier.com/v1/folder/ls.cgi", json={'folder_id': folder_id}, headers=headers)
        if r.ok:
            subfolders = r.json().get('sub_folders', [])
            for sub in subfolders:
                # print(f"  >> Escaneando subcarpeta: {sub['name']}")
                new_ancestors = ancestors + [sub['name']]
                all_files.extend(get_1fichier_files_recursive(sub['id'], headers, ancestors=new_ancestors, special_root=current_special))
    except Exception as e:
        print(f"Error leyendo subcarpetas en {folder_id}: {e}")
        
    return all_files

def get_1fichier_files(api_key, folder_id):
    """Inicia el escaneo recursivo desde la carpeta raíz."""
    if not api_key or not folder_id:
        print("Faltan credenciales de 1fichier")
        return []
        
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    
    print(f"Iniciando escaneo recursivo en 1fichier...")
    return get_1fichier_files_recursive(folder_id, headers)

def update_cache_db(catalog_results):
    """Genera cache_choloretro.db a partir del catálogo completo."""
    print(f"Generando base de datos SQLite en {CACHE_DB_PATH}...")
    
    # Conectar y asegurar esquema (idéntico al del addon)
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS items (
          "key" TEXT PRIMARY KEY,
          title TEXT,
          type TEXT,
          year TEXT,
          season TEXT,
          episode TEXT,
          tmdb_id TEXT,
          poster TEXT,
          fanart TEXT,
          clearlogo TEXT,
          banner TEXT,
          clearart TEXT,
          overview TEXT,
          episode_title TEXT,
          episode_overview TEXT,
          still_path TEXT,
          genres TEXT,
          "cast" TEXT,
          links TEXT,
          date_added TEXT,
          enriched INTEGER DEFAULT 0,
          folder_id TEXT,
          collection_id TEXT,
          collection_name TEXT,
          collection_poster TEXT,
          collection_fanart TEXT,
          collection_clearlogo TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
    ''')
    
    # Migración por si la tabla ya existe sin la columna
    try:
        c.execute("ALTER TABLE items ADD COLUMN folder_id TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE items ADD COLUMN collection_id TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE items ADD COLUMN collection_name TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE items ADD COLUMN collection_poster TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE items ADD COLUMN collection_fanart TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE items ADD COLUMN collection_clearlogo TEXT")
    except:
        pass
    
    # CORRECCIÓN: Limpiar la tabla antes de insertar para borrar items antiguos (ej. Beetlejuice como peli)
    c.execute("DELETE FROM items")

    # Preparar datos
    items_db = []
    for entry in catalog_results:
        parsed = entry.get('parsed', {})
        tmdb = entry.get('tmdb_top', {})
        item_type = parsed.get('type')
        date_added = entry.get('date_added')
        
        # Procesar géneros: convertir {id, name} a lista de nombres
        genres_raw = tmdb.get('genres', [])
        genres = [g['name'] if isinstance(g, dict) else str(g) for g in genres_raw]
        
        # EXCEPCIÓN: Forzar género "Animación" para series que TMDB no etiqueta bien (para que salgan en Dibujos)
        if str(tmdb.get('tmdb_id')) in ['12164', '237897']:
            if "Animación" not in genres: genres.append("Animación")
            if "Animation" not in genres: genres.append("Animation")
        
        # Procesar cast: ya está en formato correcto {name, role, thumbnail}
        cast = tmdb.get('cast', [])
        
        # Procesar colección
        coll = tmdb.get('collection', {})
        coll_id = coll.get('id', '')
        coll_name = coll.get('name', '')
        coll_poster = coll.get('poster', '')
        coll_fanart = coll.get('fanart', '')
        coll_clearlogo = coll.get('clearlogo', '')

        # Campos comunes
        common_vals = [
            str(tmdb.get('tmdb_id') or ''),
            tmdb.get('poster_url'), tmdb.get('backdrop_url'),
            tmdb.get('clearlogo'), tmdb.get('banner'), tmdb.get('clearart'),
            tmdb.get('overview'),
            '', '', '', # episode_title, episode_overview, still_path (pendientes de implementar en TMDB fetch)
            json.dumps(genres, ensure_ascii=False), json.dumps(cast, ensure_ascii=False)
        ]
        
        folder_id = entry.get('folder_id', '')

        if item_type == 'movie':
            links = entry.get('links') or []
            if links:
                # El título en 'parsed' ya no está normalizado, así que lo normalizamos aquí para la clave
                norm_title = rename.normalize_title(parsed.get('title', ''))
                key = f"movie_{norm_title}_{parsed.get('year')}"
                year_val = str(parsed.get('year') or tmdb.get('year') or '')
                items_db.append((key, parsed.get('title'), 'movie', year_val, '', '', *common_vals, json.dumps(links, ensure_ascii=False), date_added, 1, folder_id, coll_id, coll_name, coll_poster, coll_fanart, coll_clearlogo))
        
        elif item_type == 'series':
            for ep in entry.get('episodes', []):
                links = ep.get('links') or []
                if links:
                    key = f"tv_{rename.normalize_title(parsed.get('series', ''))}_{ep.get('season')}_{ep.get('episode')}"
                    year_val = str(parsed.get('year') or tmdb.get('year') or '')
                    
                    # Separar Anime de Series normales: Si viene de la carpeta Anime, cambiamos el tipo a 'anime'
                    final_type = 'tv'
                    if str(folder_id) == '19385669':
                        final_type = 'anime'

                    items_db.append((key, parsed.get('series'), final_type, year_val, str(ep.get('season')), str(ep.get('episode')), *common_vals, json.dumps(links, ensure_ascii=False), date_added, 1, folder_id, coll_id, coll_name, coll_poster, coll_fanart, coll_clearlogo))

    c.executemany('INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', items_db)
    conn.commit()
    conn.close()
    print(f"Base de datos actualizada con {len(items_db)} items.")

def generate():
    print("Iniciando generación de catálogo Choloretro...")
    
    # Cargar catálogo existente para no machacar todo si falla la API
    # Estructura tipo RusterWolf: {"results": [...]}
    catalog = {"results": []}
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
                if "results" not in catalog: catalog = {"results": []}
        except: pass

    # Obtener archivos de 1fichier
    files = []
    for i, acc in enumerate(ONEFICHIER_ACCOUNTS, 1):
        print(f"--- Escaneando Cuenta {i} ---")
        acc_files = get_1fichier_files(acc['key'], acc['folder'])
        files.extend(acc_files)

    if not files:
        print("No se encontraron archivos en ninguna cuenta de 1fichier.")
        return

    # Mapa temporal para agrupar series antes de guardar
    # Clave: Título normalizado
    # CAMBIO: Usar catálogo antiguo SOLO como caché de metadatos (TMDB)
    # para asegurar que se eliminan los archivos que ya no están en 1fichier.
    meta_cache = {}
    for item in catalog["results"]:
        parsed = item.get("parsed", {})
        tmdb = item.get("tmdb_top", {})
        if not tmdb: continue
        if parsed.get("type") == "series":
            title = rename.normalize_title(parsed.get("series") or "")
            meta_cache[f"tv_{title}"] = item
        elif parsed.get("type") == "movie":
            title = rename.normalize_title(parsed.get("title") or "")
            year = parsed.get("year") or ""
            meta_cache[f"movie_{title}_{year}"] = item

    series_map = {}
    new_results = []
    
    for file in files:
        filename = file.get('filename')
        link = file.get('url')
        if not filename or not link: continue
        
        if file.get('pass') == 1:
            pass # print(f"⚠️  AVISO: Archivo protegido con contraseña detectado.")
        
        meta = parse_filename_with_rename(filename)
        quality = meta.get("quality", "SD")
        
        if meta["type"] == "series":
            series_name = meta["series"]
            season = meta["season"]
            episode = meta["episode"]
            year = meta.get("year")
            
            # INTELIGENCIA DE CARPETAS:
            # Si la carpeta tiene el formato "Titulo (Año)", le damos prioridad absoluta sobre el nombre del archivo.
            if file.get('folder_name'):
                folder_raw = file.get('folder_name')
                
                # Si la carpeta es "Temporada X", usar la carpeta padre (nombre de la serie)
                if re.search(r'(?i)^(temporada|season|t)\s*\d+$', folder_raw):
                    ancestors = file.get('ancestors', [])
                    if len(ancestors) >= 2:
                        folder_raw = ancestors[-2]

                # Estrategia: Buscar patrón estricto "Titulo (Año)"
                match = re.search(r'^(.*?)\s*\(\s*(\d{4})\s*\)', folder_raw)
                if match:
                    # Si la carpeta cumple el formato TMDB, usamos sus datos ignorando el nombre del archivo
                    series_name = match.group(1).strip()
                    year = match.group(2)
                elif not series_name:
                    # Solo si no hay nombre en el archivo y la carpeta no tiene año, intentamos adivinar
                    folder_clean = rename.remove_tokens(folder_raw)
                    year_folder, title_folder = rename.extract_year_and_clean(folder_clean)
                    series_name = title_folder.strip()
                    if not year and year_folder:
                        year = year_folder

            norm_name = rename.normalize_title(series_name)
            if not norm_name: continue

            if norm_name not in series_map:
                # Intentar recuperar de caché, si no buscar en TMDB
                cached_item = meta_cache.get(f"tv_{norm_name}")
                tmdb_data = cached_item.get('tmdb_top') if cached_item else None
                manual_id = cached_item.get('manual_id') if cached_item else None
                
                # Verificar si necesitamos refrescar (datos faltantes o colección incompleta)
                need_refresh = not tmdb_data or 'collection' not in tmdb_data
                if not need_refresh and tmdb_data.get('collection') and tmdb_data['collection'].get('id'):
                    # Si tiene colección pero le falta fanart o logo, refrescar
                    if not tmdb_data['collection'].get('fanart') or not tmdb_data['collection'].get('clearlogo'):
                        need_refresh = True
                
                # Si hay ID manual y los datos no coinciden o necesitamos refrescar, forzar uso de ID manual
                if manual_id and (need_refresh or str(tmdb_data.get('tmdb_id')) != str(manual_id)):
                    need_refresh = True

                if need_refresh:
                    # print(f"Refrescando metadatos para serie: {series_name}")
                    tmdb_data = get_tmdb_meta(series_name, is_tv=True, year=year, manual_id=manual_id)
                
                series_map[norm_name] = {
                    "file": series_name,
                    "parsed": {"type": "series", "series": series_name, "year": year},
                    "tmdb_top": tmdb_data,
                    "episodes": [],
                    "date_added": datetime.datetime.utcnow().isoformat(),
                    "folder_id": str(file.get('folder_id', '')),
                    "manual_id": manual_id
                }
            
            # Buscar/Crear episodio
            entry = series_map[norm_name]
            
            # FIX: Si encontramos cualquier archivo de esta serie en la carpeta Anime, forzamos el ID de la serie
            if str(file.get('folder_id', '')) == '19385669' and entry.get('folder_id') != '19385669':
                entry['folder_id'] = '19385669'

            ep_found = None
            for ep in entry["episodes"]:
                if ep["season"] == season and ep["episode"] == episode:
                    ep_found = ep
                    break
            
            if not ep_found:
                ep_found = {"season": season, "episode": episode, "links": []}
                entry["episodes"].append(ep_found)
            
            # Añadir link si no existe
            if not any(l["url"] == link for l in ep_found.get("links", [])):
                ep_found.setdefault("links", []).append({"quality": quality, "url": link})
                # print(f"Serie procesada: {series_name} S{season}E{episode}")

        else:
            # ES PELICULA
            title = meta["title"]
            
            # INTELIGENCIA DE CARPETAS (PELICULAS): Prioridad a la carpeta si tiene formato "Titulo (Año)"
            if file.get('folder_name'):
                folder_raw = file.get('folder_name')
                match = re.search(r'^(.*?)\s*\(\s*(\d{4})\s*\)', folder_raw)
                if match:
                    title = match.group(1).strip()
                    meta["year"] = match.group(2)

            # Buscar si ya existe en new_results o catalog
            # La clave de caché usa el título normalizado, mientras que la búsqueda en TMDB usará el título sin normalizar.
            norm_title = rename.normalize_title(title)
            cache_key = f"movie_{norm_title}_{meta['year'] or ''}"
            cached_item = meta_cache.get(cache_key)
            tmdb_data = cached_item.get('tmdb_top') if cached_item else None
            manual_id = cached_item.get('manual_id') if cached_item else None
            
            # Verificar si necesitamos refrescar (datos faltantes o colección incompleta)
            need_refresh = not tmdb_data or 'collection' not in tmdb_data
            
            # Validar coincidencia de año para evitar falsos positivos cacheados (ej. Rey León 2019 vs 1994)
            if not need_refresh and meta.get('year') and tmdb_data.get('year'):
                if str(tmdb_data.get('year')) != str(meta.get('year')):
                    # print(f"  -> Mismatch de año detectado. Forzando refresh.")
                    need_refresh = True

            if not need_refresh and tmdb_data.get('collection') and tmdb_data['collection'].get('id'):
                # Si tiene colección pero le falta fanart o logo, refrescar
                if not tmdb_data['collection'].get('fanart') or not tmdb_data['collection'].get('clearlogo'):
                    need_refresh = True
            
            if manual_id and (need_refresh or str(tmdb_data.get('tmdb_id')) != str(manual_id)):
                need_refresh = True

            if need_refresh:
                # print(f"Refrescando metadatos para película: {title}")
                tmdb_data = get_tmdb_meta(title, is_tv=False, year=meta["year"], manual_id=manual_id)

            item = {
                "file": filename,
                "parsed": meta,
                "tmdb_top": tmdb_data,
                "links": [{"quality": quality, "url": link}],
                "date_added": datetime.datetime.utcnow().isoformat(),
                "folder_id": str(file.get('folder_id', '')),
                "manual_id": manual_id
            }
            new_results.append(item)
            # print(f"Película procesada: {title}")

    # Reconstruir lista final
    final_results = new_results + list(series_map.values())
    catalog["results"] = final_results

    # Guardar JSON
    with open(CATALOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Catálogo guardado en {CATALOG_PATH}")
    
    # Generar DB
    update_cache_db(final_results)

if __name__ == "__main__":
    # Iniciar proceso
    generate()
