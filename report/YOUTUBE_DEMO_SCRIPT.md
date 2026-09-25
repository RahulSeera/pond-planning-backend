# YouTube 5-Minute Demo Video Script & Walkthrough
**System**: Bhagiratha: AI-based Village Pond Planning & Catchment Delineation System  
**Presenter**: Rahul Seera (IIT Bhilai)  
**Target Duration**: 4 minutes 45 seconds (Max: 5:00)

---

## Video Outline & Timeline

| Timestamp | Segment | Visual on Screen | Key Spoken Points |
|---|---|---|---|
| **0:00 - 0:45** | **1. Introduction & Motivation** | Full-screen web UI at `http://10.1.75.53:3247/` (or `http://localhost:8000/`), zooming into title and satellite basemap. | Problem statement: Rural water security, unscientific pond excavation. Introduce Bhagiratha as an automated decision-support system. |
| **0:45 - 1:30** | **2. Architecture & Algorithms** | Architecture diagram or Info Modal (`ℹ️ Info`), showing 4-step pipeline: Contour $\to$ DEM $\to$ D8 Flow Routing $\to$ Rational Runoff. | Explain Priority-Flood depression filling, D8 steepest descent, flow accumulation, and the interior convergence heuristic. |
| **1:30 - 2:45** | **3. Live Demo — Contour Map Upload & Auto Site Selection** | Upload `contours_1m.kml` via drag-and-drop. Show progress bar, then the rendered cyan catchment basin and pulsing green marker. | Highlight auto-discovery: 1,355 contours parsed, 267–298m relief, suggested pond at (21.24185, 81.28689), 3.87 km² basin, 1.27M m³ expected water volume. |
| **2:45 - 3:30** | **4. Live Demo — Land Area Selection Mode** | Switch to **"📐 Land Area Selection"** tab. Draw a bounding box on the map. Click **"Discover Pond Site & Analyze Basin"**. | Show that users can select any candidate agricultural area. The system extracts topography, auto-discovers optimal drainage outlet, and sizes reservoir. |
| **3:30 - 4:15** | **5. Precipitation Profile, Hydraulic Sizing & GeoJSON Export** | Scroll through right dashboard: Sizing table, Chart.js Monsoon graph, click **"Export Catchment GeoJSON"** and show downloaded file. | Explain Rational Method $Q = C \cdot I \cdot A$ with $C=0.35$, monsoon precipitation from Open-Meteo, 70% capture efficiency, and GIS export. |
| **4:15 - 5:00** | **6. System Resilience & Conclusion** | Terminal showing test suite passing (`test_extended.py`), health endpoint `/api/health`, and watchdog auto-recovery script. | Highlight resilience: memory-efficient point decimation, watchdog daemon preventing disk pressure on 94% full container, and summary. |

---

## Detailed Minute-by-Minute Narration Script

### [0:00 - 0:45] 1. Introduction & Problem Statement
> *"Hello everyone! My name is Rahul Seera, and today I am presenting **Bhagiratha**, an AI-enabled geospatial decision-support system for village pond planning and automated catchment delineation.*  
>  
> *Under rural water conservation initiatives such as Mission Amrit Sarovar, thousands of farm ponds are excavated annually. However, without scientific hydrological analysis, ponds are often excavated in arbitrary locations outside natural drainage paths, resulting in dry reservoirs or failure during monsoons.  
>  
> *Bhagiratha solves this problem end-to-end. By combining digital elevation models, vector contour interpolation, D8 hydrological flow routing, and 10-year historical precipitation reanalysis, our system automatically determines the scientifically optimal pond location, delineates the contributing catchment basin, computes harvestable runoff volume, and sizes the reservoir for 70% seasonal capture efficiency."*

---

### [0:45 - 1:30] 2. System Architecture & Hydrological Algorithm
> *(Click the **"ℹ️ Info"** button on the top-right to display the System Architecture modal).*  
>  
> *"Our system is architected as an asynchronous modular monolith built on FastAPI, Rasterio, PySheds, GeoAlchemy2, PostgreSQL/PostGIS, and Leaflet.js.  
>  
> *The hydrological pipeline operates in four rigorous stages:  
> 1. **Terrain Ingestion**: The system accepts point clicks, drawn boundaries, or vector KML/KMZ contour maps. Scattered contour points are interpolated into a continuous GeoTIFF DEM using SciPy 2D Delaunay triangulation with convex-hull nearest-neighbor filling.  
> 2. **Conditioning**: Using the Barnes Priority-Flood algorithm, digital depressions and sinks are conditioned and horizontal flats are resolved.  
> 3. **D8 Flow Direction & Accumulation**: Steepest-descent vectors are calculated across 8 adjacent neighbors. Chaining these vectors produces a flow-accumulation matrix showing how many upstream cells drain through each point.  
> 4. **Auto Site Discovery**: Unlike conventional tools requiring manual coordinate inputs, our interior convergence heuristic scans the accumulation grid to automatically locate the natural drainage confluence, excluding boundary edge-artifacts."*

---

### [1:30 - 2:45] 3. Demonstration: Contour Map Analysis
> *(Switch to the **"🗺️ Contour Map (KML)"** tab. Drag and drop `tests/sample_data/contours_1m.kml` into the upload zone, or click **"Load Sample Demo"**).*  
>  
> *"Now let's demonstrate the system using the official 1-meter contour benchmark dataset from a rural watershed in Chhattisgarh.  
>  
> *I upload the file and click **'Run Contour Flow Analysis'**.  
> In under 3 seconds, the backend parses 1,355 contour lines across a 31-meter relief, interpolates the grid, and routes flow across the entire terrain.  
>  
> *Look at the Leaflet map:  
> - The cyan boundary is the exact delineated catchment basin draining into the valley.  
> - The animated pulsing green marker shows the automatically discovered optimal pond site at **latitude 21.24185° N, longitude 81.28689° E**.  
> - On the right panel, we immediately observe the key metrics:  
>   - **Catchment Area**: **3.8715 square kilometers** (or 387 hectares).  
>   - **Expected Water Volume**: **1,273,723 cubic meters** (over 1.27 billion liters).  
>   - **Average Slope**: **4.02%**, ideal for gentle earthen excavation.  
>   - **Overall Suitability Score**: **92 out of 100**, classified as Highly Suitable."*

---

### [2:45 - 3:30] 4. Demonstration: Interactive Land Area Selection
> *(Click the **"📐 Land Area Selection"** tab. Click **"Draw Area Box"** on the floating toolbar, drag a box over an agricultural zone, and click **"Discover Pond Site & Analyze Basin"**).*  
>  
> *"In addition to file uploads, village administrators can select candidate land areas directly on the map.  
> I click **'Draw Area Box'** and drag a rectangle over an agricultural sector. When I click **'Discover Pond Site & Analyze Basin'**, the system dynamically extracts the local topography, runs interior flow routing within the drawn boundary, identifies the optimal pour point, and delineates the upstream basin.  
>  
> *Both the user's selected land area and the resulting natural catchment boundary are overlaid simultaneously on the high-resolution satellite basemap."*

---

### [3:30 - 4:15] 5. Precipitation Profile, Hydraulic Sizing & GIS Export
> *(Scroll down the right panel to show the Hydraulic Sizing and Rainfall Chart).*  
>  
> *"To size the pond accurately, the system queries the Open-Meteo Historical Weather API for 10 years of daily precipitation data.  
> For this location, annual precipitation averages **1,180 mm**, with **940 mm** concentrated in the June-to-September monsoon season, visualized in this Chart.js interactive graph.  
>  
> *Applying the Rational Method ($Q = C \times I \times A$) with a calibrated rural runoff coefficient of $0.35$, the system computes an expected monsoon runoff of 1.27 million cubic meters.  
> To capture 70% of this runoff, the hydraulic sizing engine recommends:  
> - An excavation depth of **4.5 meters** to minimize surface evaporation losses,  
> - A surface footprint of **198,134 square meters**, and  
> - A target capacity of **891,606 cubic meters**.  
>  
> *Finally, with one click on **'Export Catchment GeoJSON'**, administrators can download the standard GIS polygon file for integration into QGIS, ArcGIS, or government engineering tenders."*

---

### [4:15 - 5:00] 6. System Resilience, Testing & Conclusion
> *(Show terminal with passing test suite `python3 tests/test_extended.py` and the health endpoint `/api/health`).*  
>  
> *"For deployment on resource-constrained containers with 94% disk usage, we implemented critical engineering safeguards:  
> 1. Point decimation to bound interpolation memory,  
> 2. Automated watchdog supervisor with 60-second health polling and auto-recovery, and  
> 3. Automatic temporary raster pruning and log rotation.  
>  
> *Our automated test suite rigorously validates edge cases including compressed KMZ archives, empty files, malformed XML, and spatial caching.  
>  
> *In summary, Bhagiratha bridges hydrological science and rural administrative practice, providing a fast, resilient, and scientific solution for village water security. Thank you!"*
