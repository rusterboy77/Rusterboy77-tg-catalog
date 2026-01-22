import os, sqlite3, json
paths = [r"z:\\tg-catalog\\app\\cache.db", r"z:\\tg-catalog\\app\\cache(4).db"]
res = {}
for p in paths:
    info = {"exists": os.path.exists(p)}
    if not info["exists"]:
        res[p] = info; continue
    info["size_bytes"] = os.path.getsize(p)
    try:
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        info["tables"] = [r[0] for r in cur.fetchall()]
        try:
            cur.execute("PRAGMA table_info(items)")
            info["items_columns"] = cur.fetchall()
        except Exception as e:
            info["items_columns"] = str(e)
        try:
            cur.execute("SELECT COUNT(*), SUM(LENGTH(torrents)), SUM(LENGTH(genres)), SUM(LENGTH(overview)), SUM(LENGTH(poster)), SUM(LENGTH(fanart)) FROM items")
            info_update = cur.fetchone()
            info["row_count"] = info_update[0]
            info["sum_len_torrents"] = info_update[1] or 0
            info["sum_len_genres"] = info_update[2] or 0
            info["sum_len_overview"] = info_update[3] or 0
            info["sum_len_poster"] = info_update[4] or 0
            info["sum_len_fanart"] = info_update[5] or 0
        except Exception as e:
            info["row_count_error"] = str(e)
        keys = set(); key_lengths = {}
        try:
            cur.execute('SELECT "key", LENGTH(torrents) FROM items')
            for k,l in cur.fetchall():
                keys.add(k)
                key_lengths[k] = l or 0
            info["distinct_keys"] = len(keys)
            info["top10_torrents_len"] = sorted(key_lengths.items(), key=lambda x: x[1], reverse=True)[:10]
        except Exception as e:
            info["keys_error"] = str(e)
        conn.close()
    except Exception as e:
        info["open_error"] = str(e)
    res[p] = info
comparison = {}
if res.get(paths[0],{}).get('exists') and res.get(paths[1],{}).get('exists'):
    try:
        conn = sqlite3.connect(paths[0]); cur = conn.cursor(); cur.execute('SELECT "key" FROM items'); c1 = set(r[0] for r in cur.fetchall()); conn.close()
        conn = sqlite3.connect(paths[1]); cur = conn.cursor(); cur.execute('SELECT "key" FROM items'); c2 = set(r[0] for r in cur.fetchall()); conn.close()
        comparison['only_in_1'] = sorted(list(c1 - c2))
        comparison['only_in_2'] = sorted(list(c2 - c1))
        comparison['count_only_in_1'] = len(c1 - c2)
        comparison['count_only_in_2'] = len(c2 - c1)
    except Exception as e:
        comparison['error'] = str(e)
out = {'res': res, 'comparison': comparison}
print(json.dumps(out, ensure_ascii=False, indent=2))
try:
    with open(r"z:\\tg-catalog\\tools\\compare_output.json", 'w', encoding='utf-8') as fo:
        json.dump(out, fo, ensure_ascii=False, indent=2)
except Exception:
    pass

# concise summary for terminal
try:
    a = out['res'][r"z:\\tg-catalog\\app\\cache.db"]
    b = out['res'][r"z:\\tg-catalog\\app\\cache(4).db"]
    comp = out['comparison']
    print('\n--- SUMMARY ---')
    print('cache.db size bytes:', a.get('size_bytes'))
    print('cache.db rows:', a.get('row_count'), 'distinct_keys:', a.get('distinct_keys'))
    print('cache(4).db size bytes:', b.get('size_bytes'))
    print('cache(4).db rows:', b.get('row_count'), 'distinct_keys:', b.get('distinct_keys'))
    print('only in original (count):', comp.get('count_only_in_1'))
    print('only in uploaded (count):', comp.get('count_only_in_2'))
    print('examples only in original (first 20):')
    for k in comp.get('only_in_1', [])[:20]:
        print(' -', k)
except Exception:
    pass
