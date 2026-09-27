"""
Stress / scaling test for a running Bhagiratha server.

Run ON the server machine so network jitter doesn't pollute the numbers:
    ./venv/bin/python3 scripts/stress_test.py http://127.0.0.1:3000

Scenarios (kept small on purpose: the container is shared and has 1 CPU, and
OpenTopography / Open-Meteo are third-party services we must not hammer):
  1. /api/health baseline            — 200 requests, 20 concurrent
  2. cached point analysis           — 200 requests, 20 concurrent (after 1 warm-up)
  3. contour analysis (6.7 MB KML)   — 4 requests each at concurrency 1, 2, 4
  4. responsiveness under load       — /api/health latency while 4 contour runs are in flight
Server resident memory (VmRSS) is sampled throughout.
"""

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KML = os.path.join(ROOT, "tests", "sample_data", "contours_1m.kml")
POINT = {"lat": 21.2180, "lon": 81.3390}  # Bhilai Rural preset village


def server_pid():
    out = subprocess.run(["pgrep", "-f", "uvicorn app.main:app"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def rss_mb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None


def pct(values, p):
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


def summarize(name, lat, errors, wall, conc):
    return {
        "scenario": name, "concurrency": conc, "requests": len(lat) + errors, "errors": errors,
        "p50_s": round(statistics.median(lat), 3) if lat else None,
        "p95_s": round(pct(lat, 95), 3) if lat else None,
        "max_s": round(max(lat), 3) if lat else None,
        "throughput_rps": round(len(lat) / wall, 2) if wall else None,
    }


async def run(client, make_request, total, conc):
    sem = asyncio.Semaphore(conc)
    lat, errors = [], 0

    async def one():
        nonlocal errors
        async with sem:
            t = time.perf_counter()
            try:
                r = await make_request()
                if r.status_code == 200:
                    lat.append(time.perf_counter() - t)
                else:
                    errors += 1
            except Exception:
                errors += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(total)))
    return lat, errors, time.perf_counter() - t0


async def main():
    pid = server_pid()
    peak = {"rss": rss_mb(pid) or 0}
    idle_rss = peak["rss"]
    stop = asyncio.Event()

    async def sampler():
        while not stop.is_set():
            v = rss_mb(pid)
            if v:
                peak["rss"] = max(peak["rss"], v)
            await asyncio.sleep(0.2)

    kml_bytes = open(KML, "rb").read()
    results = []
    samp = asyncio.create_task(sampler())
    async with httpx.AsyncClient(base_url=BASE, timeout=300) as c:
        # 1. health baseline
        lat, err, wall = await run(c, lambda: c.get("/api/health"), 200, 20)
        results.append(summarize("health", lat, err, wall, 20))

        # 2. cached point analysis (first call may download the DEM)
        t = time.perf_counter(); r = await c.post("/api/analyze", json=POINT)
        cold = time.perf_counter() - t
        lat, err, wall = await run(c, lambda: c.post("/api/analyze", json=POINT), 200, 20)
        s = summarize("point (cached)", lat, err, wall, 20); s["cold_first_call_s"] = round(cold, 2); s["cold_status"] = r.status_code
        results.append(s)

        # 3. contour analysis at increasing concurrency
        def contour():
            return c.post("/analyzeContour", files={"contour_map": ("contours_1m.kml", kml_bytes, "application/xml")})
        for conc in (1, 2, 4):
            lat, err, wall = await run(c, contour, 4, conc)
            results.append(summarize("contour", lat, err, wall, conc))

        # 4. health latency while 4 contour analyses run
        health_lat = []
        async def probe():
            while not stop_probe.is_set():
                t = time.perf_counter(); await c.get("/api/health"); health_lat.append(time.perf_counter() - t)
                await asyncio.sleep(0.25)
        stop_probe = asyncio.Event()
        ptask = asyncio.create_task(probe())
        lat, err, wall = await run(c, contour, 4, 4)
        stop_probe.set(); await ptask
        s = summarize("health during 4x contour", health_lat, 0, wall, 1)
        s["throughput_rps"] = None
        results.append(s)

    stop.set(); await samp
    print(json.dumps({"server_pid": pid, "idle_rss_mb": round(idle_rss, 1), "peak_rss_mb": round(peak["rss"], 1),
                      "results": results}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
