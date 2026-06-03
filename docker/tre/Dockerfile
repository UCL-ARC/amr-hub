FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/python-code

# Copy dependency files first for better Docker caching
COPY python-code/pyproject.toml python-code/uv.lock ./

# Install dependencies into a project-local virtual environment
RUN uv sync --frozen

# Copy the actual source code
COPY python-code/src ./src
COPY python-code/tests ./tests
COPY python-code/README.md ./README.md

# Default command
CMD ["uv", "run", "python"]
