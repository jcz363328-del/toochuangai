FROM node:22-bookworm-slim AS sales-build
WORKDIR /app/business_analysis
COPY Department/总经办/business_analysis/package*.json ./
RUN npm ci
COPY Department/总经办/business_analysis/ ./
COPY business_analysis/data/ ./data/
RUN npm run build:flask

FROM node:22-bookworm-slim AS listing-build
WORKDIR /app/listing_agent_v2/frontend
COPY Department/流程与AI部/listing_agent_v2/frontend/package*.json ./
RUN npm ci
COPY Department/流程与AI部/listing_agent_v2/frontend/ ./
RUN npm run build

FROM sales-build AS sales-api
ENV NODE_ENV=production TZ=Asia/Shanghai
RUN npm prune --omit=dev --ignore-scripts
CMD ["node", "server/index.mjs"]

FROM node:22-bookworm-slim AS ads-build
WORKDIR /app/ads-monitor-web
COPY Department/流程与AI部/ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/package*.json ./
RUN npm ci
COPY Department/流程与AI部/ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/ ./
RUN npm run build:flask

FROM python:3.12-slim-bookworm AS web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai TC_CONTAINER_MODE=1 TC_BACKGROUND_JOBS=0 TUCHUANGAI_STORAGE_ROOT=/data
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg fonts-noto-cjk tzdata && rm -rf /var/lib/apt/lists/*
COPY docs/requirements.txt docs/requirements.docker.txt ./docs/
RUN pip install --no-cache-dir -r docs/requirements.docker.txt
COPY *.py ./
COPY Department/ ./Department/
COPY core/ ./core/
COPY integrations/ ./integrations/
COPY shared_modules/ ./shared_modules/
COPY templates/ ./templates/
COPY static/ ./static/
COPY innovation/ ./innovation/
COPY listing_agent/ ./listing_agent/
COPY listing_agent_v2/ ./listing_agent_v2/
COPY Department/总经办/business_analysis/ ./business_analysis/
COPY business_analysis/data/ ./business_analysis/data/
COPY Department/流程与AI部/ads_monitor_web/ads-monitor-web-full-source/ ./ads_monitor_web/ads-monitor-web-full-source/
COPY docker/ ./docker/
COPY --from=sales-build /app/business_analysis/dist-flask ./business_analysis/dist-flask
COPY --from=listing-build /app/listing_agent_v2/frontend/dist/client ./Department/流程与AI部/listing_agent_v2/frontend/dist/client
COPY --from=ads-build /app/ads-monitor-web/dist-flask ./ads_monitor_web/ads-monitor-web-full-source/ads-monitor-web/dist-flask
RUN mkdir -p /data /app/logs /app/static/exports
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/_container/health', timeout=3)"
CMD ["python", "docker_entrypoint.py"]
