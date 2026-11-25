"""Measure real /upload latency and queue/throughput so README numbers come from data.

Usage (API running on localhost:8000, Redis + a Celery worker running):
    python scripts/benchmark_upload.py --file data/sample_audio/sample.wav --requests 50 --concurrency 10

Reports p50/p95/max latency of the POST /upload response (the time to accept and enqueue the job),
plus the file size, so the number is never quoted without its context.
"""
import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx


async def one(client: httpx.AsyncClient, url: str, path: Path) -> float:
    t0 = time.perf_counter()
    with path.open("rb") as f:
        r = await client.post(url, files={"file": (path.name, f, "audio/wav")})
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000


async def main(args):
    path = Path(args.file)
    url = f"{args.host}/upload"
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=60) as client:
        async def guarded():
            async with sem:
                return await one(client, url, path)
        t0 = time.perf_counter()
        lat = await asyncio.gather(*[guarded() for _ in range(args.requests)])
        wall = time.perf_counter() - t0
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))]
    print(f"file: {path.name} ({path.stat().st_size / 1024:.0f} KB)  requests: {args.requests}  concurrency: {args.concurrency}")
    print(f"upload latency ms  p50={p(0.5):.1f}  p95={p(0.95):.1f}  max={lat[-1]:.1f}  mean={statistics.mean(lat):.1f}")
    print(f"accepted {args.requests} uploads in {wall:.2f}s ({args.requests / wall:.1f} req/s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--requests", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=10)
    asyncio.run(main(ap.parse_args()))
