# InfraSentinel dashboard. Standard-library Python, so the image is small.
#   docker compose up -d            (dashboard + AI helper, see docker-compose.yml)
FROM python:3.12-slim
RUN pip install --no-cache-dir cryptography==43.0.3 \
 && useradd --create-home --uid 10001 infrasentinel
WORKDIR /app
COPY server.py agent.py index.html login.html app.js theme.css playbook.json privacy.html terms.html ./
COPY data/organizations.json ./data/organizations.json
ENV IS_BIND=0.0.0.0 IS_PORT=8765 IS_DATA=/data PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown infrasentinel /data
USER infrasentinel
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=4)"
CMD ["python", "server.py", "--no-browser"]
