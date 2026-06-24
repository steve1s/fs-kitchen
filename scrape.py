#!/usr/bin/env python3
"""
FareShare Recipe Scraper
Scrapes all recipes from https://fareshare.org.uk/recipes/
and saves them to recipes.json (put this next to index.html)

Usage:
    pip install requests beautifulsoup4
    python scrape.py          # scrape everything (~100 recipes)
    python scrape.py --test   # scrape first 5 only (for testing)
"""

import json, time, re, sys, argparse, os
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("❌  Missing dependencies. Run:  pip install requests beautifulsoup4")
    sys.exit(1)

BASE        = "https://fareshare.org.uk"
RECIPES_URL = BASE + "/recipes/"
OUTPUT_FILE = "recipes.json"
DELAY       = 1.5   # seconds between requests — polite crawling

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
})


# ── HELPERS ──────────────────────────────────────────────────────────────

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            print(f"\n  ⚠  Retry {attempt + 1}/3 for {url}: {e}")
            time.sleep(3)


def clean(el):
    return el.get_text(" ", strip=True) if el else ""


def strip_quantity(text):
    """'200g chicken breast' → 'chicken breast'"""
    text = text.strip()
    cleaned = re.sub(
        r"^[\d½¼¾⅓⅔\s\.\-–]+(?:g|kg|ml|l|cl|tsp|tbsp|oz|lb|lbs|cup|cups"
        r"|can|cans|tin|tins|jar|jars|bag|bags|bunch|bunches|head|heads"
        r"|clove|cloves|sprig|sprigs|handful|handfuls|pinch|pinches"
        r"|large|medium|small|x|piece|pieces|slice|slices)?\s*",
        "", text, flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(r"\s*\(.*?\)", "", cleaned).strip()
    return cleaned or text


# ── LISTING PAGES ─────────────────────────────────────────────────────────

def collect_recipe_urls(test_mode=False):
    print("📄  Fetching listing page 1 …")
    soup = fetch(RECIPES_URL)

    # How many listing pages are there?
    max_page = 1
    for a in soup.find_all("a", href=True):
        m = re.search(r"/recipes//page/(\d+)", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    print(f"    Found {max_page} listing pages")

    def extract_urls(soup):
        urls = []
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if a:
                href = a["href"]
                if not href.startswith("http"):
                    href = BASE + href
                if "/recipes/" in href and href.rstrip("/") != RECIPES_URL.rstrip("/"):
                    if href not in urls:
                        urls.append(href)
        return urls

    all_urls = extract_urls(soup)

    if test_mode:
        print("    TEST MODE — using first 5 recipe URLs only")
        return all_urls[:5]

    for page in range(2, max_page + 1):
        url = f"{RECIPES_URL}/page/{page}"
        print(f"📄  Listing page {page}/{max_page} …", end=" ", flush=True)
        try:
            soup = fetch(url)
            new  = [u for u in extract_urls(soup) if u not in all_urls]
            all_urls.extend(new)
            print(f"+{len(new)} (total: {len(all_urls)})")
        except Exception as e:
            print(f"⚠  skipped: {e}")
        time.sleep(DELAY)

    return all_urls


# ── RECIPE PAGE ───────────────────────────────────────────────────────────

def scrape_recipe(url):
    soup = fetch(url)

    # Title
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = clean(h1)
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").replace("- FareShare", "").strip()

    # Description — first decent paragraph
    description = ""
    for p in soup.find_all("p"):
        txt = clean(p)
        if (len(txt) > 60
                and "newsletter" not in txt.lower()
                and "cookie" not in txt.lower()
                and "FareShare is a" not in txt):
            description = txt
            break

    # Ingredients + Method — walk headings to find sections
    ingredients_raw, method_steps = [], []
    current_section = None

    for el in soup.find_all(["h2", "h3", "h4", "li", "p"]):
        txt = clean(el)
        if el.name in ("h2", "h3", "h4"):
            tl = txt.lower()
            if "ingredient" in tl:
                current_section = "ingredients"
            elif any(w in tl for w in ("method", "instruction", "direction", "step", "how to")):
                current_section = "method"
            else:
                current_section = None
        elif el.name == "li" and txt:
            if current_section == "ingredients" and len(txt) < 250:
                ingredients_raw.append(txt)
            elif current_section == "method" and len(txt) < 600:
                method_steps.append(txt)

    # Fallback: grab first <ol> if method is still empty
    if not method_steps:
        for ol in soup.find_all("ol"):
            items = [clean(li) for li in ol.find_all("li") if clean(li)]
            if len(items) >= 2:
                method_steps = items
                break

    # Diet tags from WordPress tags/categories
    diet_tags = []
    for a in soup.select(".post-tags a, .tags a, .entry-tags a, .cat-links a"):
        t = clean(a).lower()
        for label in ["vegan", "vegetarian", "gluten-free", "dairy-free", "nut-free", "pescatarian", "halal"]:
            if label.replace("-", " ") in t or label in t:
                diet_tags.append(label.replace("-", " ").title())

    # Difficulty + time from any short text block
    difficulty, cook_time = "", ""
    for el in soup.find_all(["span", "p", "div", "li"]):
        txt = clean(el)
        if not txt or len(txt) > 60:
            continue
        tl = txt.lower()
        if not difficulty:
            m = re.search(r"\b(easy|moderate|medium|difficult|hard)\b", tl)
            if m:
                difficulty = m.group(1).title()
        if not cook_time and re.search(r"\d+\s*(min|minute|hour)", tl):
            cook_time = txt

    # Clean ingredient names for search matching
    ingredient_names = []
    for raw in ingredients_raw:
        name = strip_quantity(raw).lower()
        if name and len(name) > 1:
            ingredient_names.append(name)

    return {
        "title":            title,
        "url":              url,
        "description":      description,
        "ingredients_raw":  ingredients_raw,
        "ingredient_names": ingredient_names,
        "method":           method_steps,
        "diet_tags":        list(set(diet_tags)),
        "difficulty":       difficulty,
        "cook_time":        cook_time,
        "source":           "fareshare.org.uk",
    }


# ── MAIN ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape FareShare recipes")
    parser.add_argument("--test", action="store_true", help="Scrape first 5 recipes only")
    args = parser.parse_args()

    print("🌿  FareShare Recipe Scraper")
    print("=" * 50)
    if args.test:
        print("🧪  TEST MODE\n")

    # 1. Collect URLs
    all_urls = collect_recipe_urls(test_mode=args.test)
    print(f"\n✅  {len(all_urls)} recipe URLs found\n")

    # 2. Scrape each recipe
    recipes, errors = [], []

    for i, url in enumerate(all_urls, 1):
        slug = url.rstrip("/").split("/")[-1]
        sys.stdout.write(f"\r🍳  [{i:>3}/{len(all_urls)}]  {slug[:55]:<55}")
        sys.stdout.flush()
        try:
            r = scrape_recipe(url)
            if r["title"] and r["ingredients_raw"]:
                recipes.append(r)
            else:
                errors.append((url, "No title or ingredients found"))
        except Exception as e:
            errors.append((url, str(e)))
        time.sleep(DELAY)

    print(f"\n\n✅  Scraped {len(recipes)} recipes")
    if errors:
        print(f"⚠   {len(errors)} failed:")
        for url, msg in errors[:5]:
            print(f"    • {url.split('/')[-2]}: {msg}")

    # 3. Save
    output = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "source":     "https://fareshare.org.uk/recipes/",
        "total":      len(recipes),
        "recipes":    recipes,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(OUTPUT_FILE) // 1024
    print(f"💾  Saved → {OUTPUT_FILE}  ({size_kb} KB)")

    print("\nSample recipes:")
    for r in recipes[:6]:
        print(f"  • {r['title']}  "
              f"({len(r['ingredients_raw'])} ingredients, {len(r['method'])} steps)")

    print(f"\n📌  Copy {OUTPUT_FILE} into the same folder as index.html")
    print("    Then open index.html in a browser — it loads automatically.\n")


if __name__ == "__main__":
    main()
