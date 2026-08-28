from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base plus every model module so their tables register on
# Base.metadata before autogenerate diffs against it — the same set
# app/main.py imports for create_all(), so nothing is missing here that the
# running app would otherwise know about.
from app.database import Base, DATABASE_URL

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.logs.models
import app.loading.schemas.stores_schemas
import app.reports.models
import app.notifications.models

target_metadata = Base.metadata

# The DB URL comes from the same DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
# env vars app/database.py reads (via DATABASE_URL) rather than from
# alembic.ini, so there is one place the connection string is assembled, not
# two that can drift apart.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    # chatbot_backend (a separate service, see chatbot_backend/.env.example)
    # writes its own chatbot_messages/chatbot_conversations tables into this
    # same database. They have no model here and autogenerate would
    # otherwise read them as "removed" and emit DROP TABLE — a reflected
    # table with nothing in our metadata to compare to belongs to someone
    # else, not to a schema change of ours, so it is left alone.
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
