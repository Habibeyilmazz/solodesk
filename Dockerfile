# Build the UI, then ship it inside the Python image: one container, one port.
FROM node:22-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONUNBUFFERED=1 \
    SOLODESK_DATA_DIR=/data \
    SOLODESK_STATIC_DIR=/app/static
COPY backend/ /src/
RUN pip install --no-cache-dir -c /src/constraints.txt /src && rm -rf /src \
    && useradd --system --uid 10001 solodesk \
    && mkdir /data && chown solodesk /data
COPY --from=ui /ui/dist /app/static
USER solodesk
WORKDIR /app
VOLUME /data
EXPOSE 4150
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4150/api/health', timeout=2)"
CMD ["uvicorn", "solodesk.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "4150"]
