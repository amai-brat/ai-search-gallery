import os

import psycopg
from utils.config import DATABASE_URL

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "./migrations")


def run_migrations():
    print("Checking for pending database migrations...")
    conn = psycopg.connect(DATABASE_URL)

    try:
        with conn.cursor() as cur:
            # 1. Create the migrations tracking table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

            # 2. Get a list of already applied migrations
            cur.execute("SELECT version FROM schema_migrations;")
            applied_migrations = {row[0] for row in cur.fetchall()}

            # 3. Read available migration files from the directory
            if not os.path.exists(MIGRATIONS_DIR):
                os.makedirs(MIGRATIONS_DIR)

            files = sorted(
                [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")]
            )

            # 4. Apply new migrations
            for file in files:
                if file not in applied_migrations:
                    print(f"Applying migration: {file}")
                    filepath = os.path.join(MIGRATIONS_DIR, file)

                    with open(filepath, "r") as f:
                        sql_script = f.read()

                    try:
                        # Execute the raw SQL script
                        cur.execute(sql_script)  # type: ignore
                        # Record that this migration was applied
                        cur.execute(
                            "INSERT INTO schema_migrations (version) VALUES (%s);",
                            (file,),
                        )
                        conn.commit()
                        print(f"Successfully applied: {file}")
                    except Exception as e:
                        conn.rollback()
                        print(f"Failed to apply migration {file}: {e}")
                        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
