# Offline parser fixtures

These synthetic HTML documents are retained only for reusable extraction tests.
They are not live jobs, must never be fetched as platform pages, and must never
be inserted into the application database. The former fixture/browser worker
and demonstration commands have been removed. Automated persistence tests use
an isolated temporary PostgreSQL database (see `tests/conftest.py`).
