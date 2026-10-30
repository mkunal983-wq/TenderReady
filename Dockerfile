FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.13-slim
WORKDIR /app/backend
COPY backend/pyproject.toml backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN pip install --no-cache-dir --no-deps -e . && useradd --uid 10001 --create-home appuser && mkdir -p /app/data/documents && chown -R appuser:appuser /app/data
COPY --from=frontend /build/dist /app/frontend-dist
USER appuser
ENV APP_ENV=production FRONTEND_DIST=/app/frontend-dist STORAGE_DIR=/app/data/documents
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn tenderready.site:create_site --factory --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers --no-access-log"]
