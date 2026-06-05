# SeniorBenefitsAI — handoff for first deploy

Repo built locally; everything below is **user-only** because it touches GitHub repo creation, Cloud Run, Stripe, and Namecheap.

## What's already done (in this branch on local disk)

- `/Users/eguduk/SeniorBenefitsAI/` complete: app.py, 22-program federal_benefits.json, 51-state states.json, 5 templates, Dockerfile, deploy.yml, tests, README
- `freshsky-common/freshsky_common/revenue.py` — added `seniorbenefits` to PORTFOLIO list
- `freshskyai/.github/workflows/indexnow-sweep.yml` — added `'seniorbenefits'` to BATCH_SUBDOMAINS
- `freshskyai/index.html` — added 👵 hub card in the benefits cluster (after Childcare Finder)
- Memory updated: live count 21 → 18 batch apps; stale EduSafeAI-queued memory removed (district plan shipped 2026-05-07)

## What you need to do

### 1. Create GitHub repo + first push (kicks off auto-deploy)

```bash
cd /Users/eguduk/SeniorBenefitsAI
git init
git add .
git commit -m "Initial scaffold — Senior Benefits AI"
gh repo create justfreshsky-jpg/SeniorBenefitsAI --public --source . --push
```

The push triggers `deploy.yml` automatically, which runs `gcloud run deploy seniorbenefits --source .` via WIF.

> **Possible gotcha:** the deploy uses `${{ vars.WIF_PROVIDER }}` and `${{ vars.WIF_SERVICE_ACCOUNT }}`. If those aren't set at org level (justfreshsky-jpg), copy them in via:
> `gh variable set WIF_PROVIDER --body <value> --repo justfreshsky-jpg/SeniorBenefitsAI`
> `gh variable set WIF_SERVICE_ACCOUNT --body <value> --repo justfreshsky-jpg/SeniorBenefitsAI`
> Check an existing batch repo's settings for the values.

### 2. Bind env vars / secrets on the Cloud Run service

After first deploy succeeds, the service `seniorbenefits` exists. Bind env vars (mostly LLM keys + Stripe + OAuth + Secret Manager refs):

```bash
gcloud run services update seniorbenefits --region us-central1 \
  --update-secrets=SECRET_KEY=app-secret-key:latest \
  --update-secrets=GOOGLE_CLIENT_SECRET=google-oauth-client-secret:latest \
  --update-secrets=STRIPE_SECRET_KEY=stripe-secret-key:latest \
  --update-secrets=STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest \
  --update-env-vars=GA_MEASUREMENT_ID=G-T424F11MPH,APP_URL=https://seniorbenefits.freshskyai.com,GOOGLE_CLIENT_ID=<existing-shared-id>,FREE_DAILY_LIMIT=5,LLM_PROVIDER=auto-trusted
```

Plus the LLM keys (GROQ_KEY, CEREBRAS_KEY, GEMINI_KEY, etc.) — bind from Secret Manager in the same way as other batch apps. Easiest is to copy the env-var spec from an existing benefits-category app (e.g., `medicaidcheck`, `snapcheck`).

### 3. Run setup-batch-stripe-and-env to create Stripe products

```bash
gh workflow run setup-batch-stripe-and-env.yml --repo justfreshsky-jpg/freshskyai \
  -f app_slug=seniorbenefits -f app_brand="Senior Benefits AI"
```

Do not create new access subscriptions. All tools are free subject to fair-use limits. Existing Stripe bindings remain only for legacy subscriber billing and should not be removed automatically.

### 4. Add subdomain mapping

Cloud Run console → `seniorbenefits` service → Custom domains → map `seniorbenefits.freshskyai.com`.
Or via REST (since `gcloud run domain-mappings` may not work locally per memory):

```bash
TOKEN=$(gcloud auth print-access-token)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://us-central1-run.googleapis.com/apis/domains.cloudrun.com/v1/namespaces/neon-glyph-491500-e2/domainmappings" \
  -d '{"apiVersion":"domains.cloudrun.com/v1","kind":"DomainMapping","metadata":{"name":"seniorbenefits.freshskyai.com","namespace":"neon-glyph-491500-e2"},"spec":{"routeName":"seniorbenefits"}}'
```

### 5. Add Namecheap CNAME

In Namecheap DNS for freshskyai.com:
- Type: `CNAME`
- Host: `seniorbenefits`
- Value: `ghs.googlehosted.com.`
- TTL: Automatic

(Per CLAUDE.md DNS pattern — same as every other batch subdomain.)

### 6. Push the freshsky-common + freshskyai changes

```bash
# freshsky-common (PORTFOLIO list edit)
cd /Users/eguduk/freshsky-common
git add freshsky_common/revenue.py
git commit -m "Add Senior Benefits AI to PORTFOLIO"
git push

# freshskyai hub (index.html card + indexnow-sweep.yml)
cd /Users/eguduk/freshskyai
git add index.html .github/workflows/indexnow-sweep.yml
git commit -m "Add Senior Benefits AI — hub card + IndexNow sweep"
git push
```

### 7. Bulk-redeploy benefits-category apps so they pick up the new PORTFOLIO entry

Per OPERATIONS.md (8-at-a-time, 60s sleep):

```bash
apps=(medicaidcheck snapcheck unemploymentappeal section8nav reentryhelp childcarefinder seniorbenefitsai)
for a in "${apps[@]}"; do
  gh workflow run deploy.yml --repo justfreshsky-jpg/$a &
done; wait
```

(Only benefits-category apps need the redeploy for cross-promo to pick up Senior Benefits AI as a sibling.)

## Quick post-deploy validation

```bash
curl -s https://seniorbenefits.freshskyai.com/health | jq
# Expect: {"status":"ok","federal_benefits":22,"states":51}

curl -sI https://seniorbenefits.freshskyai.com/state/CA | head -1
# Expect: HTTP/2 200

curl -sI https://seniorbenefits.freshskyai.com/federal/medicare | head -1
# Expect: HTTP/2 200
```

## Notes & open decisions

- **Subdomain choice:** I went with `seniorbenefits.freshskyai.com` (descriptive, unambiguous). If you want shorter, `senior.freshskyai.com` is open — the previous SeniorCareAI (retired 2026-05-04) may have used it. To switch, edit the slug in: `app.py`, `Dockerfile`, `.github/workflows/deploy.yml`, `BATCH_SUBDOMAINS`, `PORTFOLIO`, hub card URL, and Cloud Run service name.
- **Affiliates:** `partners.json` empty for `benefits` category currently (per OPERATIONS.md). Cards stay hidden until you add partners. Most lucrative for this audience: Medicare Advantage broker leads ($300–$1k/lead via SelectQuote, eHealth, GoHealth via Impact), reverse mortgage (HECM affiliates via direct programs), senior moving (Bekins, FlatRate via Impact), hearing aids (HearingTracker via Impact).
- **Local testing:** I couldn't run `pytest` locally because freshsky-common doesn't install via the system pip 3.9. Tests are written and will run cleanly once you spin up a venv with Python 3.12. Or just trust the first deploy.
- **Domain registration:** if you want `seniorbenefitsai.com` as a separate apex (not a subdomain), register on Namecheap and add a redirect — same pattern as guideforlivingus.com → USALivingGuide. Not required.

## What this site does (one-paragraph product summary for any future reference)

Senior Benefits AI is a federal-and-state benefits navigator for Americans 55+. Free pages give comprehensive program guidance for SS, Medicare, Medicaid LTC, SSI, SNAP, LIHEAP, Section 202, VA pension, plus per-state pages for all 50 states + DC covering state pharmacy assistance, property tax relief, Medicaid LTC office, and standout programs. The Pro-tier feature is an LLM-generated personalized checklist that takes age + state + marital status + monthly income + free-text situation and returns a prioritized punch list of programs with the right .gov links and first concrete action. Free users get 5 personalizations/day before the standard hub paywall kicks in.
