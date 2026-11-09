import asyncio
import json
import sys  # 127.0.0.1-only

from crawl4ai import (
    AsyncWebCrawler,
    BFSDeepCrawlStrategy,
    CrawlerRunConfig,
    FilterChain,
    JsonCssExtractionStrategy,
    URLPatternFilter,
)
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

schema = {
    "baseSelector": ".country",
    "fields": [
        {"name": "name", "selector": ".country-name", "type": "text"},
        {"name": "capital", "selector": ".country-capital", "type": "text"},
        {"name": "population", "selector": ".country-population", "type": "text"},
        {"name": "area_km2", "selector": ".country-area", "type": "text"},
    ],
}
config = CrawlerRunConfig(
    extraction_strategy=JsonCssExtractionStrategy(schema),
    deep_crawl_strategy=BFSDeepCrawlStrategy(
        max_depth=2,
        max_pages=20,
        filter_chain=FilterChain([URLPatternFilter(sys.argv[1], reverse=True)]),
    ),
)


async def main():
    async with AsyncWebCrawler(crawler_strategy=AsyncHTTPCrawlerStrategy()) as crawler:
        pages = await crawler.arun(sys.argv[1], config=config)
    records = [r for page in pages for r in json.loads(page.extracted_content)]
    for r in records:
        r["capital"] = None if r["capital"] == "None" else r["capital"]
        r["population"] = int(r["population"])
        r["area_km2"] = float(r["area_km2"])
    print(json.dumps(records))


asyncio.run(main())
