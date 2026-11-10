# 1. Build the web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. The Python backend, which also serves the web app
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GLA_DATA_DIR=/data \
    GLA_IMPORT_DIR=/import \
    GLA_WEB_DIR=/app/web

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/gla ./gla
RUN pip install --no-cache-dir .
COPY --from=web /web/dist /app/web

EXPOSE 8000
CMD ["uvicorn", "gla.api:app", "--host", "0.0.0.0", "--port", "8000"]
