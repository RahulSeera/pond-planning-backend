# YouTube 5-Minute Demo Video Script & Walkthrough
**System**: Bhagiratha: AI-based Village Pond Planning & Catchment Delineation System
**Presenter**: Rahul Seera (IIT Bhilai)
**Target Duration**: 4 minutes 45 seconds (Max: 5:00)

---

## Before You Record — Which Server?

The numbers you will see depend on whether live rainfall data is reachable:

| Where you record | Rainfall source | What the contour demo shows |
|---|---|---|
| **Local machine** (`http://127.0.0.1:8000/`) | Live Open-Meteo 10-year archive (or the bundled copy if the daily quota is used up) | 1,415 mm/yr, **1,251 mm monsoon**, runoff **1,713,242 m³** |
| **Campus container** (`http://10.1.75.53:3247/`) | Bundled copy of the same Open-Meteo archive (Open-Meteo is blocked from the container) | **Same numbers**, plus a yellow note saying bundled archive data was used |

Both give identical results, so you can record on either. On the container, mention the yellow note in segment 6: it shows the system is honest about where its data comes from.

### Reference numbers (`contours_1m.kml`, verified 27 Sep 2026)

| Quantity | Value |
|---|---|
| Contour lines / relief | 1,355 lines, 267–298 m |
| Suggested pond site | 21.24171° N, 81.28692° E |
| Catchment area | 3.9116 km² (≈ 391 ha) |
| Average slope | 3.99 % |
| Annual / monsoon rainfall | 1,415.2 mm / 1,251.4 mm (Open-Meteo 2016–2025) |
| Expected runoff (Q) | 1,713,242 m³ |
| Pond depth | 4.5 m |
| Surface area | 266,504 m² |
| Target capacity (70 %) | 1,199,269 m³ |
| Suitability | 98 / 100 (Highly Suitable) |

---

## Video Outline & Timeline

| Timestamp | Segment | Visual on Screen | Key Spoken Points |
|---|---|---|---|
| **0:00 - 0:45** | **1. Introduction & Motivation** | Full-screen web UI, zooming into the title and satellite basemap. | The problem: rural water security and ponds dug in arbitrary places. Bhagiratha as an automated decision-support system. |
| **0:45 - 1:30** | **2. Architecture & Algorithms** | Click **ℹ️ Info** (top right) to open the architecture & formula guide. | Contour → DEM → Priority-Flood → latitude-corrected D8 → accumulation → pond site → Rational Method. |
| **1:30 - 2:45** | **3. Live Demo — Contour Map** | **🗺️ Contour Map (KML)** tab → drag in `tests/sample_data/contours_1m.kml` → **⚡ Run Contour Flow Analysis**. (Or click **✨ Load Sample Demo** in the header, which runs the same file.) | 1,355 contours, 267–298 m relief, auto-selected site, 3.91 km² catchment, runoff and sizing. |
| **2:45 - 3:30** | **4. Live Demo — Land Area Selection** | **📐 Land Area Selection** tab → **Draw Area Box** tool on the map → drag a rectangle → **🔍 Discover Pond Site & Analyze Basin**. | The pond is always placed inside the drawn parcel; the catchment can extend upstream beyond it. Uses real SRTM 30 m terrain. |
| **3:30 - 4:15** | **5. Rainfall, Sizing & Export** | Scroll the results panel: sizing, rainfall chart; click **📥 Export GeoJSON Basin**. | Q = C·I·A with C = 0.35, 70 % capture, depth 2.5–4.5 m, GeoJSON export for QGIS. |
| **4:15 - 5:00** | **6. Resilience, Testing & Conclusion** | Terminal: `.venv/bin/pytest tests/` (27 passed), `curl http://10.1.75.53:3247/api/health`. | Watchdog, file-mode fallback, rainfall baseline, warnings instead of silent failures; summary. |

---

## Detailed Narration Script

### [0:00 - 0:45] 1. Introduction & Problem Statement
> *"Hello everyone! My name is Rahul Seera, and today I'm presenting **Bhagiratha**, a geospatial decision-support system for village pond planning.*
>
> *Under programmes like Mission Amrit Sarovar, thousands of village ponds are dug every year. Without hydrological analysis, many end up outside natural drainage paths, so they stay dry, or they're undersized and breach during the monsoon.*
>
> *Bhagiratha solves this end to end. From elevation data and ten years of rainfall history, it finds where water naturally collects, outlines the catchment that drains there, estimates how much water the monsoon will bring, and sizes the pond to hold seventy percent of it."*

---

### [0:45 - 1:30] 2. Architecture & Hydrological Algorithm
> *(Click **ℹ️ Info** in the top-right corner.)*
>
> *"Bhagiratha is an asynchronous modular monolith: FastAPI on the backend, PySheds, Rasterio and SciPy for terrain analysis, PostgreSQL with PostGIS for storage, and Leaflet.js in the browser.*
>
> *The pipeline has four stages:*
> *1. **Terrain input**: a clicked point, a drawn land parcel, or an uploaded KML or KMZ contour map. Contour points are interpolated into a continuous elevation grid using SciPy's Delaunay-based linear interpolation.*
> *2. **Conditioning**: the Priority-Flood algorithm fills artificial pits, and flat areas are given a slight gradient so water always has somewhere to flow.*
> *3. **D8 flow routing**: every cell drains to its steepest downhill neighbour. Distances are measured in real metres, correcting for the fact that a degree of longitude shrinks with latitude. Chaining these directions gives flow accumulation: how many upstream cells drain through each point.*
> *4. **Site selection**: the cell with the highest accumulation, away from the map edges, is where the most water converges, so that's where the pond goes."*

---

### [1:30 - 2:45] 3. Demonstration: Contour Map Analysis
> *(Switch to **🗺️ Contour Map (KML)**. Drag `tests/sample_data/contours_1m.kml` into the upload zone and click **⚡ Run Contour Flow Analysis**.)*
>
> *"Here's a real one-metre contour survey of a rural watershed near Durg–Bhilai in Chhattisgarh.*
>
> *In about three seconds, the backend parses 1,355 contour lines spanning 31 metres of relief, builds the elevation grid, and routes flow across the whole terrain.*
>
> *On the map:*
> *- The cyan outline is the catchment: all the land whose runoff drains to the pond site.*
> *- The pulsing green marker is the automatically chosen pond site, at **21.2417 north, 81.2869 east**.*
> *- On the right: a catchment of **3.91 square kilometres**, about 391 hectares, with an average slope of **3.99 percent**, gentle enough for safe excavation.*
> *- Expected monsoon runoff is **1.71 million cubic metres**, and the suitability score is **98 out of 100**."*
>
> *(If recording on the campus container, add: "The yellow note says the live rainfall service is blocked on the campus network, so the app used its bundled copy of the same Open-Meteo archive. Same real data, and it tells us where it came from.")*

---

> *(Zoom in on the marker in satellite view.)*
> *"You'll notice the marker sits in the Shivnath river. That's where the most water converges, which is exactly what the algorithm looks for. But it only sees elevation: it doesn't know a river is already there, or who owns the land. So this is a screening result; a site visit and the authorities make the final decision. That's why the next mode matters."*

---

### [2:45 - 3:30] 4. Demonstration: Land Area Selection
> *(Click **📐 Land Area Selection**. Click the **Draw Area Box** tool on the map, drag a rectangle over farmland, then click **🔍 Discover Pond Site & Analyze Basin**.)*
>
> *"Administrators often already know which land is available: say a panchayat plot. I draw a box around it and click Discover.*
>
> *The system downloads real 30-metre SRTM elevation data around the plot, routes flow over the surrounding terrain, and picks the best drainage point **inside** the selected land. The catchment it shows can extend well beyond the plot, because water flows in from upstream.*
>
> *Both the selected parcel and the natural catchment are overlaid on the satellite map."*

---

### [3:30 - 4:15] 5. Rainfall, Hydraulic Sizing & GIS Export
> *(Scroll down the results panel to the sizing section and rainfall chart.)*
>
> *"For sizing, the system pulls ten years of daily rainfall from the Open-Meteo archive. Here the average is about **1,415 millimetres a year**, and **1,251** of that falls in the June-to-September monsoon, as the chart shows.*
>
> *Runoff uses the Rational Method: Q equals C times I times A, with a runoff coefficient of 0.35 for rural farmland, the monsoon rainfall depth, and the catchment area. That gives about 1.7 million cubic metres.*
>
> *To capture seventy percent of it, the recommended pond is **4.5 metres deep**, the safe limit for unlined earthen banks, with a capacity of about **1.2 million cubic metres**. For a catchment this large, that's really the harvesting potential, best split across several ponds or check dams.*
>
> *Finally, **📥 Export GeoJSON Basin** downloads the catchment boundary for QGIS, ArcGIS or engineering tenders."*

---

### [4:15 - 5:00] 6. Resilience, Testing & Conclusion
> *(Show a terminal running `.venv/bin/pytest tests/` (27 passed), then `curl http://10.1.75.53:3247/api/health`.)*
>
> *"The system runs on a shared campus container with a nearly full disk, no database server, and limited internet access, so resilience was designed in:*
> *1. Without PostgreSQL, it switches to a file-based history automatically.*
> *2. If the rainfall service is blocked, it uses a bundled copy of the real archive for this region, or a regional average elsewhere, and always says so on screen. A background probe and a circuit breaker mean no request ever waits on a blocked service.*
> *3. Heavy terrain computation runs off the main event loop, so the health endpoint stays responsive, and a watchdog checks it every sixty seconds and restarts the server if needed, while cleaning temporary files and rotating logs.*
>
> *Our 27 automated tests cover KMZ archives, malformed and empty files, real-format SRTM tiles, caching, the database layer, and the hydrology formulas themselves.*
>
> *In short, Bhagiratha turns elevation and rainfall data into a practical, defensible pond plan in seconds. Thank you!"*
