# Senior Benefits AI

Federal and state benefits navigator for Americans 55+. Forwards users to authoritative .gov resources rather than duplicating them.

- **Live:** https://seniorbenefits.freshskyai.com (after first deploy + Cloud Run domain mapping)
- **Slug:** `seniorbenefits`
- **Category:** `benefits`
- **Access:** free subject to fair-use limits; legacy `/subscribe` routes redirect to voluntary sponsorship.

## Routes

| Route | Purpose |
|---|---|
| `/` | Landing page with personalized checklist tool + state picker + federal browser |
| `/federal` | All federal programs grouped by category |
| `/federal/<key>` | Detail page for a single federal program |
| `/state/<code>` | State-specific senior programs (50 states + DC) |
| `/api/personalized-checklist` (POST) | LLM-powered checklist gated by freemium |
| `/api/states` | JSON list of all 51 state entries |
| `/health` | Health check (returns counts of programs/states loaded) |

## Data

- [federal_benefits.json](federal_benefits.json) — 22 federal programs in 6 categories
- [states.json](states.json) — 51 state entries (50 states + DC), each with department of aging, Medicaid LTC, property tax program, optional SPAP, and 2–3 standout programs

Both files are loaded at startup. Editing them and pushing triggers redeploy automatically (path filter matches in `.github/workflows/deploy.yml`).

Federal entries with annual SSA/CMS amounts include `figures_as_of` and `figure_sources` fields so the UI shows when and where those numbers were verified.

## Personalized-checklist privacy

- Personalized prompts and generated checklists are not stored in the application response cache.
- `/api/personalized-checklist` responses use private `no-store` cache controls and `X-Robots-Tag: noindex, nofollow, noarchive`.
- Checklist request bodies are capped at 32 KB, and select fields accept only the options exposed in the UI to bound prompt size and cost.
- Generated result text is rendered with safe DOM nodes; only HTTPS links on `.gov`, `.mil`, BenefitsCheckUp, or SHIP Help hosts become clickable.

## Local development

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:8080
```

Tests:
```bash
pip install pytest
pytest tests/
```

## Disclosure

Senior Benefits AI is educational. We summarize publicly available program rules and forward to authoritative .gov agencies. Eligibility, income limits, and benefit amounts change — confirm with the agency before relying on any number.
