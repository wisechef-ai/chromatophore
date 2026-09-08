.PHONY: test lint proof clean help

help:
	@echo "make test   - THE canonical command: lint, suite, live proof"
	@echo "make lint   - syntax only (fast)"
	@echo "make proof  - live repaint proof against the real Hermes skin engine"

# Syntax-only by design: a plugin that will not parse fails silently inside the
# agent's process, so this must be cheap enough to run on every edit.
lint:
	@python3 -m compileall -q . -x '\.worktrees|__pycache__|\.git' && echo "lint ok"

test: lint
	@python3 -m pytest tests/ -q
	@python3 tests/proofs/live_repaint_proof.py

# Needs the Hermes venv on the path; skipped rather than failed when absent, so
# `make test` stays green on a machine without Hermes installed.
proof:
	@python3 tests/proofs/live_repaint_proof.py

clean:
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null; true
	@find . -name '*.pyc' -delete 2>/dev/null; true
