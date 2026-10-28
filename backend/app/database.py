from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """Add Phase 4 columns to databases created by earlier phases (create_all only adds new tables)."""
    from sqlalchemy import inspect, text
    wanted = {"users": [("pref_inapp", "BOOLEAN DEFAULT 1"), ("pref_email", "BOOLEAN DEFAULT 0"),
                        ("muted_types", "VARCHAR(200) DEFAULT ''")],
              "employees": [("phone", "VARCHAR(30)"), ("address", "VARCHAR(200)")]}
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
