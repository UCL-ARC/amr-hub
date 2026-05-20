# 🐳 Development Containers and Codespaces

This repository includes a pre-configured development container for contributors using Visual Studio Code.

The development container provides:

- 🐍 Python 3.13,
- 🧹 Ruff formatting and linting,
- 🧩 recommended VS Code extensions,
- 📝 NumPy-style docstring generation support,
- 🧪 pre-configured testing and pre-commit tooling,
- and ⚙️ repository-specific editor settings.

The goal is to provide a reproducible and low-friction development environment with minimal manual setup.

---

## 🚀 Option 1: Local Dev Container (Recommended)

### 📦 Requirements

Install:

- 🐳 Docker
- 💻 Visual Studio Code
- 🔌 The Dev Containers extension for VS Code

---

### ▶️ Getting Started

Clone the repository and open it in VS Code.

Then open the command palette:

```text id="jlwm6s"
Ctrl + Shift + P
```

and run:

```text id="6uj9zt"
Dev Containers: Reopen in Container
```

VS Code will automatically:

- build the container,
- install dependencies,
- configure the Python interpreter,
- install recommended extensions,
- and set up pre-commit hooks.

> [!TIP]
> The first build may take a few minutes depending on internet speed and Docker performance.

---

### ☁️ Option 2: GitHub Codespaces

Contributors may also use GitHub Codespaces.

Codespaces automatically uses the repository's devcontainer configuration, meaning contributors get:

- the same Python version,
- the same extensions,
- the same tooling,
- and the same development environment

without needing to install Docker locally.

> [!TIP]
> Codespaces is especially useful for:
>
> - first-time contributors,
> - workshop environments,
> - temporary development setups,
> - and contributors working on restricted systems.

---

### ▶️ Starting a Codespace

1. Open the repository on GitHub.
2. Click the green `Code` button.
3. Open the `Codespaces` tab.
4. Click `Create codespace on main`.

GitHub will automatically build the development environment.

---

## 🧪 Local Development Without Dev Containers

Contributors who do not wish to use devcontainers or Codespaces can still work locally by following the setup instructions in `CONTRIBUTING.md`.

The repository also provides recommended Visual Studio Code configuration files in the `workspace_settings/` folder.

These include:

- recommended extensions,
- formatting and linting settings,
- Ruff integration,
- and NumPy-style docstring tooling.

Contributors may copy these files directly into their local `.vscode/` directory if they wish to reproduce most of the repository's recommended editor configuration without using devcontainers.

> [!TIP]
> This approach provides much of the same editor experience as the devcontainer setup while allowing contributors to use their existing local Python environments.

---

> [!NOTE]
> Contributors using local environments are responsible for ensuring that:
>
> - dependencies are installed correctly,
> - pre-commit hooks are configured,
> - and tests/linting pass before opening a PR.
