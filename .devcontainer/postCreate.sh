# .devcontainer/postCreate.sh

curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="$HOME/.cargo/bin:$PATH"

cd python-code/
uv sync --group dev
