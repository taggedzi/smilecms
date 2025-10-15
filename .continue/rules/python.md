---
name: Python Best Practices
globs: ["**/*.py"]
---

# Python Rules

- **PEP 8 Compliance**: Ensure all code conforms to PEP 8 standards for consistency and readability. format with Black (line length 88) and sort imports (isort); lint with Ruff
- **Modular Design**: Structure code into small, reusable functions and classes, each with a single responsibility, to enhance maintainability and scalability.
- **DRY Principle**: Avoid code duplication by abstracting repetitive code into functions or classes, promoting the 'Don't Repeat Yourself' principle.
- **Type Hinting**: Utilize type hints to specify the expected data types of function arguments and return values, improving code clarity and aiding in error detection. Use type hints on all public functions, methods, and module-level variables
- **Latest Python Features**: Incorporate features from the latest stable Python release to leverage performance improvements and new capabilities.
- **Clear Naming Conventions**: Use descriptive and consistent naming for variables, functions, and classes to enhance code readability.
- **Comprehensive Documentation**: Provide docstrings for all modules, classes, and functions, detailing their purpose, parameters, and return values, to facilitate understanding and maintenance.
- **Version Control**: Maintain a clear commit history with meaningful messages to document changes and facilitate collaboration.
- **Testing**: Develop unit tests for all functions and classes to ensure code reliability and facilitate refactoring.
- Prefer `dataclasses` (or `attrs`) for simple data containers; avoid bare tuples/dicts for structured data
- Avoid mutable default arguments; use `None` and assign inside the function
- Use f-strings for string formatting; avoid %-formatting and `str.format` unless necessary
- Do not use wildcard imports; order imports: stdlib → third-party → local
- Avoid side effects at import time; place execution in `if __name__ == "__main__":` blocks
- Prefer `pathlib` over `os.path` for filesystem paths
- Use context managers to manage resources (files, locks, sessions); ensure explicit cleanup
- Handle errors with specific exceptions; never use bare `except:`; do not silently swallow exceptions
- Log with the `logging` module (not `print`) and include level, module, and message; configure once per app
- Write concise, single-responsibility functions and methods; keep modules focused and cohesive
- Document all public APIs with docstrings (Google or NumPy style); explain *why*, not just *what*
- Keep functions pure when practical; minimize hidden state and side effects
- Validate and sanitize all external inputs (CLI args, env vars, HTTP payloads, files)
- Never commit secrets; load from environment or a secure store; support `.env` for local dev only
- In example scripts that set environment variables or temp state, **restore/cleanup before exit**
- Use `argparse` or `typer` for CLIs; provide `--help` and sensible defaults
- Prefer composition over inheritance; use abstract base classes or Protocols when polymorphism is needed
- Avoid `eval`/`exec` and dynamic imports; if unavoidable, encapsulate, validate, and justify in comments
- Write deterministic tests with `pytest`; include positive, negative, and exception cases
- Isolate tests from network, time, and randomness (use fixtures, mocks; seed RNGs where used)
- Enforce and monitor coverage (e.g., ≥90% lines/branches) for critical modules
- Pin dependencies and record them (`pyproject.toml`/`requirements.txt`); avoid unnecessary packages
- Keep modules importable and fast; defer heavy imports/work to runtime where possible
- Prefer immutable data (e.g., `tuple`, `frozenset`) when feasible; use `typing.Final` for constants
- Use `from __future__ import annotations` (Python 3.11-) to improve typing performance and ergonomics
- Return early to reduce nesting; keep cyclomatic complexity low
- Prefer explicit `None` checks and `is`/`is not` over truthiness for sentinel values
- Serialize with standard libraries (`json`, `dataclasses.asdict`) unless a strong reason exists otherwise
- When performance matters, measure first (`timeit`, `cProfile`, `perf_counter`); optimize hot paths only
- Protect concurrency with correct primitives (`threading`, `asyncio`, `multiprocessing`) and avoid shared mutable state
- Public APIs are stable and documented; breaking changes require a major version bump (SemVer)
