# site2md 0.4.4

Version 0.4.4 keeps the child requests of site and follow modes at least the full delay apart as the server receives them. The README also gains a benchmark.

- **Child request pacing.** Site and follow modes promise at least one second between child requests, or the longer `crawl-delay` or `request-rate` interval from `robots.txt`. A server could still log two child requests closer together than that delay: the benchmark measured gaps down to 0.965 s.
  - On Windows before Python 3.13, `time.monotonic()` ticks every 15.6 ms, so the wait could end up to one tick early.
  - The delay ran from the start of one request to the start of the next, so a request that took longer to reach the server shortened the gap the server saw.
  - Each delay is now timed with `time.perf_counter()` and starts when the previous child response arrives, redirect responses included. A crawl gets slower by about one response time per page ([#50](https://github.com/CamiloMartinezM/site2md/issues/50)).
- **Benchmark.** The README now shows how site2md compares with Scrapling, crawl4ai, MarkItDown and pandoc on the same task, and [BENCHMARKS.md](../BENCHMARKS.md) holds the method, the raw results and how to rerun them. The harness lives in `benchmarks/` and doesn't ship with the package ([#40](https://github.com/CamiloMartinezM/site2md/issues/40)).

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
