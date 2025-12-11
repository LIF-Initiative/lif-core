# lif-core

The LIF Core project is a modular collection of components designed to facilitate the aggregation of learner
information from a variety of systems and sources into a single data record. The record is based off of a
flexible data model schema that can be extended and constrained for localized use. Mapping from a variety of
source formats into the LIF data model is managed by a web app (known as MDR) with a graphical UI, included in this repo.

## Try the LIF Demo

To experience the LIF components firsthand, you can run the LIF demo application using Docker. Navigate to the [`deployments/advisor-demo-docker/`](deployments/advisor-demo-docker/) directory for instructions on setting up and running the demo. This will give you an interactive demonstration of the LIF Advisor, LIF GraphQL, and MDR, allowing you to explore the system's capabilities and features in a controlled, local environment.

## Documentation

This project maintains several key documentation files to help contributors and users:

### For Contributors

- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Guidelines for contributing to the project, including coding standards, commit conventions, and the pull request process
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** - Community standards and expectations for all participants
- **[docs/](docs/)** - Detailed technical documentation, API references, and user guides

### For Users

- **[CHANGELOG.md](CHANGELOG.md)** - Complete history of all notable changes, organized by version. Check here to see what's new, what's changed, and what's been fixed in each release
- **[MIGRATION.md](MIGRATION.md)** - Step-by-step upgrade guides for breaking changes. **Read this before upgrading** to understand what changes require action on your part

### When to Check Each File

| Scenario | File to Check |
| ---------- | -------------- |
| I want to contribute code | [CONTRIBUTING.md](CONTRIBUTING.md) |
| What changed in the latest release? | [CHANGELOG.md](CHANGELOG.md) |
| How do I upgrade to a new version? | [MIGRATION.md](MIGRATION.md) |
| I need technical/API documentation | [docs/](docs/) |
| Reporting behavior issues | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |

### Documentation Standards

When contributing, please ensure:

- Breaking changes are documented in both CHANGELOG.md and MIGRATION.md
- Database schema changes include migration files and changelog entries
- API changes update both the base Python documentation and project READMEs
- Configuration changes update relevant folder READMEs

For more details, see the pull request template and [CONTRIBUTING.md](CONTRIBUTING.md).

## Community Support

We will be activating the Discussions feature in GitHub to support community discussions and topics.
Community engagement is highly encouraged, especially for code changes and data model discussions.

## Toolchain

- python
- uv
- polylith
- ruff
- ty
- pytest
- pre-commit
- commitlint
- cspell
- mkdocs

## Initial Local Development Setup

1. Clone Repository
    - In a terminal, run:
        ```
        git clone git@github.com:LIF-Initiative/lif-main.git
        ```
2. Install uv
    - Instructions: [https://docs.astral.sh/uv/getting-started/installation/]
    - Verify:
        - In a terminal, run:

            ```bash
            uv --version

            ```
        - You should see a something like this:

            ```bash
            uv 0.7.11
            ```

3. Create Virtual Environment / Install Dependencies
    - In a terminal, run:

        ```bash
        uv sync
        ```

    - Output will indicate that virtual environment was created at .venv and dependencies installed will be listed
4. Verify Python is Installed
    - In a terminal, run:

        ```bash
        uv run python --version
        ```

    - You should see:

        ```bash
        Python 3.13.4
        ```

5. Verify ruff is Installed
    - In a terminal, run:

        ```bash
        uv run ruff --version
        ```

    - You should see something like:

        ```bash
        ruff 0.11.13
        ```

6. Verify ty is Installed
    - In a terminal, run:

        ```bash
        uv run ty --version
        ```

    - You should see something like:

        ```bash
        ty 0.0.1-alpha.8
        ```

7. Verify pytest is Installed
    - In a terminal, run:

        ```bash
        uv run pytest --version
        ```

    - You should see something like:

        ```bash
        pytest 8.4.0
        ```

8. Verify pre-commit is Installed
    - In a terminal, run:

        ```bash
        uv run pre-commit --version
        ```

    - You should see something like:

        ```bash
        pre-commit 4.2.0 (pre-commit-uv=4.1.4, uv=0.7.11)
        ```

9. Verify mkdocs is Installed
    - In a terminal, run:

        ```bash
        uv run mkdocs --version
        ```

    - You should see something like:

        ```bash
        mkdocs, version 1.6.1
        ```

10. Install pre-commit Hooks
    - In a terminal, run:

        ```bash
        uv run pre-commit install
        ```

    - You should see the following output:
  
        ```bash
        pre-commit installed at .git/hooks/pre-commit
        ```

    - In a terminal, run:

        ```bash
        uv run pre-commit install --hook-type commit-msg
        ```

    - You should see the following output:

        ```bash
        pre-commit installed at .git/hooks/commit-msg
        ```

## Optional Local Development Setup

1. Install jq
    - See: [jqlang.org download page](https://jqlang.org/download/)
    - This is only needed if you will be using the mongodb-seed Docker container with the sample data

## Common Commands

### Check Code Formatting

```bash
uv run ruff format

```

### Run Linter

```bash
uv run ruff check
```

### Run Type Checker

```bash
uv run ty check
```

### Run All Checks

```
uv run pre-commit run
```

## Using Virtual Environment

Instead of having to prefix each command with `uv run`, you can instead activate the virtual environment.

### Activate

```bash
source .venv/bin/activate

```

### Deactivate

```bash
deactivate
```
