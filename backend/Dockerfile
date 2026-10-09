# Backend image: FastAPI + LangGraph agents.
#   docker build -t eka-backend backend
# Secrets are NEVER baked in: the keys arrive as environment variables at run time.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as a normal user, not root: if the app is ever compromised, it can do less.
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
WORKDIR /srv

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY data/seed_raw.json ./data/seed_raw.json

USER app

# The SQLite file lives in /data, which docker compose keeps in a named volume,
# so the data survives container restarts and rebuilds.
ENV DATABASE_URL=sqlite:////data/knowledge.db \
    PORT=8000
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)"

# On every start: bring the schema up to date, load the sample data only if the database
# is empty (safe to repeat), then serve on $PORT (hosts like Render choose the port).
CMD ["sh", "-c", "alembic upgrade head && python -m app.db.seed --if-empty && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
