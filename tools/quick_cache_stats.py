import os, sqlite3
paths = [r"z:\\tg-catalog\\app\\cache.db", r"z:\\tg-catalog\\app\\cache(4).db"]
for p in paths:
    print('PATH:', p)
    if not os.path.exists(p):
        print('  missing')
        continue
    print('  size_bytes:', os.path.getsize(p))
    try:
        conn = sqlite3.connect(p); cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM items'); rc = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT "key") FROM items'); kc = cur.fetchone()[0]
        print('  rows:', rc, 'distinct keys:', kc)
        conn.close()
    except Exception as e:
        print('  error opening db:', e)
