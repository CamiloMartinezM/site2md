import sys  # 127.0.0.1-only

from scrapling.spiders import LinkExtractor, Spider

seen = {sys.argv[1]}


class Countries(Spider):
    name = "countries"
    start_urls = tuple(seen)

    async def parse(self, response):
        for c in response.css(".country"):
            yield {
                "name": c.css(".country-name")[0].get_all_text(strip=True),
                "capital": c.css(".country-capital::text").re_first(r"^(?!None$).+"),
                "population": int(c.css(".country-population::text").get()),
                "area_km2": float(c.css(".country-area::text").get()),
            }
        depth = response.meta.get("depth", 0)
        for url in LinkExtractor(allow_domains="127.0.0.1").extract(response):
            if depth < 2 and url not in seen and len(seen) < 20:
                seen.add(url)
                yield response.follow(url, meta={"depth": depth + 1})


Countries().start().items.to_json("output.json")
