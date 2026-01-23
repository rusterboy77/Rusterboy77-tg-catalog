#!/usr/bin/env python3
"""
Script para generar la estructura de un Repositorio Kodi automáticamente.
MEJORADO:
- Usa el ID del XML para el nombre del ZIP (evita errores si la carpeta se llama distinto).
- Genera addons.xml con formato legible (pretty print).
- Asegura rutas de iconos con barras normales (/) para compatibilidad.
"""
import os
import zipfile
import shutil
import hashlib
import xml.etree.ElementTree as ET
from xml.dom import minidom

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
                if file.endswith(".pyc") or file.startswith(".") or "__pycache__" in root:
                    continue
                abs_path = os.path.join(root, file)
                # Calcular ruta relativa dentro del zip asegurando que la carpeta raíz sea el addon_id
                rel_path_from_src = os.path.relpath(abs_path, source_path)
                zip_entry_path = os.path.join(addon_id, rel_path_from_src)
                zf.write(abs_path, zip_entry_path)

def copy_assets(addon_id, source_path, xml_root):
    """Copia los iconos/fanart fuera del zip y actualiza el XML en memoria."""
    dest_folder = os.path.join(ZIPS_DIR, addon_id)
    os.makedirs(dest_folder, exist_ok=True)
    
    paths_to_copy = []
    # 1. Buscar assets ya definidos en el XML
    assets = xml_root.find(".//extension[@point='xbmc.addon.metadata']/assets")
    if assets is not None:
        for child in assets:
            if child.text: paths_to_copy.append(child.text)
    
    # 2. Si no hay assets, buscar los estándar y añadirlos al XML
    fallback_assets = []
    if not paths_to_copy:
        if os.path.exists(os.path.join(source_path, "icon.png")): fallback_assets.append("icon.png")
        elif os.path.exists(os.path.join(source_path, "icon.jpg")): fallback_assets.append("icon.jpg")
        
        if os.path.exists(os.path.join(source_path, "fanart.jpg")): fallback_assets.append("fanart.jpg")
        elif os.path.exists(os.path.join(source_path, "fanart.jpeg")): fallback_assets.append("fanart.jpeg")

    if fallback_assets:
        paths_to_copy.extend(fallback_assets)
        metadata = xml_root.find(".//extension[@point='xbmc.addon.metadata']")
        if metadata is not None:
            assets_elem = metadata.find("assets")
            if assets_elem is None:
                assets_elem = ET.SubElement(metadata, "assets")
            for asset in fallback_assets:
                tag = "icon" if "icon" in asset else "fanart"
                el = ET.SubElement(assets_elem, tag)
                # Forzar barra normal para que Kodi lo lea bien en cualquier OS
                el.text = asset.replace("\\", "/")

    if not paths_to_copy:
        print(f"  [AVISO] No se encontraron iconos para {addon_id}.")

    for rel_path in paths_to_copy:
        # Normalizar ruta para el sistema operativo actual (Windows usa backslash)
        sys_rel_path = rel_path.replace("/", os.sep)
        src = os.path.join(source_path, sys_rel_path)
        if os.path.exists(src):
            dest = os.path.join(dest_folder, sys_rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  [ASSET] Copiado {rel_path}")
        else:
            print(f"  [ERROR] Asset declarado pero no encontrado: {src}")

def generate():
    if not os.path.exists(ADDONS_SRC):
        print(f"ERROR: No existe {ADDONS_SRC}")
        return

    if not os.path.exists(ZIPS_DIR):
        os.makedirs(ZIPS_DIR)

    addons_xml = ET.Element("addons")
    count = 0
    
    for folder_name in os.listdir(ADDONS_SRC):
        addon_path = os.path.join(ADDONS_SRC, folder_name)
        if not os.path.isdir(addon_path): continue
        
        xml_file = os.path.join(addon_path, "addon.xml")
        if not os.path.exists(xml_file): continue
        
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            addon_id = root.get("id") # Usar el ID real del XML
            version = root.get("version")
            
            if folder_name != addon_id:
                print(f"  [INFO] La carpeta '{folder_name}' se empaquetará como ID '{addon_id}'")

            print(f"Procesando {addon_id} v{version}...")
            
            # Crear el zip usando el ID correcto
            make_zip(addon_id, version, addon_path)
            
            # Copiar assets y actualizar el objeto root en memoria
            copy_assets(addon_id, addon_path, root)
            
            # Añadir al addons.xml global
            addons_xml.append(root)
            count += 1
        except Exception as e:
            print(f"Error procesando {folder_name}: {e}")

    if count == 0:
        print("No se encontraron addons.")
        return

    # Guardar addons.xml con formato bonito (pretty print)
    print("Generando addons.xml y MD5...")
    xml_str = ET.tostring(addons_xml, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="    ", encoding="utf-8")

    xml_path = os.path.join(ZIPS_DIR, "addons.xml")
    with open(xml_path, "wb") as f:
        f.write(pretty_xml)

    # Generar MD5
    with open(xml_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    with open(xml_path + ".md5", "w") as f:
        f.write(md5)
    
    print("¡Listo! Sube la carpeta 'zips' a GitHub.")

if __name__ == "__main__":
    generate()
