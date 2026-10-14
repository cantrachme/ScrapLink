FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini pytest.ini ./
COPY tests ./tests
CMD ["python", "-m", "backend.app.workers.run_worker"]
