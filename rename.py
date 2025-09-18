import sys, os, re

def clean_name(fname):
    name = os.path.splitext(fname)[0]
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(".", " ")
    return name

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    fname = sys.argv[1]
    new_name = clean_name(fname) + ".torrent"
    print(new_name)
