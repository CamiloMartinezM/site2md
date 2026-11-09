import json
import sys  # 127.0.0.1-only

from scrapling.fetchers import Fetcher

records = [
    {
        "name": c.css(".country-name")[0].get_all_text(strip=True),
        "capital": c.css(".country-capital::text").re_first(r"^(?!None$).+"),
        "population": int(c.css(".country-population::text").get()),
        "area_km2": float(c.css(".country-area::text").get()),
    }
    for c in Fetcher.get(sys.argv[1]).css(".country")
]
print(json.dumps(records))
