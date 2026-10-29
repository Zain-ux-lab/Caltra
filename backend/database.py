"""Connection adapter for the app's fixed SQL statements, SQLite locally/Postgres remotely."""
import re

TABLES={'settings':'key','foods':'id','estimates':'id','meals':'id','favorites':'id','analyses':'id','usual_products':'category'}

def postgres_sql(sql):
    # The store uses fixed two-column JSON tables. Postgres needs an explicit
    # ordering column where SQLite supplies its implicit rowid.
    if sql.startswith('CREATE TABLE IF NOT EXISTS '):
        return sql[:-1]+', rowid BIGSERIAL UNIQUE)'
    if sql.startswith('INSERT '):
        match=re.match(r'INSERT(?: OR REPLACE)? INTO (\w+) VALUES',sql)
        if match:
            table=match[1];key=TABLES[table];replace='OR REPLACE' in sql
            sql=re.sub(r'INSERT(?: OR REPLACE)? INTO '+table+r' VALUES',f'INSERT INTO {table} ({key},data) VALUES',sql,count=1)
            if replace:sql+=' ON CONFLICT('+key+') DO UPDATE SET data=excluded.data'
    return sql.replace('?','%s')

class PostgresConnection:
    def __init__(self,url):
        import psycopg
        self.db=psycopg.connect(url,connect_timeout=15)
    def __enter__(self):
        self.db.__enter__();return self
    def __exit__(self,*args):return self.db.__exit__(*args)
    def execute(self,sql,args=()):return self.db.execute(postgres_sql(sql),args)
    def executemany(self,sql,args):
        with self.db.cursor() as cursor:cursor.executemany(postgres_sql(sql),args)
