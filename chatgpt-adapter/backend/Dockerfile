FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1
WORKDIR /app
RUN groupadd --system ars && useradd --system --gid ars --home-dir /home/ars --create-home ars \
    && mkdir -p /data \
    && chown -R ars:ars /app /data /home/ars
COPY --chown=ars:ars skills /app/skills
COPY --chown=ars:ars backend /app/backend
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && chown -R ars:ars /app /data
ENV PYTHONPATH=/app/backend:/app/skills
ENV ARS_MCP_TRANSPORT=streamable-http
ENV ARS_HOST=0.0.0.0
ENV PORT=8000
ENV ARS_STATE_DB=/data/ars_state.sqlite3
ENV ARS_ALLOWED_HOSTS=127.0.0.1:*,localhost:*,[::1]:*
ENV ARS_ALLOWED_ORIGINS=http://127.0.0.1:*,http://localhost:*,http://[::1]:*
ENV ARS_MAX_MCP_REQUEST_BYTES=12582912
VOLUME ["/data"]
EXPOSE 8000
USER ars
CMD ["python", "-m", "ars_mcp.server"]
