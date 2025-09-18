import os, sys, re, json

TORRENTS_DIR = "torrents"

def clean_name(name: str) -> str:
    name = re.sub(r"\.torrent$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[\[\]\(\)]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def main():
    if len(sys.argv) < 2:
        print("[ERROR] Falta nombre de archivo")
        return
    filename = sys.argv[1]
    clean_title = clean_name(filename)

    item = {"title": clean_title, "source": f"{TORRENTS_DIR}/{filename}", "type": "torrent"}

    with open("last_item.json", "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

    print(f"[INFO] rename.py -> {clean_title}")

if __name__ == "__main__":
    main()
