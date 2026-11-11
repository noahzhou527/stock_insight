from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from backend.app.db.models import Base
from backend.app.db.session import make_engine, upgrade


def test_migrations_match_models(tmp_path):
    engine = make_engine(tmp_path / "m.db")
    upgrade(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert diff == []
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    engine.dispose()
