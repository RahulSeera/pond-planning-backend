# Bhagiratha: YouTube Demo Script (~7 min)

Explaining the maths properly takes about **7 minutes**. If your course caps videos at 5, cut Parts 4 and 7 to one sentence each.

**Before recording:** open `http://10.1.75.53:3247/` and click ✨ **Load Sample Demo** once, then 🧹 **Clear Map**. Have ready `tests/sample_data/contours_1m.kml`, a terminal, and `report/final_report.pdf`.
**Tip:** show the formulas and calculations on screen while you speak. The report pages or a simple slide both work.

---

### Part 1: The problem (0:00–0:30)
*[App home screen, satellite map]*
> "Hi, I'm Rahul Seera from IIT Bhilai. This is **Bhagiratha**, an AI-based village pond planning system.
> Village ponds are often dug wherever land is free, not where rainwater actually collects, so many stay dry or overflow in the monsoon.
> Bhagiratha answers three questions: **where** should the pond go, **how much water** will reach it, and **how big** should it be."

---

### Part 2: Architecture (0:30–1:00)
*[Click ℹ️ Info, or show the architecture diagram, report Fig. 1]*
> "The front end is a Leaflet map in the browser. The backend is Python FastAPI.
> It has three engines: a **terrain engine** that finds the pond site and its catchment, a **rainfall engine** with ten years of data from Open-Meteo, and a **recommendation engine** that calculates water volume and pond size.
> Elevation comes from OpenTopography's SRTM satellite data at 30-metre resolution, or from an uploaded contour map."

---

### Part 3: Land area selection, live (1:00–2:00)
*[📐 Land Area Selection → South 21.235, North 21.255, West 81.278, East 81.298 (or drag a box with Draw Area Box) → 🔍 Discover Pond Site & Analyze Basin]*
> "The main feature: an administrator selects the land that's available, say a panchayat plot, and clicks Discover.
> The system downloads real elevation data for this area **plus a margin around it**, because water flows in from upstream. It then finds the best drainage point **inside** my box."

*[Result appears after ~15–30 s. Point at each item.]*
> "The orange dashed box is my land. The green marker is the suggested pond location: **21.23611 north, 81.27806 east**. The blue region is the **catchment**, all the land whose rain flows to this point: **7.089 square kilometres**. It extends far beyond my box, because water comes from upstream.
> The expected water volume is **3,104,911 cubic metres**. Everything is on the map: click the marker or hover over the catchment."

---

### Part 4: How the terrain algorithm works (2:00–3:15)
*[Slide or report §4: step list]*
> "Here's what happened behind that click, in five steps.
> **Step 1, elevation grid.** The map is a grid of cells, each with a height. For contour maps, we take every point on every contour line: the sample file has 1,355 lines and 159,113 points. We keep every 7th point, 22,731 of them, to bound memory. Then we interpolate a smooth surface using Delaunay triangulation, giving a 152 by 200 grid.
> **Step 2, fill pits.** Real data has small fake holes where water would get stuck. The **Priority-Flood** algorithm raises each hole to the level where water would spill out, so water can always flow downhill.
> **Step 3, flow direction, the D8 algorithm.** Each cell sends its water to the **steepest downhill** of its 8 neighbours. Steepness is the height drop divided by the distance.
> One detail: our map is in degrees, and at 21° north one degree of longitude is only cos 21°, about **0.93**, of a degree of latitude. So we convert to real metres: each cell is **16.3 m wide and 17.5 m tall**. Without this, east-west slopes would be off by about 7 percent.
> **Step 4, flow accumulation.** Count how many cells drain through each cell. Streams light up with big numbers.
> **Step 5, pond site and catchment.** The pond goes where the count is highest, inside my box. We skip the outer 8 percent of the map, where edge effects distort flow. Then we trace uphill to find every cell that drains there. That's the catchment."

---

### Part 5: Contour map and the full calculation (3:15–5:15)
*[🗺️ Contour Map (KML) → drag in contours_1m.kml → ⚡ Run Contour Flow Analysis (or ✨ Load Sample Demo)]*
> "Now a real 1-metre contour survey near Durg. It's analysed in under a second. Let's check every number by hand."

*[Show each calculation on screen as you say it]*

**Catchment area:**
> "The catchment contains **13,719 cells**. Each cell is 16.28 m by 17.52 m, which is **285.1 square metres**.
> 13,719 × 285.1 ≈ **3,911,600 m², or 3.9116 square kilometres**, about 391 hectares."

**Rainfall:**
> "From Open-Meteo we take ten years of daily rainfall, 2016 to 2025, for this exact spot. We add up June to September each year and average over the ten years: **1,251.4 mm of monsoon rain**, out of 1,415.2 mm for the whole year."

**Runoff volume, the Rational Method, Q = C × I × A:**
> "C is the runoff coefficient, the fraction of rain that runs off instead of soaking in. For farmland on loamy soil we use **0.35**.
> I is the rainfall depth: 1,251.4 mm is **1.2514 metres**.
> A is the area: **3,911,600 m²**.
> Q = 0.35 × 1.2514 × 3,911,600 = **1,713,242 cubic metres**, about **1.71 billion litres** of water every monsoon."

**Pond size:**
> "We design the pond to hold **70 percent** of it, so heavy rain can spill safely:
> V = 0.70 × 1,713,242 = **1,199,269 m³**.
> Depth scales between **2.5 m** (shallower ponds lose too much to evaporation) and **4.5 m** (the safe limit for earthen banks). Anything above 200,000 m³ gets the full **4.5 m**.
> Surface area = volume ÷ depth = 1,199,269 ÷ 4.5 = **266,504 m², about 26.7 hectares**."

**Suitability score (0–100):**
> "Score = 40 percent catchment + 35 percent slope + 25 percent rainfall.
> The catchment is 3.9 km², inside the ideal 0.5 to 5 range: 100. The slope is 3.99 percent, at most 4 percent: 100. Rainfall is 1,415 mm, over 1,000: 100.
> The total is 100, capped at **98** because no site is perfect."

*(Optional, for the land-area result:)*
> "For the land-area site the catchment is 7.09 km², above 5, so it loses 3 points per extra km²: 100 − 3 × 2.09 = 93.7. The score is 0.4 × 93.7 + 35 + 25 = **97.5**. Runoff: 0.35 × 1.2514 × 7,089,000 = **3,104,911 m³**."

---

### Part 6: Being honest about the result (5:15–5:45)
*[Zoom in on the marker in satellite view]*
> "Notice this marker is **in the Shivnath river**. That's correct hydrology: the river is where the most water flows together. But the algorithm only sees elevation. It doesn't know a river is already there, or who owns the land, the soil, or the permissions.
> So Bhagiratha is a **screening tool**: it narrows the search, and a field visit and the authorities make the final decision. That's why the land-area mode matters: you search only the land you actually have."

---

### Part 7: Performance and limits of the server (5:45–6:40)
*[Terminal: `.venv/bin/pytest tests/ -q` → 28 passed; then report Table 4]*
> "It runs on the campus server we chose, **sys3**: just **one CPU and 512 MB of memory**. Testing on it found three real problems:
> **One:** the maths libraries started 120 threads for one CPU, so an analysis took 45 seconds. We limited them to one thread, and now it's **under one second**.
> **Two:** two analyses at once used over 512 MB and the server was killed. Now heavy analyses **queue one at a time**. The stress test: **446 requests, up to 20 at once, zero errors**, memory peaking at **330 MB**.
> **Three:** the rainfall service is blocked from that server, so we bundle the real rainfall data for this region, and the app always says which data it used.
> A **watchdog** checks the server every minute and restarts it if needed, and **28 automated tests** check the maths."

---

### Part 8: Wrap-up (6:40–7:00)
> "So: select your land on the map, and in seconds you get the pond location, the catchment area and the expected water volume, on the map, with every number traceable to a formula. Code and report are on GitHub: github.com/RahulSeera/pond-planning-backend. Thank you!"

---

### Quick reference card (keep it next to you while recording)

| Quantity | Calculation | Value |
|---|---|---|
| Cell size | 0.000157° × 111,320 × cos 21.24° ; 0.000157° × 111,320 | 16.28 m × 17.52 m = 285.1 m² |
| Catchment area A | 13,719 cells × 285.1 m² | 3.9116 km² |
| Monsoon rain I | mean of Jun–Sep totals, 2016–2025 | 1,251.4 mm = 1.2514 m |
| Runoff Q | 0.35 × 1.2514 × 3,911,600 | 1,713,242 m³ |
| Capacity V | 0.70 × Q | 1,199,269 m³ |
| Depth d | V ≥ 200,000 m³ → max | 4.5 m |
| Surface area | V ÷ d | 266,504 m² (26.7 ha) |
| Score | 0.4 × 100 + 0.35 × 100 + 0.25 × 100 → cap | 98 |
| Land-area runoff | 0.35 × 1.2514 × 7,089,000 | 3,104,911 m³ |
| Land-area score | 0.4 × 93.7 + 35 + 25 | 97.5 |
