# Prospect Agent

A free, local team of agents that finds local businesses, audits their websites, scores them as leads, and drafts a
personalised, honest outreach message. **You approve every message. Nothing is sent automatically.**

```
Finder -> Auditor -> Scorer -> Writer        Supervisor handles retries, rate limits, dedupe, resume, tracing
(OSM/CSV) (real checks) (rules)  (Ollama + validation + template fallback)        Dashboard: review, edit, approve
```

## How I came up with this

![Hand-sketched board showing how Prospect Agent went from idea to a working agent team](docs/ideation.png)

I started from three earlier projects (a harness lab, an automation project and a multi-document RAG brain) and looked for a
fourth that shows different skills: tool use, multi-agent hand-offs, and a human approval step. I dropped a document-processing idea
because it overlapped my RAG project, and chose a lead-research agent team that also helps me find freelance clients.
Before writing code I set the rules: facts come from code and not the model, a human approves everything, crawling is polite,
and a template takes over if the model fails.

## 1. Setup (VS Code terminal)

Windows PowerShell:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```
macOS / Linux:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```
Edit `.env`: set `PROSPECT_SENDER_NAME`, `PROSPECT_OFFER`, and `PROSPECT_MODEL` to a model you have (`ollama list`).

## 2. Check everything works

```bash
pytest -q                          # 16 tests, no internet or Ollama needed
python -m app.cli run --demo       # offline demo with fake businesses
python -m app.cli serve            # open http://127.0.0.1:8000
```

## 3. Use it for real

```bash
ollama pull qwen2.5:7b             # or any model you already have
python -m app.cli doctor           # confirms Ollama and the model
python -m app.cli run --niche dentist --city Islamabad --limit 20
python -m app.cli serve            # review, edit, approve or reject
python -m app.cli export > approved.csv
```
OpenStreetMap only lists businesses that have a website tag, so results vary by city. If a city comes back thin, use your
own list: `python -m app.cli run --csv data/sample_prospects.csv`.
Other commands: `list`, `resume` (continue after a crash), and `--niche key=value` for any OSM tag (e.g. `shop=bakery`).

## How it stays honest and safe
- **Facts come from code, not the model.** The Auditor makes deterministic checks (no mobile viewport, no booking, no WhatsApp, slow load,
  old copyright year, and so on). The model only phrases the message.
- **Drafts are validated.** Length, spam words, placeholders, and at least one real audit observation. Three tries, then a plain template.
  So a weak local model cannot ship a vague draft, and the tool still works with Ollama off.
- **Polite crawling.** Respects `robots.txt`, one homepage request per business, delay between requests, identifiable user agent.
  Set a real contact in `PROSPECT_USER_AGENT`.
- **No auto-send.** Approved drafts are exported. Check the cold-email and anti-spam rules where you and the recipient live, and keep the opt-out line.
- **Resumable and traceable.** State lives in `data/prospects.db`; the `/trace` page shows every step, its time, and failures.

## Roadmap ideas (good Codex tasks)
Playwright fallback for JavaScript-only sites, restaurant and clinic audit presets, an eval set of saved pages,
an MCP server exposing `audit_site`, and a follow-up reminder queue. See `AGENTS.md`.
