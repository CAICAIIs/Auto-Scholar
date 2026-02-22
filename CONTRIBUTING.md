# Contributing to Auto-Scholar

Thanks for your interest in contributing.

## Ways to Contribute

- Report bugs and UX issues
- Improve docs and examples
- Add tests or improve reliability
- Submit feature PRs aligned with project scope

## Development Setup

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for local setup and command references.

## Pull Request Process

1. Fork and create a topic branch from `main`
2. Keep changes focused and small
3. Update docs when behavior/contracts change
4. Ensure all required checks pass
5. Open PR with clear context and screenshots/logs if relevant

## Required Checks

### Backend

```bash
ruff check backend/
ruff format backend/ --check
find backend -name '*.py' -exec python -m py_compile {} +
```

### Frontend

```bash
cd frontend && bun x tsc --noEmit
cd frontend && bun run lint
```

## Coding Guidelines

- Python: absolute imports from `backend.*`, typed functions, async network I/O
- TypeScript: use `@/` aliases, keep components focused and testable
- Avoid unrelated refactors in feature/fix PRs
- Keep API schemas and docs synchronized

## Commit Messages

Use clear, scoped messages, for example:

- `feat(backend): add pubmed source filter`
- `fix(frontend): handle empty citation list`
- `docs: update API start/approve examples`

## Questions

Open a GitHub issue for architecture discussions before implementing major changes.
