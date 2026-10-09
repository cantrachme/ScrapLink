"""Keep committed queue fixtures out of the application/live-worker database."""
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import URL, create_engine, text


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # Must run before test collection: modules import engine/SessionLocal, and
    # crash-recovery tests start subprocesses that must inherit this same DB.
    from backend.app.config import settings

    original_url, original_env = settings.DATABASE_URL, settings.APP_ENV
    original_variables = {key: os.environ.get(key) for key in ('DATABASE_URL', 'APP_ENV')}
    url = settings.DATABASE_URL or URL.create(
        'postgresql+psycopg', username=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD, host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT, database=settings.POSTGRES_DB,
    )
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    name = 'scraplink_pytest_' + uuid4().hex
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE {name}'))
    isolated_url = admin.url.set(database=name).render_as_string(hide_password=False)
    settings.DATABASE_URL, settings.APP_ENV = isolated_url, 'test'
    os.environ.update(DATABASE_URL=isolated_url, APP_ENV='test')

    def cleanup():
        database = sys.modules.get('backend.app.database')
        if database is not None:
            database.engine.dispose()
        try:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
        finally:
            admin.dispose()
            settings.DATABASE_URL, settings.APP_ENV = original_url, original_env
            for key, value in original_variables.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    config.add_cleanup(cleanup)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                   cwd=config.rootpath, check=True)
