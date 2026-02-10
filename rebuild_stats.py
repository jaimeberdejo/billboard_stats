import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
from billboard_stats.db.connection import get_conn, put_conn
from billboard_stats.etl.stats_builder import build_all_stats
conn = get_conn()
try:
    build_all_stats(conn)
finally:
    put_conn(conn)
print('Done.')
