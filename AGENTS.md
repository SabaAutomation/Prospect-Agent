# Prospect Agent: notes for coding agents (Codex CLI, Claude Code, etc.)

## What this project is
A local-first team of agents: Finder -> Auditor -> Scorer -> Writer, run by a Supervisor
(`app/pipeline.py`). A human approves every draft in a web dashboard. Nothing is ever sent automatically.

## Rules that must not be broken
- Never add auto-send of emails or messages. Approved drafts are exported only.
- Auditor must keep respecting robots.txt and rate limits (`PROSPECT_DELAY`).
- The LLM only phrases text. Facts (findings, scores) come from deterministic code.
- Any new draft path must go through `writer.validate()` and keep the template fallback.
- Keep it free and local: Ollama only, no paid APIs, no required cloud services.

## Commands
- Setup: `python -m venv .venv`, activate it, `pip install -r requirements-dev.txt`
- Test: `pytest -q` (must stay green; add tests for every new check or step)
- Demo without internet or Ollama: `python -m app.cli run --demo`
- Dashboard: `python -m app.cli serve` then open http://127.0.0.1:8000

## Layout
- `app/auditor.py` fetch + checks, `app/scorer.py` score, `app/writer.py` draft + validation
- `app/finder.py` OpenStreetMap/CSV, `app/pipeline.py` supervisor, `app/db.py` SQLite state
- `app/web.py` approval dashboard, `app/cli.py` commands, `app/demo.py` offline demo data

## Good next tasks
1. Playwright fallback for JavaScript-only sites (keep it optional).
2. A new niche preset with its own audit checks (e.g. restaurants: menu link, reservations).
3. An eval set: 30 saved HTML pages with expected findings, scored in CI.
4. An MCP server exposing `audit_site` and `list_prospects` tools.
