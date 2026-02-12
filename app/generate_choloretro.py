#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import requests
import re
import sys
import datetime

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

def parse_filename_with_rename(filename):
    """Usa la lógica de rename.py para extraer metadatos."""
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
        season = int(se_match.group(1))
        episode = int(se_match.group(2))
        title_part = base[:se_match.start()]
        title_clean = rename.normalize_title(rename.remove_tokens(title_part))
        _, title_clean = rename.extract_year_and_clean(title_clean)
        return {"type": "series", "series": title_clean, "season": season, "episode": episode, "quality": quality}
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
    if year and not is_tv: params['year'] = year
    
    try:
        r = requests.get(url, params=params)
        results = r.json().get('results', [])
        if results:
            item = results[0]
            return {
                'tmdb_id': item.get('id'),
                'title': item.get('name') if is_tv else item.get('title'), # Título oficial
                'original_title': item.get('original_name') if is_tv else item.get('original_title'),
                'overview': item.get('overview'),
                'poster_url': f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else "",
                'backdrop_url': f"https://image.tmdb.org/t/p/original{item.get('backdrop_path')}" if item.get('backdrop_path') else "",
                # Campos extra para igualar a RusterWolf
                'vote_average': item.get('vote_average'),
                'release_date': item.get('first_air_date') if is_tv else item.get('release_date'),
                # Nota: genres y cast requerirían una llamada extra a TMDB (details), 
                # por ahora usamos lo básico de la búsqueda.
                'year': (item.get('first_air_date') if is_tv else item.get('release_date') or "")[:4]
            }
    except Exception as e:
        print(f"Error TMDB: {e}")
    return {}

def get_1fichier_files(folder_id):
    """Lista archivos de una carpeta de 1fichier."""
    if not ONEFICHIER_API_KEY or not folder_id:
        print("Faltan credenciales de 1fichier")
        return []
        
    url = "https://api.1fichier.com/v1/file/ls.cgi"
    headers = {'Authorization': f'Bearer {ONEFICHIER_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'folder_id': folder_id}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        return data.get('items', [])
    except Exception as e:
        print(f"Error 1fichier: {e}")
        return []

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
    series_map = {}
    
    # Procesar catálogo existente para llenar el mapa (preservar datos)
    for item in catalog["results"]:
        parsed = item.get("parsed", {})
        if parsed.get("type") == "series":
            title = rename.normalize_title(parsed.get("series") or "")
            series_map[title] = item

    new_results = []
    
    for file in files:
        filename = file.get('filename')
        link = file.get('url')
        if not filename or not link: continue
        
        meta = parse_filename_with_rename(filename)
        quality = meta.get("quality", "SD")
        
        if meta["type"] == "series":
            series_name = meta["series"]
            norm_name = rename.normalize_title(series_name)
            season = meta["season"]
            episode = meta["episode"]
            
            if norm_name not in series_map:
                tmdb_data = get_tmdb_meta(series_name, is_tv=True)
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

if __name__ == "__main__":
    generate()