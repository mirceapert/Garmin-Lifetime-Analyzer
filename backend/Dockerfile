FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GLA_DATA_DIR=/data \
    GLA_IMPORT_DIR=/import

WORKDIR /app
COPY pyproject.toml ./
COPY gla ./gla
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "gla.api:app", "--host", "0.0.0.0", "--port", "8000"]
