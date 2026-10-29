import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            # Parsed tender/evidence text is also sensitive; protect the SQLite
            # database, not just the original PDFs. In-memory DBs have no path.
            if os.name == "posix":
                for _, name, filename in connection.execute("PRAGMA database_list"):
                    if name == "main" and filename:
                        os.chmod(filename, 0o600)
    return engine


def build_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
