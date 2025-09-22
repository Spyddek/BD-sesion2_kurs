import psycopg2

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="23565471",
    host="localhost",
    port="5432"
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("DROP ROLE IF EXISTS admin_spa;")
cur.execute("DROP ROLE IF EXISTS salon_spa;")
cur.execute("DROP ROLE IF EXISTS client_spa;")

cur.execute("""
CREATE ROLE admin_spa LOGIN PASSWORD 'admin123';
GRANT ALL PRIVILEGES ON DATABASE smart_spa TO admin_spa;
""")

cur.execute("""
CREATE ROLE salon_spa LOGIN PASSWORD 'salon123';
GRANT CONNECT ON DATABASE smart_spa TO salon_spa;
""")

cur.execute("""
CREATE ROLE client_spa LOGIN PASSWORD 'client123';
GRANT CONNECT ON DATABASE smart_spa TO client_spa;
""")

cur.close()
conn.close()

print("Роли admin_spa, salon_spa и client_spa успешно созданы!")