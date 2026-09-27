# Bhagiratha: YouTube Demo Script (≈ 5 minutes)

**Presenter:** Rahul Seera (IIT Bhilai) · **Target length:** 4:45–5:00
**Where to record:** the live server `http://10.1.75.53:3247/` (or your laptop at `http://127.0.0.1:8000/`); both give identical numbers.

---

## Before you press record

1. Open the app and click **✨ Load Sample Demo** once (a rehearsal; it takes about 1 s).
2. Click **🧹 Clear Map** (map toolbar) so you start from a clean map.
3. Have ready: `tests/sample_data/contours_1m.kml`, a terminal in the project folder, and `report/final_report.pdf`.
4. Browser zoom 100 %, full screen, notifications off.

### Numbers you will see (all verified)

| Demo step | Result |
|---|---|
| Contour map: pond site | 21.24171° N, 81.28692° E |
| Contour map: catchment / slope | 3.9116 km² (≈ 391 ha) / 3.99 % |
| Rainfall (Open-Meteo, 2016–2025) | 1,415.2 mm per year, 1,251.4 mm in the monsoon |
| Expected water volume | **1,713,242 m³** |
| Pond | 4.5 m deep · 266,504 m² (≈ 26.7 ha) · capacity 1,199,269 m³ · score 98 |
| Land area box 21.235–21.255 N, 81.278–81.298 E | site 21.23611, 81.27806 · catchment 7.089 km² · **3,104,911 m³** |

---

## Timeline

| Time | Segment | On screen |
|---|---|---|
| 0:00–0:35 | 1. Problem | App home screen, satellite map |
| 0:35–1:15 | 2. How it works | **ℹ️ Info** modal |
| 1:15–2:15 | 3. Land area selection (the core requirement) | **📐 Land Area Selection** |
| 2:15–3:05 | 4. Contour map analysis | **🗺️ Contour Map (KML)** |
| 3:05–3:35 | 5. Being honest about the result | zoom on the marker, satellite view |
| 3:35–4:25 | 6. Speed, load & limits of the server | terminal + report table |
| 4:25–5:00 | 7. Wrap-up | app + report |

---

## Narration

### 1 · Problem (0:00–0:35)
> "Hi, I'm Rahul Seera from IIT Bhilai, and this is **Bhagiratha**, an AI-based village pond planning system.
> Village ponds are often dug wherever land happens to be free, not where rainwater actually collects. So many stay dry, or they're too small and breach in the monsoon.
> Bhagiratha answers three questions from terrain and ten years of rainfall: **where** should the pond go, **how much water** will reach it, and **how big** should it be."

### 2 · How it works (0:35–1:15)
*(Click **ℹ️ Info**.)*
> "Under the hood: the browser is a Leaflet map. The backend is Python FastAPI.
> First it gets an elevation grid, either real 30-metre satellite elevation data from OpenTopography, or by interpolating an uploaded contour map.
> It fills artificial pits in the terrain, then works out, for every cell, which neighbour water flows to. That's the D8 algorithm, with distances corrected for latitude.
> Counting how much water flows through each cell tells us where runoff converges. That's the pond site.
> Then it traces the catchment uphill, takes ten years of monsoon rainfall from Open-Meteo, and computes runoff as Q = C × I × A, and sizes the pond to hold seventy percent of it."
*(Close the modal.)*

### 3 · Land area selection (1:15–2:15)
*(Click **📐 Land Area Selection** → type South 21.235, North 21.255, West 81.278, East 81.298, or use **Draw Area Box** and drag → **🔍 Discover Pond Site & Analyze Basin**.)*
> "This is the main requirement: selecting land on the map. Say the panchayat has this parcel available. I select it and click Discover.
> The system downloads real elevation data around the parcel, so it also sees the land **upstream**, and finds the best drainage point **inside** my parcel." *(Results appear, ≈15–30 s.)*
> "On the map: the dashed orange box is my parcel, the green marker is the suggested pond location, and the blue area is the catchment, all the land whose rain flows here. Notice it extends beyond my parcel, because water flows in from upstream.
> The popup shows the catchment area, **7.09 square kilometres**, and the expected water volume, **about 3.1 million cubic metres**. The same numbers are in the panel on the right."
*(Hover over the blue polygon to show its tooltip.)*

### 4 · Contour map analysis (2:15–3:05)
*(Click **🗺️ Contour Map (KML)** → drag in `contours_1m.kml` → **⚡ Run Contour Flow Analysis**. Or click **✨ Load Sample Demo**.)*
> "The second input is a surveyed contour map, here a real one-metre survey near Durg with 1,355 contour lines.
> In under a second, it's parsed, turned into an elevation grid, and analysed.
> The catchment is **3.91 square kilometres**. Rainfall is **1,251 millimetres** in the monsoon. So the expected water volume is **1.71 million cubic metres**.
> The recommended pond is **4.5 metres deep**, the safe limit for earthen banks, and it holds seventy percent of that water. Suitability score: 98."
*(Scroll the panel: sizing and the rainfall chart.)*

### 5 · Being honest about the result (3:05–3:35)
*(Zoom in on the marker in satellite view.)*
> "One thing I want to point out: this marker sits in the Shivnath river. That's correct hydrology, because the river is where the most water converges. But the algorithm only sees elevation. It doesn't know a river is already there, or who owns the land. So this is a **screening tool**: it narrows the search, and a site visit and the authorities make the final decision. That's exactly why the land-area mode matters: you restrict the search to land you actually have."

### 6 · Speed, load & limits (3:35–4:25)
*(Terminal: `.venv/bin/pytest tests/ -q` → 28 passed. Then show the performance table in the report, Table 4.)*
> "The app runs on a campus server we were given: one CPU and 512 megabytes of memory.
> We stress-tested it on that server: 446 requests, up to 20 at a time, zero errors.
> Measuring on the real machine found three real problems. First, the math libraries started 120 threads on a single CPU, which made analysis take 45 seconds; we fixed it by pinning the threads, and now it's under one second. Second, two heavy analyses at once ran out of memory and crashed the server; now heavy jobs queue one at a time, and memory peaks at 330 megabytes. Third, the rainfall service is blocked from that server, so we bundle the real rainfall data for the region and the app always says which data it used.
> A watchdog also checks the server every minute and restarts it if needed, and 28 automated tests guard the maths."

### 7 · Wrap-up (4:25–5:00)
> "So: select land on the map, and in seconds you get a suggested pond location, its catchment area and the expected water volume, all on the map, from a system that stays fast and honest on a small server.
> Everything is in the report and on GitHub. Thank you!"
