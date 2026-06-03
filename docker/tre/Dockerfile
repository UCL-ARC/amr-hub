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

# Copy examples (if needed for testing or demonstration purposes)
COPY examples /app/examples

# Create a directory for simulation outputs
RUN mkdir -p /app/simulation_outputs

# In TRE, run scripts directly with the prebuilt venv Python
ENTRYPOINT ["/app/python-code/.venv/bin/python3"]

# Default action if no script is provided
CMD ["--version"]
