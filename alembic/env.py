"""Alembic migration environment for the PhotoSpace database."""

# os reads DATABASE_URL after dotenv loads the project .env file.
import os

# fileConfig applies the logging section from alembic.ini.
from logging.config import fileConfig

# context is the Alembic migration runtime.
from alembic import context

# load_dotenv reads the project .env without overriding exported variables.
from dotenv import load_dotenv

# engine_from_config builds the engine from the ini values.
from sqlalchemy import engine_from_config, pool

# Importing models registers every table on Base.metadata.
from spacedesigner.db import models

# Alembic config loaded from alembic.ini.
config = context.config

# Load .env from the current working directory when it exists.
load_dotenv()

# Read the URL the rest of the project uses.
database_url = os.environ.get("DATABASE_URL")

# Stop with a setup hint when the variable is missing.
if not database_url:
    # Alembic cannot connect or render offline SQL without a URL.
    raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")

# Escape percent signs so ConfigParser does not treat them as interpolation.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Apply the logging configuration when alembic.ini is the source.
if config.config_file_name is not None:
    # Configure loggers from that ini file.
    fileConfig(config.config_file_name)

# Metadata Alembic compares when generating migrations.
target_metadata = models.Base.metadata


# Emit SQL without opening a database connection.
def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    # Read the URL written into the config above.
    url = config.get_main_option("sqlalchemy.url")
    # Configure a URL-only migration context.
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    # Run the migration scripts inside one transaction block.
    with context.begin_transaction():
        # Execute the revisions selected on the command line.
        context.run_migrations()


# Open a connection and run the migrations against it.
def run_migrations_online() -> None:
    """Run migrations in online mode."""
    # Build an engine that does not keep a connection pool.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Open one connection for this invocation.
    with connectable.connect() as connection:
        # Attach that connection and the model metadata.
        context.configure(connection=connection, target_metadata=target_metadata)
        # Run the migration scripts inside one transaction block.
        with context.begin_transaction():
            # Execute the revisions selected on the command line.
            context.run_migrations()


# Offline mode prints SQL. Online mode applies it.
if context.is_offline_mode():
    # Print SQL for the selected revisions.
    run_migrations_offline()
else:
    # Apply the selected revisions to the database.
    run_migrations_online()
