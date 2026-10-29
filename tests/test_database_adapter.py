from backend.database import postgres_sql

def test_create_table_preserves_json_columns_and_adds_ordering():
    assert postgres_sql('CREATE TABLE IF NOT EXISTS meals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')=='CREATE TABLE IF NOT EXISTS meals (id TEXT PRIMARY KEY, data TEXT NOT NULL, rowid BIGSERIAL UNIQUE)'

def test_replacement_and_upsert_preserve_keys():
    assert postgres_sql('INSERT OR REPLACE INTO settings VALUES (?,?)')=='INSERT INTO settings (key,data) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET data=excluded.data'
    assert postgres_sql('INSERT INTO meals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data')=='INSERT INTO meals (id,data) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data'

def test_cache_eviction_uses_ordering_column():
    sql='DELETE FROM analyses WHERE rowid NOT IN (SELECT rowid FROM analyses ORDER BY rowid DESC LIMIT 500)'
    assert postgres_sql(sql)==sql
