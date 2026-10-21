from scrapling.fetchers import Fetcher

# Download the Wikivoyage page for Tempe
page = Fetcher.get("https://en.wikivoyage.org/wiki/Tempe")

# Find the <title> tag and read its text
title = page.css("title::text").get()

print(title)
