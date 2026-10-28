from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)  # keep application loggers alive
target_metadata = Base.metadata
URL = settings.database_url


def run_migrations_offline():
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


(run_migrations_offline if context.is_offline_mode() else run_migrations_online)()
