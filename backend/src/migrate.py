import logging
from pathlib import Path

from utils.database import get_db_connection, now

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Apply the SQL files in migrations/ that have not been applied yet."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            logger.info("Applying migration %s", path.name)
            script = path.read_text(encoding="utf-8")
            # executescript commits first; wrap the file and its record in one
            # transaction so a failed migration leaves nothing behind.
            conn.executescript(
                "BEGIN;\n"
                + script
                + "\nINSERT INTO schema_migrations (version, applied_at) VALUES ("
                + f"'{path.name}', '{now()}');\nCOMMIT;"
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
