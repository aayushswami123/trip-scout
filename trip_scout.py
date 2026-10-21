"""trip-scout: scrape Wikivoyage travel listings (See, Do, Eat, Sleep) for one or more cities.

Usage: python trip_scout.py "Tempe" "Sedona" "Flagstaff"
       python trip_scout.py "Tempe" "Sedona" --compare
"""
import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

from scrapling.fetchers import Fetcher

USER_AGENT = "trip-scout/0.1 (student project; aayushswami.dev@gmail.com)"
BASE_URL = "https://en.wikivoyage.org/wiki/"
SECTIONS = ["See", "Do", "Eat", "Sleep"]
OUTPUT_DIR = Path("output")
FIELDS = ["city", "section", "name", "description", "price", "hours", "website", "latitude", "longitude"]

# Every listing on Wikivoyage is a <bdi class="vcard"> (found by inspecting the Tempe and Phoenix pages).
# A stray <span class="vcard"> also exists on some pages, but it is a map widget, not a listing.
LISTING_SELECTOR = "bdi.vcard"

# adaptive=True needs somewhere to remember what a listing looked like. The domain is fixed so
# that what we learn on the Tempe page is reused for every other city.
Fetcher.configure(
    adaptive=True,
    adaptive_domain="en.wikivoyage.org",
    storage_args={"storage_file": str(OUTPUT_DIR / ".adaptive.db"), "url": "en.wikivoyage.org"},
)


def shorten(text, limit=300):
    """Cut long descriptions at a word boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def clean(text):
    """Collapse whitespace; return '' for None."""
    return re.sub(r"\s+", " ", text or "").strip()


def first_text(node, selector):
    """Text of the first element matching `selector` inside `node`, or '' if it's missing."""
    found = node.css(selector)
    return clean(found[0].get_all_text()) if found else ""


def section_of(listing):
    """Name of the closest <h2> heading above this listing (e.g. 'Eat'), or '' if none."""
    headings = listing.xpath("preceding::h2[1]")
    return headings[0].attrib.get("id", "") if headings else ""


def parse_listing(node, city, section):
    name_link = node.css(".listing-name a")
    website = ""
    if name_link:
        href = name_link[0].attrib.get("href", "")
        website = href if href.startswith("http") else ""
    lat = first_text(node, ".latitude")
    lon = first_text(node, ".longitude")
    return {
        "city": city,
        "section": section,
        "name": first_text(node, ".listing-name"),
        "description": shorten(first_text(node, ".listing-content")),
        "price": first_text(node, ".listing-price"),
        "hours": first_text(node, ".listing-hours"),
        "website": website,
        "latitude": lat,
        "longitude": lon,
    }


def scrape_city(city):
    """Fetch one city page. Returns (listings, error_message)."""
    url = BASE_URL + quote(city.strip().replace(" ", "_"))
    try:
        page = Fetcher.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, retries=2)
    except Exception as exc:  # network down, DNS failure, timeout, ...
        return [], f"could not fetch {url} ({type(exc).__name__}: {exc})"

    if page.status == 404:
        return [], f"no Wikivoyage page called '{city}' (404). Check the spelling."
    if page.status != 200:
        return [], f"{url} returned HTTP {page.status}"

    # auto_save stores what a listing looks like; adaptive finds them again if the selector breaks.
    nodes = page.css(LISTING_SELECTOR, identifier="wikivoyage-listing", adaptive=True, auto_save=True)
    if len(nodes) == 1:
        # Adaptive mode may relocate just one best match; grab its look-alikes (the other listings).
        nodes = [nodes[0], *nodes[0].find_similar()]

    listings = []
    for node in nodes:
        section = section_of(node)
        if section in SECTIONS:
            item = parse_listing(node, city, section)
            if item["name"]:  # skip malformed entries with no name
                listings.append(item)
    return listings, None


def slug(city):
    """'Las Vegas' -> 'las_vegas', safe to use in a filename."""
    return re.sub(r"[^\w\-]+", "_", city.strip().lower()).strip("_")


def save_json(city, listings):
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = slug(city) + ".json"
    (OUTPUT_DIR / filename).write_text(json.dumps(listings, indent=2, ensure_ascii=False), encoding="utf-8")


def save_csv(all_listings):
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "all_cities.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_listings)


def print_summary(counts):
    print(f"\n{'City':<20} {'Section':<10} {'Count':>5}")
    print("-" * 37)
    for city, per_section in counts.items():
        for section in SECTIONS:
            print(f"{city:<20} {section:<10} {per_section[section]:>5}")
    print("-" * 37)


def completeness(item):
    """Score a listing by how much useful info it has. More info = better pick for a plan."""
    return sum(bool(item[k]) for k in ("description", "website", "hours", "latitude"))


def pick(listings, section, how_many):
    """Pick the best `how_many` listings from one section (most complete first, page order breaks ties)."""
    in_section = [item for item in listings if item["section"] == section]
    # sorted() is stable, so equally complete listings stay in the order they appear on the page
    return sorted(in_section, key=completeness, reverse=True)[:how_many]


def plan_line(item):
    """One markdown bullet for a place: name, short description, and any hours/price/website we have."""
    name = f"[{item['name']}]({item['website']})" if item["website"] else item["name"]
    line = f"- **{name}**"
    if item["description"]:
        line += f" - {item['description']}"
    details = []
    if item["hours"]:
        details.append(f"Hours: {item['hours']}")
    if item["price"]:
        details.append(f"Price: {item['price']}")
    if details:
        line += f" _({'; '.join(details)})_"
    return line


def save_day_plan(city, listings):
    """Write output/<city>_day_plan.md: 2 See + 1 Eat + 1 Do, ordered like a day. Returns the path."""
    see = pick(listings, "See", 2)
    eat = pick(listings, "Eat", 1)
    do = pick(listings, "Do", 1)

    # (heading, places) in the order they happen during the day; sections with no listings are skipped
    stops = [
        ("Morning - See", see[:1]),
        ("Lunch - Eat", eat),
        ("Afternoon - See", see[1:]),
        ("Evening - Do", do),
    ]
    lines = [f"# 1-day plan for {city}", "", "_Built from Wikivoyage listings by trip-scout._", ""]
    for heading, places in stops:
        if places:
            lines += [f"## {heading}", ""] + [plan_line(p) for p in places] + [""]
    if len(lines) == 4:  # nothing was added besides the title
        lines.append("Not enough listings found to build a plan.")

    path = OUTPUT_DIR / f"{slug(city)}_day_plan.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_comparison(counts):
    """Side-by-side table: one row per section, one column per city."""
    cities = list(counts)
    print(f"\n{'Section':<10}" + "".join(f"{c:>14}" for c in cities))
    print("-" * (10 + 14 * len(cities)))
    for section in SECTIONS:
        print(f"{section:<10}" + "".join(f"{counts[c][section]:>14}" for c in cities))
    print(f"{'Total':<10}" + "".join(f"{sum(counts[c].values()):>14}" for c in cities))


def main(cities, compare=False):
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_listings, counts, errors = [], {}, []

    for i, city in enumerate(cities):
        if i > 0:
            time.sleep(random.uniform(1, 2))  # be polite to Wikivoyage
        print(f"Scraping {city}...")
        listings, error = scrape_city(city)
        if error:
            print(f"  ! {error}")
            errors.append(city)
            continue

        counts[city] = {s: sum(1 for item in listings if item["section"] == s) for s in SECTIONS}
        empty = [s for s in SECTIONS if counts[city][s] == 0]
        if empty:
            print(f"  note: no listings found in {', '.join(empty)}")
        save_json(city, listings)
        save_day_plan(city, listings)
        all_listings.extend(listings)

    if counts:
        save_csv(all_listings)
        print_summary(counts)
        if compare:
            print_comparison(counts)
        print(f"\nSaved {len(all_listings)} listings to {OUTPUT_DIR}/ (JSON + day plan per city, plus all_cities.csv)")
    if errors:
        print(f"Failed cities: {', '.join(errors)}")
    return 1 if errors and not counts else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Wikivoyage listings and build 1-day plans.")
    parser.add_argument("cities", nargs="+", help='city names, e.g. "Tempe" "Sedona"')
    parser.add_argument("--compare", action="store_true", help="print listing counts for all cities side by side")
    args = parser.parse_args()
    sys.exit(main(args.cities, compare=args.compare))
