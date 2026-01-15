import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="convoy_ai",
            user="postgres",
            password="prapti",
            port="5432",
            cursor_factory=RealDictCursor   # IMPORTANT
        )
        print("SUCCESS! Connection established.")
        return conn

    except Exception as e:
        print(f"FAILURE! Connection failed with error: {e}")
        return None

