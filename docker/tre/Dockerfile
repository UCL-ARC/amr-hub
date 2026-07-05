FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Work from the repository root
WORKDIR /app

# Make source importable
ENV PYTHONPATH=/app/python-code/src

# Copy dependency files first for better Docker caching
COPY python-code/pyproject.toml python-code/uv.lock ./python-code/

# Install dependencies into a project-local virtual environment
RUN cd python-code && uv sync --frozen --all-groups

# Copy project files
COPY python-code/src ./python-code/src
COPY python-code/tests ./python-code/tests
COPY python-code/README.md ./python-code/README.md

# Copy examples
COPY examples ./examples

# Copy Makefile (and any other top-level files you need)
COPY Makefile ./

# Create output directory
RUN mkdir -p /app/simulation_outputs

# Add the virtual environment to the PATH
ENV PATH="/app/python-code/.venv/bin:${PATH}"

# Default action
CMD ["/app/python-code/.venv/bin/python3", "--version"]
