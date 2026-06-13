FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    libpq-dev \
    tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data/logs /app/data/cache

EXPOSE 38001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:38001/api/docs >/dev/null || exit 1

CMD ["/app/entrypoint.sh"]
