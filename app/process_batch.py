#!/usr/bin/env python3
# process_batch.py - Versión "Serverless" para GitHub Actions
# Se conecta a Telegram, descarga novedades, actualiza catálogo y BD, y termina.

import os, re, json, time, logging, datetime, sqlite3, tempfile, requests, shutil, sys, subprocess

# Configuración
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "")
# Directorios relativos al script (asumiendo ejecución desde raíz del repo)
BASE_DIR = os.getcwd()
APP_DIR = os.path.join(BASE_DIR, "app")
CATALOG_PATH = os.path.join(APP_DIR, "catalog.json")
CACHE_DB_PATH = os.path.join(APP_DIR, "cache.db")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("batch")

# --- Importar lógica existente de main.py (copia simplificada de funciones clave) ---
# Nota: Para una migración limpia, duplicamos las funciones esenciales aquí para que este script sea autónomo.

def _norm_title(s):
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^0-9A-Za-z\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()

def run_script_collect(script_name, args, timeout=30):
    # Buscar scripts en la carpeta app/
    script_path = os.path.join(APP_DIR, script_name)
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "PYTHONUNBUFFERED":"1"})
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        logger.error(f"Error ejecutando {script_name}: {e}")
        return -1, "", str(e)

# --- Lógica de Base de Datos (Simplificada para batch) ---
def ensure_db():
    if not os.path.exists(CACHE_DB_PATH):
        logger.info("Creando cache.db nueva...")
        conn = sqlite3.connect(CACHE_DB_PATH)
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS items (
              "key" TEXT PRIMARY KEY, title TEXT, type TEXT, year TEXT, season TEXT, episode TEXT,
              tmdb_id TEXT, poster TEXT, fanart TEXT, clearlogo TEXT, banner TEXT, clearart TEXT,
              overview TEXT, episode_title TEXT, episode_overview TEXT, still_path TEXT,
              genres TEXT, "cast" TEXT, torrents TEXT, date_added TEXT, enriched INTEGER DEFAULT 0
            );
        """)
        conn.commit(); conn.close()

def db_upsert(key, item):
    try:
        conn = sqlite3.connect(CACHE_DB_PATH, timeout=30)
        c = conn.cursor()
        # Campos JSON
        genres = json.dumps(item.get("genres") or [])
        cast = json.dumps(item.get("cast") or [])
        torrents = json.dumps(item.get("torrents") or [])
        now = item.get("date_added") or datetime.datetime.utcnow().isoformat()
        
        c.execute("""INSERT OR REPLACE INTO items 
            ("key", title, type, year, season, episode, tmdb_id, poster, fanart, clearlogo, banner, clearart, 
             overview, episode_title, episode_overview, still_path, genres, "cast", torrents, date_added, enriched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, item.get("title"), item.get("type"), item.get("year"), item.get("season"), item.get("episode"),
             item.get("tmdb_id"), item.get("poster"), item.get("fanart"), item.get("clearlogo"), item.get("banner"), item.get("clearart"),
             item.get("overview"), item.get("episode_title"), item.get("episode_overview"), item.get("still_path"),
             genres, cast, torrents, now, int(bool(item.get("enriched")))))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.error(f"Error DB upsert {key}: {e}")
        return False

# --- Lógica TMDB (Simplificada) ---
def enrich_tmdb(parsed):
    if not TMDB_API_KEY: return {}
    # Lógica mínima de búsqueda y enriquecimiento
    # (Aquí podrías importar la lógica completa de main.py si lo prefieres, 
    #  para este ejemplo uso una versión resumida que delega en main.py si fuera módulo,
    #  pero para ser autónomo, implementamos lo básico o copiamos enrich_with_tmdb_if_needed)
    # ... Por brevedad, asumimos que el script main.py tiene la lógica compleja.
    # TRUCO: Importamos main.py como módulo para reutilizar su lógica potente.
    try:
        sys.path.append(APP_DIR)
        import main as logic
        return logic.enrich_with_tmdb_if_needed(parsed)
    except Exception as e:
        logger.warning(f"No se pudo importar lógica TMDB de main.py: {e}")
        return {}

# --- Proceso Principal ---
def process_telegram_updates():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN no definido.")
        return

    # 1. Eliminar Webhook (necesario para poder usar getUpdates)
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    except Exception:
        pass

    # 2. Obtener actualizaciones
    updates = []
    try:
        # Offset 0 o manejar persistencia si se desea, pero GitHub Actions suele ser stateless.
        # Al procesar, Telegram marca como leídos si usamos offset+1.
        # Para simplificar en stateless: pedimos todo, procesamos, y confirmamos al final.
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?allowed_updates=[\"message\",\"channel_post\"]", timeout=20)
        if r.ok:
            updates = r.json().get("result", [])
    except Exception as e:
        logger.error(f"Error obteniendo updates: {e}")
        return

    if not updates:
        logger.info("No hay novedades en Telegram.")
        return

    logger.info(f"Procesando {len(updates)} mensajes...")
    
    # Cargar catálogo actual
    ensure_db()
    # Importar lógica de main para reutilizar funciones complejas de merge/upsert
    sys.path.append(APP_DIR)
    import main as logic

    # Forzar recarga de catálogo local en memoria
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
            catalog = json.load(f)
    else:
        catalog = {"results": []}

    max_update_id = 0
    changes_count = 0

    for up in updates:
        update_id = up.get("update_id")
        max_update_id = max(max_update_id, update_id)
        
        msg = up.get("channel_post") or up.get("message")
        if not msg: continue
        
        # Verificar Chat ID
        chat_id = str(msg.get("chat", {}).get("id"))
        allowed = [x.strip() for x in ALLOWED_CHAT_IDS.split(",") if x.strip()]
        if allowed and chat_id not in allowed:
            logger.warning(f"Chat ID {chat_id} no permitido.")
            continue

        # Buscar documentos
        docs = []
        if "document" in msg: docs.append(msg["document"])
        if "documents" in msg: docs.extend(msg["documents"])
        
        for doc in docs:
            file_name = doc.get("file_name", "unknown.torrent")
            file_id = doc.get("file_id")
            
            logger.info(f"Procesando archivo: {file_name}")
            
            # Descargar
            try:
                r_path = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}")
                file_path = r_path.json().get("result", {}).get("file_path")
                dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                content = requests.get(dl_url).content
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as tf:
                    tf.write(content)
                    temp_path = tf.name
                
                # Ejecutar scripts auxiliares (rename/magnet)
                rc, out_ren, _ = run_script_collect("rename.py", [file_name])
                rc2, out_mag, _ = run_script_collect("magnet.py", [temp_path])
                os.remove(temp_path)

                if rc != 0 or rc2 != 0:
                    logger.error("Fallo en scripts auxiliares")
                    continue

                meta = json.loads(out_ren)
                magnet_data = json.loads(out_mag)

                # Construir objeto resultado (lógica idéntica a main.py)
                new_result = {"file": file_name, "parsed": {}, "tmdb_top": {}, "torrents": []}
                # ... (Adaptación simplificada de la lógica de construcción de new_result)
                # Para no duplicar código gigante, usamos la lógica:
                if meta.get("type") == "series":
                    new_result["parsed"] = {"type": "series", "series": meta.get("series"), "season": meta.get("season"), "episode": meta.get("episode"), "quality": meta.get("quality")}
                    new_result["torrents"] = [{"season": meta.get("season"), "episode": meta.get("episode"), "torrents": [{"quality": meta.get("quality"), "magnet": magnet_data.get("magnet")}]}]
                else:
                    new_result["parsed"] = {"type": "movie", "title": meta.get("title") or meta.get("movie"), "year": meta.get("year"), "quality": meta.get("quality")}
                    new_result["torrents"] = [{"quality": meta.get("quality"), "magnet": magnet_data.get("magnet")}]

                # Enriquecer
                enriched = logic.enrich_with_tmdb_if_needed(new_result["parsed"], None)
                if enriched:
                    # Fusionar datos enriquecidos
                    tm = new_result.setdefault("tmdb_top", {})
                    if enriched.get("tmdb_top"): tm.update(enriched["tmdb_top"])
                    for k in ["overview", "poster_url", "backdrop_url", "genres", "cast"]:
                        if enriched.get(k): new_result[k] = enriched[k] # Helper simple

                # Merge en catálogo
                catalog = logic.merge_new_result_into_remote(catalog, new_result)
                
                # Upsert en DB local
                logic.upsert_cache_from_new_result(new_result)
                changes_count += 1

            except Exception as e:
                logger.exception(f"Error procesando {file_name}: {e}")

    # Guardar cambios
    if changes_count > 0:
        logger.info(f"Guardando {changes_count} cambios en catalog.json y cache.db")
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        # cache.db ya se actualiza en tiempo real con logic.upsert_cache_from_new_result
    else:
        logger.info("No hubo cambios efectivos.")

    # Confirmar updates a Telegram (para que no vuelvan a salir)
    if max_update_id > 0:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={max_update_id + 1}")

if __name__ == "__main__":
    process_telegram_updates()
