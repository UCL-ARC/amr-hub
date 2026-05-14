# .devcontainer/postCreate.sh

curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="$HOME/.cargo/bin:$PATH"

cd python-code/
uv sync --group dev
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
