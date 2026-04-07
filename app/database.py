from collections.abc import Generator
from urllib.parse import unquote

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings


def _resolved_database_url():
    """Decode DB name in path (e.g. pizzashop%2Dapi -> pizzashop-api). PyMySQL otherwise sends the literal string to MySQL."""
    u = make_url(settings.database_url)
    if settings.mysql_database:
        return u.set(database=settings.mysql_database.strip())
    if u.database:
        decoded = unquote(u.database)
        if decoded != u.database:
            u = u.set(database=decoded)
    return u


engine = create_engine(
    _resolved_database_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
