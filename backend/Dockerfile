FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENT_ARTIFACT_ROOT=/opt/kai-agent
WORKDIR /app

RUN groupadd --system --gid 1001 kai && useradd --system --uid 1001 --gid kai --home-dir /app kai
COPY backend/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 20 --timeout 120 -r requirements.txt
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY backend/data/getdeploying_public_index.json /opt/kai-bootstrap/getdeploying_public_index.json
COPY backend/docker/entrypoint.sh /usr/local/bin/kai-backend-entrypoint
COPY agent /opt/kai-agent
RUN chmod 0755 /usr/local/bin/kai-backend-entrypoint && chown -R kai:kai /app /opt/kai-agent

USER kai
EXPOSE 8100
ENTRYPOINT ["/usr/local/bin/kai-backend-entrypoint"]
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/ready', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--proxy-headers", "--forwarded-allow-ips=*"]
