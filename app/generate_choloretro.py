#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import requests
import re
import sys
import datetime
import sqlite3

# Importar rename.py desde el mismo directorio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import rename

# Configuración desde Secrets
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
ONEFICHIER_API_KEY = os.environ.get('ONEFICHIER_API_KEY')
ONEFICHIER_FOLDER_ID = os.environ.get('ONEFICHIER_FOLDER_ID')

# Rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(BASE_DIR, "catalog_choloretro.json")
CACHE_DB_PATH = os.path.join(BASE_DIR, "cache_choloretro.db")

def parse_filename_with_rename(filename):
    """Usa la lógica de rename.py para extraer metadatos."""
    # LIMPIEZA: Eliminar marcas de canales que confunden al parser
    filename = re.sub(r'[@\[\(]?\s*canales?[\s._-]*locos?\s*[\]\)]?', '', filename, flags=re.IGNORECASE)

    base = rename.safe_norm(filename.rsplit(".", 1)[0])
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
        # CORRECCIÓN: Si el título está vacío (ej: 1x04 Titulo), buscar después del patrón
        if not title_part.strip():
            title_part = base[se_match.end():]
        title_clean = rename.normalize_title(rename.remove_tokens(title_part))
        year, title_clean = rename.extract_year_and_clean(title_clean)
        return {"type": "series", "series": title_clean, "season": season, "episode": episode, "quality": quality, "year": year}
    elif is_series_cap:
        # Lógica simple para capítulos numéricos (ej. 101 -> S1 E1)
        return {"type": "series", "series": rename.normalize_title(rename.remove_tokens(base)), "season": cap_num // 100, "episode": cap_num % 100, "quality": quality}
    else:
        cleaned = rename.remove_tokens(base)
        year, cleaned_no_year = rename.extract_year_and_clean(cleaned)
        movie_title = rename.normalize_title(rename.safe_norm(cleaned_no_year))
        return {"type": "movie", "title": movie_title, "year": year or "", "quality": quality}

def get_tmdb_meta(query, is_tv, year=None):
    """Busca en TMDB y retorna metadatos."""
    if not TMDB_API_KEY: return {}
    
    type_str = 'tv' if is_tv else 'movie'
    url = f"https://api.themoviedb.org/3/search/{type_str}"
    params = {'api_key': TMDB_API_KEY, 'query': query, 'language': 'es-ES'}
    if year:
        if is_tv: params['first_air_date_year'] = year
        else: params['year'] = year
    
    try:
        r = requests.get(url, params=params)
        results = r.json().get('results', [])
        if results:
            item = results[0]
            tmdb_id = item.get('id')
            
            # --- ENRIQUECIMIENTO EXTRA (Detalles, Créditos, Imágenes) ---
            # Esto recupera géneros, actores y clearlogo que faltaban
            genres = []
            cast = []
            clearlogo = ""
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
            except Exception as e:
                print(f"Error enriqueciendo TMDB {tmdb_id}: {e}")

            return {
                'tmdb_id': tmdb_id,
                'title': item.get('name') if is_tv else item.get('title'), # Título oficial
                'original_title': item.get('original_name') if is_tv else item.get('original_title'),
                'overview': item.get('overview'),
                'poster_url': f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else "",
                'backdrop_url': f"https://image.tmdb.org/t/p/original{item.get('backdrop_path')}" if item.get('backdrop_path') else "",
                # Campos extra para igualar a RusterWolf
                'vote_average': item.get('vote_average'),
                'release_date': item.get('first_air_date') if is_tv else item.get('release_date'),
                'year': (item.get('first_air_date') if is_tv else item.get('release_date') or "")[:4],
                # Nuevos campos enriquecidos
                'genres': genres,
                'cast': cast,
                'clearlogo': clearlogo,
                'banner': '', 
                'clearart': ''
            }
    except Exception as e:
        print(f"Error TMDB: {e}")
    return {}

def get_1fichier_files_recursive(folder_id, headers, parent_folder_name=None):
    """Función auxiliar para recorrer carpetas recursivamente."""
    all_files = []
    
    # 1. Obtener archivos de la carpeta actual
    try:
        r = requests.post("https://api.1fichier.com/v1/file/ls.cgi", json={'folder_id': folder_id}, headers=headers)
        if r.ok:
            items = r.json().get('items', [])
            for item in items:
                item['folder_name'] = parent_folder_name
            all_files.extend(items)
    except Exception as e:
        print(f"Error leyendo archivos en carpeta {folder_id}: {e}")

    # 2. Buscar subcarpetas y entrar en ellas
    try:
        r = requests.post("https://api.1fichier.com/v1/folder/ls.cgi", json={'folder_id': folder_id}, headers=headers)
        if r.ok:
            subfolders = r.json().get('sub_folders', [])
            for sub in subfolders:
                print(f"  >> Escaneando subcarpeta: {sub['name']}")
                all_files.extend(get_1fichier_files_recursive(sub['id'], headers, parent_folder_name=sub['name']))
    except Exception as e:
        print(f"Error leyendo subcarpetas en {folder_id}: {e}")
        
    return all_files

def get_1fichier_files(folder_id):
    """Inicia el escaneo recursivo desde la carpeta raíz."""
    if not ONEFICHIER_API_KEY or not folder_id:
        print("Faltan credenciales de 1fichier")
        return []
        
    headers = {'Authorization': f'Bearer {ONEFICHIER_API_KEY}', 'Content-Type': 'application/json'}
    
    print(f"Iniciando escaneo recursivo en 1fichier (ID Raíz: {folder_id})...")
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
          enriched INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
    ''')
    
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
        
        # Procesar cast: ya está en formato correcto {name, role, thumbnail}
        cast = tmdb.get('cast', [])
        
        # Campos comunes
        common_vals = [
            str(tmdb.get('tmdb_id') or ''),
            tmdb.get('poster_url'), tmdb.get('backdrop_url'),
            tmdb.get('clearlogo'), tmdb.get('banner'), tmdb.get('clearart'),
            tmdb.get('overview'),
            '', '', '', # episode_title, episode_overview, still_path (pendientes de implementar en TMDB fetch)
            json.dumps(genres), json.dumps(cast)
        ]

        if item_type == 'movie':
            links = entry.get('links') or []
            if links:
                key = f"movie_{parsed.get('title')}_{parsed.get('year')}"
                items_db.append((key, parsed.get('title'), 'movie', str(parsed.get('year') or ''), '', '', *common_vals, json.dumps(links), date_added, 1))
        
        elif item_type == 'series':
            for ep in entry.get('episodes', []):
                links = ep.get('links') or []
                if links:
                    key = f"tv_{parsed.get('series')}_{ep.get('season')}_{ep.get('episode')}"
                    items_db.append((key, parsed.get('series'), 'tv', str(parsed.get('year') or ''), str(ep.get('season')), str(ep.get('episode')), *common_vals, json.dumps(links), date_added, 1))

    c.executemany('INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', items_db)
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
    files = get_1fichier_files(ONEFICHIER_FOLDER_ID)
    if not files:
        print("No se encontraron archivos en 1fichier o error de API.")
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
            meta_cache[f"tv_{title}"] = tmdb
        elif parsed.get("type") == "movie":
            title = rename.normalize_title(parsed.get("title") or "")
            year = parsed.get("year") or ""
            meta_cache[f"movie_{title}_{year}"] = tmdb

    series_map = {}
    new_results = []
    
    for file in files:
        filename = file.get('filename')
        link = file.get('url')
        if not filename or not link: continue
        
        if file.get('pass') == 1:
            print(f"⚠️  AVISO: El archivo '{filename}' está protegido con contraseña. Puede fallar en el addon. Se recomienda quitarla en 1fichier.")
        
        meta = parse_filename_with_rename(filename)
        quality = meta.get("quality", "SD")
        
        if meta["type"] == "series":
            series_name = meta["series"]
            season = meta["season"]
            episode = meta["episode"]
            year = meta.get("year")
            
            # Si no hay nombre de serie (ej: 1x01.mkv), usar nombre de carpeta
            if not series_name and file.get('folder_name'):
                folder_raw = file.get('folder_name')
                # Estrategia: Buscar "Titulo (Año)" y descartar el resto (CAST, LAT, etc.)
                match = re.search(r'^(.*?)\s*\(\s*(\d{4})\s*\)', folder_raw)
                if match:
                    series_name = match.group(1).strip()
                    if not year: year = match.group(2)
                else:
                    folder_clean = rename.remove_tokens(folder_raw)
                    year_folder, title_folder = rename.extract_year_and_clean(folder_clean)
                    series_name = rename.normalize_title(title_folder)
                    if not year and year_folder:
                        year = year_folder

            norm_name = rename.normalize_title(series_name)
            if not norm_name: continue

            if norm_name not in series_map:
                # Intentar recuperar de caché, si no buscar en TMDB
                tmdb_data = meta_cache.get(f"tv_{norm_name}")
                if not tmdb_data:
                    tmdb_data = get_tmdb_meta(series_name, is_tv=True, year=year)
                
                series_map[norm_name] = {
                    "file": series_name,
                    "parsed": {"type": "series", "series": series_name},
                    "tmdb_top": tmdb_data,
                    "episodes": [],
                    "date_added": datetime.datetime.utcnow().isoformat()
                }
            
            # Buscar/Crear episodio
            entry = series_map[norm_name]
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
                print(f"Serie procesada: {series_name} S{season}E{episode}")

        else:
            # ES PELICULA
            title = meta["title"]
            # Buscar si ya existe en new_results o catalog
            # (Simplificación: reconstruimos la lista de pelis cada vez o hacemos append)
            # Para este ejemplo, creamos un item nuevo
            cache_key = f"movie_{rename.normalize_title(title)}_{meta['year'] or ''}"
            tmdb_data = meta_cache.get(cache_key)
            if not tmdb_data:
                tmdb_data = get_tmdb_meta(title, is_tv=False, year=meta["year"])
            
            item = {
                "file": filename,
                "parsed": meta,
                "tmdb_top": tmdb_data,
                "links": [{"quality": quality, "url": link}],
                "date_added": datetime.datetime.utcnow().isoformat()
            }
            new_results.append(item)
            print(f"Película procesada: {title}")

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
    generate()