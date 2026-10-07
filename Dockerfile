FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY app.py ./
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:${PATH}" FRAUD_PROJECT_ROOT=/app FRAUD_STATE_DIR=/app/state
EXPOSE 8000
CMD ["uvicorn", "fraud_lab.api:app", "--host", "0.0.0.0", "--port", "8000"]
