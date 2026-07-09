FROM node:22-slim AS frontend

WORKDIR /src
COPY package.json package-lock.json* tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm install && npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EEW_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=frontend /src/public ./public

EXPOSE 18761
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18761/api/health', timeout=4).read()"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18761"]
