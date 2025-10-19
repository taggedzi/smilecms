---
name: Python Best Practices
globs: ["**/*.py", "tests/**/*.py", "pyproject.toml"]
---

# Python Rules (Clean, Testable, Performant)

## Clarity & Structure

- Prefer readable over clever; one responsibility per function (≈5–30 lines when practical).
- Name well: nouns for data (`order_repo`), verbs for actions (`calculate_total`).
- Separate concerns: pure domain logic ↔ I/O/orchestration ↔ configuration.
- Keep public API small; mark internal helpers with leading `_` or exclude via `__all__`.

## Types & Contracts

- Use type hints everywhere; code must be `mypy`/`pyright` clean (no silent `Any`).
- Use `Protocol`, `TypedDict`/`dataclasses`, `NewType` for boundary clarity.
- Avoid `*args/**kwargs` unless forwarding; prefer explicit parameters.

## Errors

- Fail fast near the source; raise specific exceptions with actionable messages.
- Don’t blanket-catch `Exception`. Catch-and-wrap 3rd-party errors as domain exceptions.

## Configuration

- Load config once (env/TOML/YAML), validate, and inject explicitly. No hidden globals.
- Support sensible defaults; document all config keys.
- Scripts that set env vars must restore them before exit.

## Testing

- Write fast, deterministic unit tests for pure logic; use fakes for I/O.
- Cover negative/edge/exception paths. Keep a few integration/system tests.
- Use pytest fixtures and `tmp_path`. Aim for >90% coverage on core logic.

## Data Modeling

- Prefer `@dataclass(frozen=True)` (or pydantic at the boundary) over loose dicts.
- Validate inputs at edges; assume validity inside.

## Logging & Observability

- Use stdlib `logging` with module-level loggers. No `print()` in libraries.
- Log events (inputs/outputs at boundaries, warnings, errors), not noise.

## Performance

- Profile before optimizing (`cProfile`, `py-spy`, `scalene`).
- Use the right containers: `dict/set` for membership; `deque` for ends; avoid O(n²).
- Stream with generators; avoid huge intermediates.
- Use `lru_cache` for hot pure functions. Use `asyncio` for high-latency I/O; multiprocessing for CPU-bound.

## Style & Hygiene

- Enforce PEP 8 automatically (`ruff format`/`black`). Keep imports ordered.
- No magic numbers/strings—use constants.
- Docstrings for public functions/classes: purpose, params, returns, raises, short example.

## Dependencies

- Prefer stdlib first; keep deps minimal. Optional features behind extras/lazy imports.
- Pin version ranges in `pyproject.toml`; lock in CI builds if reproducibility matters.

## Boundaries & Interfaces

- Isolate third-party SDKs behind adapters. Keep serialization/deserialization at the edges.

## Resources & Safety

- Use context managers for files/sockets/locks. Add timeouts/retries for I/O. Design idempotent operations.

## CLI

- Keep CLI thin (argparse/typer) over testable functions. Return exit codes.

## Security

- Never log secrets. Validate/sanitize external inputs. Avoid `pickle` across trust boundaries.

## Docs & Change Safety

- Keep a concise README + Architecture note. Examples must run.
- Semantic versioning (libs), meaningful changelogs, feature flags for risky changes.

## Automation

- Pre-commit: ruff (lint+format), mypy, pytest (quick set), docstring check.
- CI: run tests + type checks + linters; fail on violations.

## Anti-patterns (reject)

- God classes/functions; “misc utils” dumping grounds.
- Hidden I/O in pure functions. Global mutable state/config.
- Catch-all `except Exception:` with no re-raise/context.
- Premature optimization without data. Overuse of inheritance.

