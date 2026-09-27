# Bhagiratha: Live Demo Guide (for evaluators)

A step-by-step plan for demonstrating the project live, **about 10 minutes**. (For the recorded 5-minute YouTube video, use `YOUTUBE_DEMO_SCRIPT.md`.)

---

## 0. Before the evaluator arrives (5 minutes)

| # | Check | How | Expected |
|---|---|---|---|
| 1 | Server is up | Open <http://10.1.75.53:3247/api/health> | `"status":"healthy"`, `"database":"standby (resilient persistent-file mode)"` |
| 2 | Quick rehearsal | Open <http://10.1.75.53:3247/> → click **✨ Load Sample Demo** once | Result in ≈1 s; runoff **1,713,242 m³** |
| 3 | Laptop terminal ready | `cd ~/Documents/semister7/pond-project` | — |
| 4 | Tests pass | `.venv/bin/pytest tests/ -q` | `28 passed` |
| 5 | Report open | `report/final_report.pdf` (or Overleaf) | 9 pages (course template); performance is Table 4, CSD themes Table 3 |
| 6 | Sample file handy | `tests/sample_data/contours_1m.kml` | 6.7 MB |

**If the server is down:** the watchdog restarts it within 60 s. If it's still down after 2 minutes:
```bash
ssh -p 2247 student@10.1.75.53          # password: enter student password
bash ~/pond-project/scripts/start_server.sh
curl http://127.0.0.1:3000/api/health
```
**If the campus network is flaky** (it drops some connections), run locally instead:
```bash
.venv/bin/uvicorn app.main:app --port 8000     # then open http://127.0.0.1:8000/
```
The results are the same as on the server (see the table in §2).

**Don't use up the rainfall quota on demo day.** Open-Meteo's free tier allows a limited number of 10-year queries per day (running the test suite many times, or `scripts/build_rainfall_cache.py`, uses it up). If it's exhausted, the app automatically uses the bundled data, so the numbers stay the same.

---

## 1. Problem & idea (1 min): no clicking yet

> "Village ponds are often dug where land happens to be free, not where water collects, so they stay dry or breach. Bhagiratha takes elevation data plus ten years of rainfall and answers: where should the pond go, how much water will reach it, and how big should it be?"

Show the map: satellite imagery (Esri World Imagery) and the three mode tabs: **📍 Point Analysis**, **📐 Land Area Selection**, **🗺️ Contour Map (KML)**.

---

## 2. Contour map analysis (3 min): the core demo

1. Click the **🗺️ Contour Map (KML)** tab.
2. Drag `tests/sample_data/contours_1m.kml` into the upload box → **⚡ Run Contour Flow Analysis**.
   (Shortcut: **✨ Load Sample Demo** in the header runs the same file.)
3. Point out on the map:
   - **Cyan polygon**: the catchment, i.e. all the land whose rain drains to the pond.
   - **Green marker**: the auto-selected pond site.
4. Read the results panel:

| What you'll see | Value (same on the server and the laptop) |
|---|---|
| Contours parsed | 1,355 (267–298 m) |
| Pond site | 21.24171, 81.28692 |
| Catchment | 3.9116 km² (≈391 ha) |
| Slope | 3.99 % |
| Rainfall (annual / monsoon) | 1,415.2 / 1,251.4 mm (real Open-Meteo archive, 2016–2025) |
| Runoff | 1,713,242 m³ |
| Depth / area / capacity | 4.5 m / 266,504 m² / 1,199,269 m³ |
| Suitability | 98 |

5. **On the server, point at the yellow note** ("Live Open-Meteo query unavailable on this network — using bundled Open-Meteo archive data … 0.0 km away"):
   > "The campus firewall blocks the rainfall service from this container. So we pre-fetched the real 10-year Open-Meteo data for this region and ship it with the app. The numbers are the same real data, and the app says where they came from. Outside the bundled region it falls back to a conservative regional average, again with a warning. It never degrades silently."

6. **Raise the river point yourself, before they ask.** Switch to satellite view and zoom in on the marker: it sits in the **Shivnath river**.
   > "Notice the marker is in the river. That's hydrologically correct: the river is where the most water converges on this map. But the algorithm only knows elevation. It doesn't know a river is already there, or who owns the land. So this is a screening result: it tells you where water collects, and a field visit plus the revenue and irrigation departments make the final call. On this spot the right structure would be a check dam, not a dug pond. Excluding existing water bodies using OpenStreetMap, which already maps this river and four canals here, is the first item in our future work."

   Then switch to **📐 Land Area Selection**: "When the administrator knows which land is available, they draw it, and the pond is placed inside that land." That is how ownership is handled today.

**How it works (say it while results load):**
> "Contour points are interpolated into an elevation grid. Priority-Flood fills fake pits, and D8 sends each cell's water to its steepest downhill neighbour, measured in real metres with the latitude correction. Counting how many cells drain through each point gives flow accumulation, and the maximum, away from the map edges, is where the pond goes."

---

## 3. Land area selection (2 min)

1. Click the **📐 Land Area Selection** tab.
2. Use the **Draw Area Box** tool (map toolbar) → drag a rectangle over farmland near the sample site (≈ 21.235–21.255 N, 81.278–81.298 E).
3. Click **🔍 Discover Pond Site & Analyze Basin** (≈15–30 s on the server: it downloads real SRTM elevation data). For the sample box: site 21.23611, 81.27806, catchment 7.089 km², runoff 3,104,911 m³, score 97.5.
4. Say:
   > "The pond is always placed **inside** the land I selected, but the catchment can extend beyond it, because water flows in from upstream."

If OpenTopography is slow or blocked, a warning says **synthetic demonstration terrain** was used. Mention this as another example of honest degradation.

---

## 4. Point analysis (1 min, optional)

**📍 Point Analysis** → click on a stream or valley on the map → **🚀 Delineate Basin & Size Pond** (≈13–25 s on the server, mostly the elevation download).
> "A click is snapped to the strongest drainage line within about 60 m, which is standard GIS practice, because clicking one pixel off a stream would give a tiny hillslope catchment."

Click the same point again: it returns instantly (**rounded-grid cache**, ≈3–8 ms).

---

## 5. Export & extras (1 min)

- **📥 Export GeoJSON Basin**: the catchment polygon for QGIS/ArcGIS.
- **📄 Print / Save Summary**: a printable report.
- **📜 History**: past analyses (stored in `data/analyses_history.json` because there's no PostgreSQL on the container).
- **ℹ️ Info**: the architecture and formula guide.
- <http://10.1.75.53:3247/docs>: interactive API documentation for all 9 endpoints.

---

## 6. System design / CSD points (2 min): terminal

```bash
.venv/bin/pytest tests/ -q                       # 28 passed
curl http://10.1.75.53:3247/api/health           # status, DB mode, uptime, memory
```
Talking points (report Table 3 and §6):
1. **Concurrency**: terrain download and rainfall query run in parallel; heavy computation runs in worker threads, so `/api/health` answers in ~2 ms even mid-analysis.
2. **Caching**: coordinates rounded to ~110 m cells; a repeat query drops from 13 s to 8 ms.
3. **Resilience**: no database → file mode; rainfall service blocked → bundled real archive data, then a regional baseline. A background probe checks Open-Meteo every 5 minutes, and a circuit breaker means no request ever waits on a blocked service. The watchdog checks health every 60 s and restarts the server (with a startup grace period); a startup warm-up makes even the first request fast.
4. **Resource limits (strong real-world story)**: "The container is limited to one CPU but reports 120 cores, so the math libraries started 120 threads fighting over one CPU. Analysis took 45 seconds. Pinning the thread pools to the real quota brought it to under 1 second." Second: "It has only 512 MB of memory. Our stress test found that two analyses at once ran out of memory and the kernel killed the server. Now heavy analyses queue one at a time, so 446 requests, up to 20 at once, ran with zero errors and memory peaked at 330 MB." Also: a 99 %-full disk (temp-file pruning, log rotation) and bounded point decimation.

---

## 7. Likely questions & answers

| Question | Answer |
|---|---|
| Why C = 0.35? | A typical runoff coefficient for cultivated land on loamy soil (tables give ~0.2–0.5). It's constant for now; a land-use/soil lookup is future work. |
| Is this the real Rational Method? | Its volumetric form: seasonal rainfall depth × area × C gives a seasonal volume (m³), not the peak discharge (m³/s) of the classical formula. |
| Why 70 %? | The pond holds 70 % of the monsoon runoff; the remaining 30 % leaves through a spillway, so the embankment isn't overtopped. |
| Why 2.5–4.5 m deep? | Shallower ponds lose proportionally more water to evaporation; deeper than ~4.5 m, unlined earthen banks become unstable. |
| A 26-hectare pond is huge. | Yes, for a 3.9 km² catchment that's the harvesting potential. In practice it would be split across several ponds or check dams (noted in the report's limitations). |
| Why exclude the 8 % border? | Accumulation is distorted at DEM edges, where water "flows off the map". |
| How do you know the catchment is right? | The polygon is valid and non-self-intersecting, its area matches the cell count (3.9114 vs 3.9116 km²), it doesn't touch the map edge, and regression tests check the maths. |
| What changed in the final audit? | Latitude-corrected D8, pixel-centre georeferencing, real SRTM support (int16 crash), pond kept inside the drawn parcel, pour-point snapping, continuous scoring, no silent fallbacks, plus the container fixes. See report §6 and §9. |
| Does it pick the best point, or score the point I choose? | Both. **Point mode** scores the point you click (snapped ≤ 60 m to the drainage line). **Area mode** picks the best point inside the box you draw. **Contour mode** picks the best point on the whole map. "Best" = where the most runoff converges. |
| Why is the pond in the river? | The river is the strongest convergence line, and the algorithm only sees elevation. It doesn't check existing water bodies, ownership, land use, soil, groundwater, or approvals (report §1.2 and §8). It's a screening tool; the final siting needs a field visit. Water-body exclusion via OpenStreetMap is the planned next step. |
| So how would a real user use it? | Draw the available government/panchayat land in Area mode → get the best drainage point inside it → verify on the ground. Or click candidate spots in Point mode and compare their scores. |
| What happens with many users? | Light requests (health, cached results, search) run concurrently: 20 at once with 0 errors. Heavy analyses queue one at a time, because the server has 1 CPU and 512 MB; running two at once gives no speed-up and ran out of memory. A request waiting over 120 s gets a clean "busy, retry" (HTTP 503). Numbers: report Table 4, `report/stress_results_sys3.json`. |
| Why no load balancer? | With one CPU and 512 MB, a second instance would compete for the same CPU and memory. The queue is the effective load control on this machine. On a bigger machine you'd run more workers or instances behind Nginx and raise `BHAGIRATHA_HEAVY_SLOTS`. |
| What if PostgreSQL is down? | A 3 s check at startup switches to file mode. It never crashes or returns a 500 because of the database. |
| Is the bundled rainfall "fake"? | No. It's the same Open-Meteo 10-year archive, fetched with `scripts/build_rainfall_cache.py` and stored in `data/rainfall_cache.json` (19 points around Durg–Bhilai). The server uses the nearest point within 11 km and says so in the note. |
| What about places outside the bundle? | Live Open-Meteo if reachable; otherwise a conservative regional average (1,150 mm/yr), with a warning. |
