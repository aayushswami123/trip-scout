# trip-scout

A small command-line tool that scrapes [Wikivoyage](https://en.wikivoyage.org) travel listings for one or more cities, using [Scrapling](https://github.com/D4Vinci/Scrapling). It is a student project and part of a capstone on an AI travel planner.

## What it does

For each city it collects the **See, Do, Eat and Sleep** listings and keeps: name, short description, price, hours, website and latitude/longitude (when Wikivoyage has them). It then writes:

- `output/<city>.json` - all listings for that city
- `output/all_cities.csv` - every city combined
- `output/<city>_day_plan.md` - a simple 1-day plan (2 See, 1 Eat, 1 Do)

It also prints a summary table, and `--compare` prints the cities side by side.

How it works: listings are selected with CSS selectors found by inspecting the real page (`bdi.vcard`), with Scrapling's `adaptive=True` so the selector can find the listings again if the page layout changes. It sends a clear User-Agent and waits 1-2 seconds between cities. Missing pages, empty sections and missing fields are handled without crashing.

## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "scrapling[fetchers]"
scrapling install
```

## Run

```bash
python trip_scout.py "Tempe" "Sedona" "Flagstaff"
python trip_scout.py "Tempe" "Sedona" "Flagstaff" --compare
```

## Example output

```
City                 Section    Count
-------------------------------------
Tempe                See           18
Tempe                Do             6
Tempe                Eat            9
Tempe                Sleep          9
Sedona               See            5
Sedona               Do            15
Sedona               Eat           11
Sedona               Sleep         15
Flagstaff            See           10
Flagstaff            Do            18
Flagstaff            Eat           18
Flagstaff            Sleep         20
-------------------------------------

Section            Tempe        Sedona     Flagstaff
----------------------------------------------------
See                   18             5            10
Do                     6            15            18
Eat                    9            11            18
Sleep                  9            15            20
Total                 42            46            66
```

A day plan (`output/sedona_day_plan.md`) starts like this:

```markdown
# 1-day plan for Sedona

## Morning - See
- **Palatki Heritage Site** - A Sinagua archeological site with cliff dwellings ...
```

## Scrapling command line

Scrapling also has a CLI that saves a page without writing any code. Saving as Markdown needs one extra package:

```bash
pip install markdownify
scrapling extract get https://en.wikivoyage.org/wiki/Sedona sedona.md
```

## Data and credits

Listings come from Wikivoyage and are available under the [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license. Please be polite: this tool is meant for a handful of pages, not bulk scraping.
