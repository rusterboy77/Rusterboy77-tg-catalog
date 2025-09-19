import os
import sys

if len(sys.argv) < 2:
    print("Uso: python rename.py <torrent_path>")
    sys.exit(1)

torrent_path = sys.argv[1]
dirname = os.path.dirname(torrent_path)
fname = os.path.basename(torrent_path)

# Simplificamos nombre (ejemplo: quitamos corchetes raros)
new_name = fname.replace(".", " ").replace("[", "").replace("]", "")
new_name = new_name.replace("  ", " ").strip()
new_name = new_name.replace(" ", ".")  # mantener estilo
new_path = os.path.join(dirname, new_name)

os.rename(torrent_path, new_path)

# stdout: ruta final
print(new_path)
