#!/usr/bin/env python3
"""
Script para generar la estructura de un Repositorio Kodi automáticamente.
1. Busca carpetas de addons en 'addons_src'.
2. Lee sus versiones en addon.xml.
3. Crea los ZIPs en la carpeta 'zips'.
4. Genera el archivo addons.xml y addons.xml.md5 necesarios para Kodi.
"""
import os
import zipfile
import hashlib
import xml.etree.ElementTree as ET

# Rutas relativas a la raíz del repo
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDONS_SRC = os.path.join(BASE_DIR, "addons_src")
ZIPS_DIR = os.path.join(BASE_DIR, "zips")

def make_zip(addon_id, version, source_path):
    zip_folder = os.path.join(ZIPS_DIR, addon_id)
    os.makedirs(zip_folder, exist_ok=True)
    zip_name = f"{addon_id}-{version}.zip"
    zip_path = os.path.join(zip_folder, zip_name)
    
    if os.path.exists(zip_path):
        print(f"  [SKIP] {zip_name} ya existe.")
        return

    print(f"  [ZIP] Creando {zip_name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                # Excluir archivos innecesarios (git, pyc, cache)
                if file.endswith(".pyc") or file.startswith(".") or "__pycache__" in root:
                    continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, os.path.dirname(source_path))
                zf.write(abs_path, rel_path)

def generate():
    if not os.path.exists(ADDONS_SRC):
        print(f"AVISO: Crea la carpeta '{ADDONS_SRC}' en la raíz y pon ahí dentro la carpeta de tu addon.")
        return

    if not os.path.exists(ZIPS_DIR):
        os.makedirs(ZIPS_DIR)

    addons_xml = ET.Element("addons")
    count = 0
    
    for addon_id in os.listdir(ADDONS_SRC):
        addon_path = os.path.join(ADDONS_SRC, addon_id)
        if not os.path.isdir(addon_path): continue
        
        xml_file = os.path.join(addon_path, "addon.xml")
        if not os.path.exists(xml_file): continue
        
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            version = root.get("version")
            print(f"Procesando {addon_id} v{version}...")
            
            # Añadir al addons.xml global
            addons_xml.append(root)
            
            # Crear el zip
            make_zip(addon_id, version, addon_path)
            count += 1
        except Exception as e:
            print(f"Error en {addon_id}: {e}")

    if count == 0:
        print("No se encontraron addons en addons_src.")
        return

    # Guardar addons.xml
    print("Generando addons.xml y MD5...")
    xml_str = ET.tostring(addons_xml, encoding="utf-8", method="xml")
    
    # Guardar addons.xml
    xml_path = os.path.join(ZIPS_DIR, "addons.xml")
    with open(xml_path, "wb") as f:
        f.write(b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
        f.write(xml_str)

    # Generar MD5 (Kodi lo necesita para saber si hay cambios)
    with open(xml_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    with open(xml_path + ".md5", "w") as f:
        f.write(md5)
    
    print("¡Listo! Sube la carpeta 'zips' a GitHub.")

if __name__ == "__main__":
    generate()
