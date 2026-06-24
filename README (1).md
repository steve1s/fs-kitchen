# FareShare Seasonal Kitchen 🌿

Free recipe app for students, volunteers and community kitchens.
Searches **real FareShare recipes** first, falls back to AI generation.

---

## Your 3 files

| File | What it is |
|---|---|
| `index.html` | The entire app |
| `scrape.py` | Run once on your computer to collect FareShare recipes |
| `worker.js` | Deploy to Cloudflare to enable AI fallback (free) |

---

## Step 1 — Scrape FareShare recipes (run on your computer)

```bash
pip install requests beautifulsoup4
python scrape.py           # scrapes ~100 recipes → saves recipes.json
python scrape.py --test    # quick test: 5 recipes only
```

This creates `recipes.json`. Put it in the same folder as `index.html`.
Re-run whenever you want to refresh recipes from the site.

---

## Step 2 — Deploy to GitHub Pages (free, 3 minutes)

1. Go to **github.com/new** → name it `fareshare-kitchen` → Public → Create
2. Upload `index.html` and `recipes.json` (Add file → Upload files)
3. Go to **Settings → Pages → Source: Deploy from branch → main / root → Save**
4. Your app is live at: `https://YOUR-USERNAME.github.io/fareshare-kitchen`

---

## Step 3 — Deploy Cloudflare Worker for AI fallback (free)

Enables AI recipe generation when no FareShare recipe matches.

1. Sign up free at **cloudflare.com** (no card needed)
2. Go to **Workers & Pages → Create Worker**
3. Name it `fareshare-kitchen`, click Deploy
4. Click **Edit code**, delete starter code, paste all of `worker.js`, Deploy
5. Go to **Settings → Variables → Add variable**:
   - Name: `ANTHROPIC_API_KEY`
   - Value: your key from console.anthropic.com
   - Tick **Encrypt** → Save and deploy
6. Your Worker URL: `https://fareshare-kitchen.YOUR-NAME.workers.dev`

### Connect to the app

**Option A** — Hardcode it (best for public deployment):
Open `index.html`, find line:
```js
const WORKER_URL = "";
```
Change to:
```js
const WORKER_URL = "https://fareshare-kitchen.YOUR-NAME.workers.dev";
```
Then re-upload `index.html` to GitHub.

**Option B** — Enter it in the app:
Open the live app → paste Worker URL in the yellow banner → Save & connect.

---

## How the app works

1. User picks ingredients from the tabbed picker (seasonal / veg / meat / spices / cupboard)
2. App searches `recipes.json` for the best matching FareShare recipe
3. If a good match is found → shows the real FareShare recipe with a link to the original
4. If no match → calls the Cloudflare Worker → AI generates a custom recipe
5. Every recipe shows seasonal ingredient highlights, FareShare tips, and swap suggestions

## Cost

| | Cost |
|---|---|
| GitHub Pages | Free forever |
| Cloudflare Workers | Free (100k requests/day) |
| Anthropic API | ~£0.002 per AI recipe |

---

## Updating recipes

When FareShare adds new recipes, re-run:
```bash
python scrape.py
```
Then re-upload `recipes.json` to GitHub.
