# syntax=docker/dockerfile:1
# Optional deployment path (cPanel is the primary target, see docs/CPANEL_DEPLOY.md).
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /w
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt

FROM python:3.13-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ENV=production UPLOAD_DIR=/data/uploads
RUN useradd --system --uid 10001 --home /app flatwise && mkdir -p /data/uploads && chown -R flatwise /data
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=flatwise app ./app
COPY --chown=flatwise alembic ./alembic
COPY --chown=flatwise alembic.ini passenger_wsgi.py ./
COPY --chown=flatwise --chmod=755 docker-entrypoint.sh ./
USER flatwise
EXPOSE 8000
VOLUME /data/uploads
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
