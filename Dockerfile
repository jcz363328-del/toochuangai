FROM node:22-bookworm-slim AS sales-build
WORKDIR /app/business_analysis
COPY business_analysis/package*.json ./
RUN npm ci
COPY business_analysis/ ./
RUN npm run build:flask

FROM node:22-bookworm-slim AS listing-build
WORKDIR /app/listing_agent_v2/frontend
COPY listing_agent_v2/frontend/package*.json ./
RUN npm ci
COPY listing_agent_v2/frontend/ ./
RUN npm run build

FROM sales-build AS sales-api
ENV NODE_ENV=production TZ=Asia/Shanghai
RUN npm prune --omit=dev --ignore-scripts
CMD ["node", "server/index.mjs"]

FROM node:22-bookworm-slim AS ads-build
WORKDIR /app/ads-monitor-web
COPY ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/package*.json ./
RUN npm ci
COPY ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/ ./
RUN npm run build:flask

FROM python:3.12-slim-bookworm AS web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai TC_CONTAINER_MODE=1 TC_BACKGROUND_JOBS=0 TUCHUANGAI_STORAGE_ROOT=/data
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg fonts-noto-cjk tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.docker.txt
COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY innovation/ ./innovation/
COPY listing_agent/ ./listing_agent/
COPY listing_agent_v2/ ./listing_agent_v2/
COPY business_analysis/ ./business_analysis/
COPY 图片/ ./图片/
COPY ads_monitor_web/ads-monitor-web-full-source/ ./ads_monitor_web/ads-monitor-web-full-source/
COPY docker/ ./docker/
COPY --from=sales-build /app/business_analysis/dist-flask ./business_analysis/dist-flask
COPY --from=listing-build /app/listing_agent_v2/frontend/dist/client ./listing_agent_v2/frontend/dist/client
COPY --from=ads-build /app/ads-monitor-web/dist-flask ./ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/dist-flask
RUN mkdir -p /data /app/logs /app/static/exports
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/_container/health', timeout=3)"
CMD ["python", "docker_entrypoint.py"]
