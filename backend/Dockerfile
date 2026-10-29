FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir --no-deps -e . && useradd --uid 10001 --create-home appuser && mkdir -p /app/data/documents && chown -R appuser:appuser /app/data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "tenderready.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
