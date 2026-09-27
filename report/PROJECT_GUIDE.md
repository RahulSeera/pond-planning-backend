# Bhagiratha: The Whole Project, Explained Plainly

This is the "what do we actually have?" guide. Read it once before the demo or viva.

---

## 1. What the project does (in one paragraph)

A village administrator opens a web page with a satellite map. They either **draw a box** around land that's available, **upload a contour map** (a KML/KMZ file of elevation lines), or **click a point**. The system works out where rainwater naturally flows and collects, suggests a **pond location**, draws the **catchment** (all the land whose rain drains to that spot), looks up **ten years of rainfall**, and calculates the **expected water volume** plus a recommended **pond depth, size and capacity**. Everything is drawn on the map and summarised in a side panel.

---

## 2. How that covers the assignment brief

| The brief asks for | What we have | Where to show it |
|---|---|---|
| A fully working front-end | Single-page web app, 3 modes, map + results panel | `http://10.1.75.53:3247/` |
| Option to select land on a map | **📐 Land Area Selection**: drag a box, or type its corners | Land Area tab |
| Results based on the selected land | The pond is searched for **inside** your box | Land Area → Discover |
| Suggested pond location | Green marker + coordinates | Map + panel |
| Catchment area | Blue polygon + area in km² | Map (popup and tooltip) + panel |
| Expected water volume | m³ of monsoon runoff | Map (popup and tooltip) + panel |
| All three overlaid on the map | Marker, polygon, parcel box, popup with area and volume | Map |
| Fast and functional | Contour analysis < 1 s; repeat queries in milliseconds | Report Table 4 |
| Stress, scaling, system limits (on the system we picked: sys3) | Stress test on sys3; fixes for its 1-CPU / 512 MB / blocked-network limits | Report §6, §7.1; `report/stress_results_sys3.json` |

---

## 3. How it works, step by step

1. **Get elevation**
   - *Land box or clicked point* → download real satellite elevation data (SRTM, 30 m grid) from **OpenTopography**, a bit larger than your box so upstream land is included.
   - *Contour map* → read every elevation line and fill in a smooth elevation grid between them (Delaunay interpolation).
2. **Clean the terrain.** Fill tiny fake pits so water can always flow downhill (**Priority-Flood** algorithm).
3. **Flow direction.** For every grid cell, find the neighbour it drains to, the steepest downhill one (the **D8** algorithm). We measure distances in real metres; a degree of longitude is shorter than a degree of latitude at 21°N.
4. **Flow accumulation.** Count how many cells drain through each cell. Big numbers = streams.
5. **Pick the pond site.** The cell with the most water flowing in:
   - *Land mode*: inside your box.
   - *Contour mode*: anywhere on the map except the outer 8 % edge.
   - *Point mode*: your click, nudged up to 60 m onto the nearest drainage line.
6. **Catchment.** Trace uphill from the site to find all the land that drains there; turn it into a polygon; measure its area.
7. **Rainfall.** Ten years (2016–2025) of daily rain from **Open-Meteo**; keep the June–September (monsoon) average.
8. **Water volume.** `Q = C × I × A` (runoff coefficient 0.35 × monsoon rain depth × catchment area).
9. **Pond size.** Hold 70 % of Q; depth between 2.5 m (less evaporation) and 4.5 m (safe earthen banks); surface area = volume ÷ depth.
10. **Score (0–100).** 40 % catchment size + 35 % slope + 25 % rainfall.

---

## 4. The three modes: what "best" means

| Mode | You give | It does | Answers |
|---|---|---|---|
| 📍 Point | a click | **scores** your spot | "If I build here, how good is it?" |
| 📐 Land Area | a box | **picks** the best spot inside it | "Where on this land?" |
| 🗺️ Contour | a KML/KMZ file | **picks** the best spot on the whole map | "Where does water collect on this map?" |

"Best" = **where the most runoff converges**. Nothing else. The system does **not** know about existing rivers and canals, land ownership, buildings, soil, groundwater, approvals or cost. That's why the sample demo's marker lands **in the Shivnath river**: hydrologically right, but it's a check-dam spot, not a dug pond. Say this yourself in the demo; it shows you understand the limits.

---

## 5. Reference results (memorise these)

**Sample contour map** (`contours_1m.kml`, 1,355 lines, 267–298 m, near Durg):

| | |
|---|---|
| Site | 21.24171° N, 81.28692° E |
| Catchment | 3.9116 km², slope 3.99 % |
| Rain (2016–2025) | 1,415.2 mm/yr, 1,251.4 mm monsoon |
| Water volume | **1,713,242 m³** |
| Pond | 4.5 m deep, 266,504 m² (26.7 ha), holds 1,199,269 m³ |
| Score | 98 |

**Land box** 21.235–21.255 N × 81.278–81.298 E: site 21.23611, 81.27806 · catchment 7.089 km² · **3,104,911 m³**.

---

## 6. The server (sys3) and what we learned from it

`stu72_sys3`, at `http://10.1.75.53:3247/` (container port 3000). SSH: `ssh -p 2247 student@10.1.75.53`.

| Limit we found (by measuring) | Problem it caused | Fix |
|---|---|---|
| Only **1 CPU**, but it reports 120 cores | Math libraries started 120 threads → an analysis took 28–49 s | `start_server.sh` pins threads to 1 → **0.8 s** |
| Only **512 MB RAM** | 2 analyses at once → out of memory → server killed | Heavy jobs queue one at a time (`app/heavy_jobs.py`) → peak **330 MB**, 0 errors |
| **Open-Meteo & Nominatim blocked** | No live rainfall; each try hung 45 s | Bundled real rainfall for the region (`data/rainfall_cache.json`), background check, circuit breaker |
| **No PostgreSQL** | — | Automatic file mode (`data/analyses_history.json`) |
| **Disk 99 % full** | — | Watchdog deletes temp files, rotates logs |

**Stress test on sys3** (`scripts/stress_test.py`): 446 requests, up to 20 at once, **0 errors**. Health p95 0.28 s; cached point p95 0.42 s; contour 0.84 s alone; health stays at 0.42 s even while 4 contour jobs are queued; memory 291 → 330 MB.

**Watchdog** (`scripts/watchdog.sh`, every 60 s): checks `/api/health`, restarts the server if it's down (with a 90 s grace period for a server that's still starting).

---

## 7. Files you should know

| Path | What it is |
|---|---|
| `app/main.py` | The API: all 9 endpoints, fallbacks, history, startup warm-up |
| `app/heavy_jobs.py` | The one-at-a-time queue for heavy analyses |
| `app/modules/catchment.py` | Terrain cleaning, D8, flow accumulation, site choice, catchment |
| `app/modules/area_analysis.py` | Land-box mode |
| `app/modules/kml_parser.py`, `dem_from_contours.py` | Contour map → elevation grid |
| `app/modules/rainfall.py` | Open-Meteo, bundled data, baseline, circuit breaker |
| `app/modules/recommendation.py` | Q = C·I·A, pond size, score |
| `app/static/` | The web page (HTML, CSS, JavaScript) |
| `scripts/start_server.sh`, `watchdog.sh` | Start and supervise the server |
| `scripts/stress_test.py`, `build_rainfall_cache.py` | Load test; rebuild the bundled rainfall |
| `tests/` | 28 automated tests (`.venv/bin/pytest tests/ -q`) |
| `report/final_report.tex` + `figures/` | The 9-page report (course template) |
| `report/final_report.pdf` | Compiled report |
| `report/DEMO_GUIDE.md` | Live demo plan + Q&A |
| `report/YOUTUBE_DEMO_SCRIPT.md` | 5-minute video script |

---

## 8. Honest limitations (say them before you're asked)

1. It doesn't know about existing water bodies, ownership, land use, soil or approvals, so it's a **screening** tool.
2. Big catchments give huge ponds (26.7 ha here); in reality, split the water across several ponds or check dams.
3. The satellite elevation data is 30 m, so it misses small channels a 1 m survey sees.
4. The runoff coefficient is a fixed 0.35; evaporation and seepage aren't modelled.
5. One server, no load balancer. With 1 CPU a second copy wouldn't help; the queue is the right load control there.

---

## 9. What's left for you

1. **Overleaf:** upload `report/final_report.tex` **and** the `report/figures/` folder (two JPGs). It should compile to 9 pages.
2. **YouTube:** record using `YOUTUBE_DEMO_SCRIPT.md` (only if the course asks for a video).
3. **GitHub:** run `git push origin main` with your personal access token.
