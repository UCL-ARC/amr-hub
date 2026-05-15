# 🤝 Contributing to AMR Hub ABM

Thank you for your interest in contributing to the AMR Hub ABM project 🎉

This repository aims to develop a robust, maintainable, and scientifically rigorous agent-based modelling framework for studying antimicrobial resistant (AMR) infections in hospitals.

We welcome:

- 🐛 bug fixes,
- ✨ new features,
- 📚 documentation improvements,
- 🧪 tests,
- ♻️ refactoring,
- 💡 discussions and ideas.

---

## 🧭 Development Philosophy

This repository prioritises:

- 📖 readability over premature optimisation,
- 🧩 strong typing and maintainability,
- 🔬 scientific reproducibility,
- 🧪 extensive testing,
- 📚 clear documentation,
- 🏗️ modular design,
- 🕰️ long-term maintainability over short-term convenience.

> [!NOTE]
> Passing `ruff`, `mypy`, and tests is a **necessary but not sufficient** condition for merging code.

Code should also be:

- understandable,
- appropriately documented,
- scientifically justifiable,
- and maintainable by future contributors.

> [!TIP]
> Most linting, formatting, code-quality, typing, and docstring requirements can be automatically handled by extensions and tooling available in modern IDEs.

Want an easy setup?

> [!TIP]
> Recommended setups for development in VS Code are provided in the `.devcontainer/` and `workspace_settings/` folders of this repository.

---

## 🔄 Contribution Workflow

The expected workflow is:

```text id="j4n1ax"
Issue -> Pull Request -> Review -> Merge into main
```

## 📌 Repository Rules

- 🔒 `main` is protected.
- 🚫 Direct pushes to `main` are not allowed.
- 🚫 Force pushes are not allowed.
- 🚫 Never ever push data, secrets, or large files to the repository.
- 🔗 Every PR should link to an issue.
- 📝 Either the issue or the PR description must contain sufficient detail for reviewers to understand:
  - the motivation,
  - the implementation approach,
  - and the testing strategy.

> [!TIP]
> If you are unsure whether something deserves an issue first, the answer is usually "yes" 🙂

Very Important:

> [!DANGER]
> This project works with sensitive patient data. Do not ever push data, secrets, or large files to the repository. If you need to share data or secrets for development purposes, please use secure channels outside of the repository. Sharing data or secrets in the repository is a serious breach of security and privacy protocols and will not be tolerated.

---

## 🧱 Large Features and Architectural Changes

For larger features or architectural changes:

1. Open an issue first.
2. Discuss the proposed design.
3. Break large work into smaller sub-issues where appropriate.
4. Submit focused PRs linked to those issues.

> [!WARNING]
> Large architectural changes submitted without prior discussion may require substantial revision before merging.

---

## 🔍 Pull Request Expectations

### 🎯 Keep PRs Focused

PRs should ideally have a **single responsibility**.

Examples:

- one feature,
- one bug fix,
- one refactor,
- one documentation improvement.

Avoid:

- mixing unrelated changes,
- combining large refactors with feature additions,
- and “catch-all” PRs.

> [!NOTE]
> Smaller PRs are easier to review, test, and maintain.

---

### 🚧 Draft PRs and WIP Commits

Draft/WIP PRs are completely acceptable and encouraged.

WIP commits are also acceptable.

> [!TIP]
> Early feedback is usually better than late feedback.

---

## 🛠️ Local Development Setup

The repository uses `uv` for dependency management.

### 📥 Recommended Setup

```bash id="zcm8hx"
curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="$HOME/.cargo/bin:$PATH"

cd python-code
uv sync --group dev

uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

---

### 📦 Optional Dependency Groups

#### 📚 Documentation dependencies

```bash id="n0m0mf"
uv sync --group dev --group docs
```

#### 🧪 Additional testing dependencies

```bash id="6zx4l7"
uv sync --group dev --group test
```

---

## ✅ Before Opening a PR

Contributors should run:

```bash id="1qujlwm"
cd python-code

make pre-commit
make tests
```

> [!DANGER]
> PRs with failing tests or failing pre-commit checks should not be merged.

Also,

> [!NOTE]
> If you are unsure how to resolve failures, please ask for help in the issue or PR discussion.

---

## 🧪 Testing Expectations

- ✅ All new functionality should include tests.
- ✅ Bug fixes should include regression tests where feasible.
- ✅ Documentation-only changes may skip tests if no executable behaviour is affected.
- ✅ New code should not reduce the reliability or reproducibility of the model.

Where practical:

- tests should be deterministic,
- random behaviour should be controllable,
- and scientific assumptions should be explicit.

> [!TIP]
> Good tests are part of the scientific reliability of the project.

---

## 🧠 Code Style Guidelines

### 🏷️ Type Hinting

Type hints are considered **essential** in this repository.

Contributors are expected to:

- use explicit typing wherever practical,
- avoid unnecessary `Any`,
- and write code that passes `mypy`.

> [!WARNING]
> Untyped code will usually require strong justification.

---

### 📖 Readability First

Prefer:

- clear naming,
- small focused functions,
- explicit logic,
- and maintainable abstractions.

Avoid:

- overly clever code,
- deeply nested logic,
- and premature optimisation.

> [!NOTE]
> Readability is a feature.

---

### 🧱 Structured State

Use structured representations for state where appropriate:

- dataclasses,
- enums,
- typed containers,
- and explicit configuration objects

are preferred over loosely structured dictionaries.

---

### 📝 Comments and Documentation

Comments should explain:

- scientific assumptions,
- modelling decisions,
- non-obvious implementation details,
- and reasoning behind algorithms.

Avoid comments that merely restate the code.

---

### 📚 NumPy-Style Docstrings

This repository uses **NumPy-style docstrings**.

Public-facing functions, classes, and modules should generally include:

- a short summary,
- parameter descriptions,
- return value descriptions,
- raised exceptions where relevant,
- and usage notes where appropriate.

Example:

```python id="3nn1o0"
def move_agent(agent: Agent, step_size: float) -> Coordinates:
    """Move an agent by a single simulation step.

    Parameters
    ----------
    agent : Agent
        The agent to move.
    step_size : float
        Magnitude of the movement step.

    Returns
    -------
    Coordinates
        The proposed new coordinates for the agent.
    """
```

> [!TIP]
> Good docstrings help both developers and researchers understand modelling assumptions and simulation behaviour.

---

## 📦 Dependencies

Avoid introducing unnecessary dependencies.

New dependencies should:

- provide clear value,
- be actively maintained,
- and fit the long-term goals of the project.

---

## 📚 Documentation Contributions

Documentation improvements are highly encouraged ❤️

This includes:

- tutorials,
- examples,
- API documentation,
- developer documentation,
- and scientific/model explanations.

Documentation should aim to help:

- researchers,
- developers,
- and future maintainers.

---

## 🔬 Scientific and Modelling Considerations

This repository is a scientific software project, not just a general software project.

Contributors should prioritise:

- reproducibility,
- clarity of assumptions,
- and scientific correctness.

When implementing modelling behaviour:

- assumptions should be documented,
- stochastic behaviour should be controlled where practical,
- and limitations should be acknowledged clearly.

> [!WARNING]
> Scientific correctness takes priority over convenience.

---

## 💬 Communication

Questions, ideas, and discussion are welcome.

If you are unsure about:

- architecture,
- modelling assumptions,
- implementation details,
- testing approaches,
- or repository conventions,

please open an issue or start a discussion before investing significant development effort.

> [!TIP]
> We would much rather discuss early than rewrite large PRs later 🙂

---

## ❤️ Thank You

Thank you for contributing to the project and helping improve the quality, reliability, and usability of AMR Hub ABM.
