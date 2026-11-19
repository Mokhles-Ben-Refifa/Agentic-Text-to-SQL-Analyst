FROM python:3.12-slim

# Install uv for high-speed package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency locks
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application directories
COPY agent/ ./agent/
COPY app/ ./app/
COPY data/ ./data/
COPY eval/ ./eval/
COPY mcp_server/ ./mcp_server/
COPY semantic/ ./semantic/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000 8501

CMD ["uv", "run", "streamlit", "run", "app/ui.py", "--server.headless=true", "--server.port=8501", "--server.address=0.0.0.0"]
