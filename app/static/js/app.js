/**
 * Bhagiratha — AI-based Village Pond Planning System
 * Interactive Leaflet Frontend Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // Global State
  let currentMode = "point"; // "point", "area", "contour"
  let map, basemaps = {};
  let catchmentLayer = null;
  let pondMarker = null;
  let selectionBoxLayer = null;
  let clickMarker = null;
  let selectedFile = null;
  let currentAnalysisData = null;
  let rainfallChartInstance = null;
  let isDrawingArea = false;
  let drawStartLatLng = null;

  // Initialize Application
  initMap();
  initEventHandlers();
  checkSystemHealth();

  // -------------------------------------------------------------
  // Map Initialization
  // -------------------------------------------------------------
  function initMap() {
    // Default center: Chhattisgarh / Bhilai / Durg basin
    const defaultCenter = [21.24185, 81.28689];
    const defaultZoom = 13;

    map = L.map("map", {
      center: defaultCenter,
      zoom: defaultZoom,
      zoomControl: false,
    });

    // Custom Zoom Control top-right
    L.control.zoom({ position: "topright" }).addTo(map);

    // Basemaps
    basemaps.satellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Esri, Maxar, Earthstar Geographics" }
    );

    basemaps.topo = L.tileLayer(
      "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
      { maxZoom: 17, attribution: "Map data: © OpenStreetMap, SRTM | Map style: © OpenTopoMap" }
    );

    basemaps.cartodark = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      { maxZoom: 20, attribution: "© OpenStreetMap contributors © CARTO" }
    );

    basemaps.osm = L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19, attribution: "© OpenStreetMap contributors" }
    );

    // Add default basemap
    basemaps.satellite.addTo(map);

    // Layer Groups
    catchmentLayer = L.geoJSON(null, {
      style: {
        color: "#06b6d4",
        weight: 3,
        opacity: 0.95,
        fillColor: "#06b6d4",
        fillOpacity: 0.35,
      },
      onEachFeature: (feature, layer) => {
        layer.bindPopup(`
          <div class="popup-title">Delineated Catchment Basin</div>
          <table class="popup-table">
            <tr><td>Area:</td><td><strong>${currentAnalysisData?.catchment_area_km2 || "—"} km²</strong></td></tr>
            <tr><td>Avg Slope:</td><td><strong>${currentAnalysisData?.avg_slope_percent || "—"}%</strong></td></tr>
            <tr><td>Expected Runoff:</td><td><strong>${(currentAnalysisData?.expected_water_volume_m3 || currentAnalysisData?.recommendation?.runoff_m3 || 0).toLocaleString()} m³</strong></td></tr>
          </table>
        `);
      }
    }).addTo(map);

    // Map Event Listeners
    map.on("mousemove", (e) => {
      document.getElementById("hud-lat").textContent = `Lat: ${e.latlng.lat.toFixed(5)}° N`;
      document.getElementById("hud-lon").textContent = `Lon: ${e.latlng.lng.toFixed(5)}° E`;
    });

    map.on("zoomend", () => {
      document.getElementById("hud-zoom").textContent = `Zoom: ${map.getZoom()}`;
    });

    map.on("click", (e) => {
      if (isDrawingArea) return;

      if (currentMode === "point") {
        const lat = parseFloat(e.latlng.lat.toFixed(5));
        const lon = parseFloat(e.latlng.lng.toFixed(5));
        document.getElementById("point-lat").value = lat;
        document.getElementById("point-lon").value = lon;

        if (clickMarker) map.removeLayer(clickMarker);
        clickMarker = L.circleMarker([lat, lon], {
          radius: 7,
          color: "#3b82f6",
          fillColor: "#60a5fa",
          fillOpacity: 0.8,
          weight: 2,
        }).addTo(map).bindTooltip("Selected Candidate Point", { permanent: false });
      }
    });

    // Box selection events on map
    map.on("mousedown", (e) => {
      if (!isDrawingArea) return;
      drawStartLatLng = e.latlng;
      map.dragging.disable();
    });

    map.on("mousemove", (e) => {
      if (!isDrawingArea || !drawStartLatLng) return;
      const bounds = L.latLngBounds(drawStartLatLng, e.latlng);
      if (selectionBoxLayer) map.removeLayer(selectionBoxLayer);
      selectionBoxLayer = L.rectangle(bounds, {
        color: "#f59e0b",
        weight: 2,
        dashArray: "6, 6",
        fillColor: "#f59e0b",
        fillOpacity: 0.15,
      }).addTo(map);

      updateAreaInputsFromBounds(bounds);
    });

    map.on("mouseup", () => {
      if (isDrawingArea && drawStartLatLng) {
        isDrawingArea = false;
        drawStartLatLng = null;
        map.dragging.enable();
        document.getElementById("draw-area-tool-btn").textContent = "📐 Draw Area Box";
        document.getElementById("draw-area-tool-btn").classList.remove("active");
      }
    });
  }

  // -------------------------------------------------------------
  // Event Handlers & UI Controls
  // -------------------------------------------------------------
  function initEventHandlers() {
    // Mode Switcher Tabs
    document.querySelectorAll(".mode-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".mode-tab").forEach((t) => {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        tab.classList.add("active");
        tab.setAttribute("aria-selected", "true");

        currentMode = tab.dataset.mode;
        document.querySelectorAll(".mode-view").forEach((v) => v.classList.remove("active"));
        document.getElementById(`view-${currentMode}`).classList.add("active");
      });
    });

    // Basemap Switcher
    document.getElementById("basemap-dropdown").addEventListener("change", (e) => {
      const selected = e.target.value;
      Object.values(basemaps).forEach((layer) => map.removeLayer(layer));
      if (basemaps[selected]) {
        basemaps[selected].addTo(map);
      }
    });

    // Tool: Draw Area Box
    document.getElementById("draw-area-tool-btn").addEventListener("click", () => {
      isDrawingArea = !isDrawingArea;
      const btn = document.getElementById("draw-area-tool-btn");
      if (isDrawingArea) {
        btn.textContent = "Click & Drag on Map...";
        btn.classList.add("active");
        if (currentMode !== "area") {
          document.getElementById("tab-area").click();
        }
      } else {
        btn.textContent = "📐 Draw Area Box";
        btn.classList.remove("active");
        map.dragging.enable();
      }
    });

    // Tool: Clear Map
    document.getElementById("clear-map-btn").addEventListener("click", () => {
      clearMapOverlays();
      document.getElementById("results-dashboard").style.display = "none";
      document.getElementById("zoom-catchment-btn").disabled = true;
    });

    // Tool: Recenter / Fit Catchment
    document.getElementById("zoom-catchment-btn").addEventListener("click", fitCatchmentBounds);
    document.getElementById("recenter-basin-btn").addEventListener("click", fitCatchmentBounds);

    // Point Analysis Run Button
    document.getElementById("run-point-analysis-btn").addEventListener("click", () => {
      const lat = parseFloat(document.getElementById("point-lat").value);
      const lon = parseFloat(document.getElementById("point-lon").value);
      if (isNaN(lat) || isNaN(lon)) {
        alert("Please enter valid latitude and longitude coordinates.");
        return;
      }
      runPointAnalysis(lat, lon);
    });

    // Area Analysis Run Button
    document.getElementById("run-area-analysis-btn").addEventListener("click", () => {
      const south = parseFloat(document.getElementById("area-south").value);
      const north = parseFloat(document.getElementById("area-north").value);
      const west = parseFloat(document.getElementById("area-west").value);
      const east = parseFloat(document.getElementById("area-east").value);

      if (isNaN(south) || isNaN(north) || isNaN(west) || isNaN(east)) {
        alert("Please specify valid bounding coordinates.");
        return;
      }
      if (south >= north || west >= east) {
        alert("North must be greater than South, and East must be greater than West.");
        return;
      }

      runAreaAnalysis({ min_lat: south, max_lat: north, min_lon: west, max_lon: east });
    });

    // Contour File Upload
    const dropzone = document.getElementById("upload-dropzone");
    const fileInput = document.getElementById("contour-file-input");

    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
      }
    });

    document.getElementById("remove-file-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      selectedFile = null;
      fileInput.value = "";
      document.getElementById("file-info-preview").style.display = "none";
      document.getElementById("upload-dropzone").style.display = "block";
      document.getElementById("run-contour-analysis-btn").disabled = true;
    });

    document.getElementById("run-contour-analysis-btn").addEventListener("click", () => {
      if (!selectedFile) return;
      runContourAnalysis(selectedFile);
    });

    // Load Sample Demo Button
    document.getElementById("load-sample-btn").addEventListener("click", loadSampleDemo);

    // Village Search Autocomplete
    const searchInput = document.getElementById("village-search-input");
    const searchDropdown = document.getElementById("search-results-dropdown");
    const clearSearchBtn = document.getElementById("clear-search-btn");
    let searchTimeout = null;

    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.trim();
      clearSearchBtn.style.display = q ? "block" : "none";
      clearTimeout(searchTimeout);

      if (q.length < 2) {
        searchDropdown.style.display = "none";
        return;
      }

      searchTimeout = setTimeout(async () => {
        try {
          const resp = await fetch(`/api/villages/search?q=${encodeURIComponent(q)}`);
          const data = await resp.json();
          renderSearchResults(data.results);
        } catch (err) {
          console.error("Village search error:", err);
        }
      }, 250);
    });

    clearSearchBtn.addEventListener("click", () => {
      searchInput.value = "";
      clearSearchBtn.style.display = "none";
      searchDropdown.style.display = "none";
    });

    // Modals
    document.getElementById("history-modal-btn").addEventListener("click", openHistoryModal);
    document.getElementById("close-history-modal").addEventListener("click", () => {
      document.getElementById("history-modal").style.display = "none";
    });

    document.getElementById("guide-modal-btn").addEventListener("click", () => {
      document.getElementById("guide-modal").style.display = "flex";
    });
    document.getElementById("close-guide-modal").addEventListener("click", () => {
      document.getElementById("guide-modal").style.display = "none";
    });

    // Export Buttons
    document.getElementById("export-geojson-btn").addEventListener("click", exportGeoJSON);
    document.getElementById("download-report-btn").addEventListener("click", printSummaryReport);
    document.getElementById("copy-coords-btn").addEventListener("click", copyCoordinates);
  }

  // -------------------------------------------------------------
  // File Handling
  // -------------------------------------------------------------
  function handleFileSelect(file) {
    const ext = file.name.split(".").pop().toLowerCase();
    if (ext !== "kml" && ext !== "kmz") {
      alert("Please upload a .kml or .kmz contour file.");
      return;
    }
    selectedFile = file;
    document.getElementById("preview-filename").textContent = file.name;
    document.getElementById("preview-filesize").textContent = formatBytes(file.size);

    document.getElementById("upload-dropzone").style.display = "none";
    document.getElementById("file-info-preview").style.display = "flex";
    document.getElementById("run-contour-analysis-btn").disabled = false;
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(2) + " MB";
  }

  // -------------------------------------------------------------
  // API Calls
  // -------------------------------------------------------------
  async function runPointAnalysis(lat, lon) {
    showLoading("Analyzing Point Coordinates...", "Fetching elevation raster, calculating D8 flow & historical precipitation...");
    try {
      const resp = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lon }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Point analysis failed.");
      }
      const data = await resp.json();
      currentAnalysisData = {
        suggested_pond_site: { lat: data.lat, lon: data.lon },
        catchment_area_km2: data.terrain.area_km2,
        avg_slope_percent: data.terrain.avg_slope,
        catchment_polygon: data.terrain.catchment_polygon,
        expected_water_volume_m3: data.recommendation ? data.recommendation.runoff_m3 : 0,
        rainfall: data.rainfall,
        recommendation: data.recommendation,
        warnings: data.warnings,
      };
      renderResults(currentAnalysisData, "Point-based Analysis");
    } catch (err) {
      alert(`Analysis Error: ${err.message}`);
    } finally {
      hideLoading();
    }
  }

  async function runAreaAnalysis(bounds) {
    showLoading("Evaluating Land Area...", "Computing flow accumulation over land area and discovering optimal drainage site...");
    try {
      const resp = await fetch("/api/analyze-area", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bounds, name: "Selected Boundary" }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Land area analysis failed.");
      }
      const data = await resp.json();
      currentAnalysisData = data;
      renderResults(currentAnalysisData, "Land Area Selection");
    } catch (err) {
      alert(`Area Analysis Error: ${err.message}`);
    } finally {
      hideLoading();
    }
  }

  async function runContourAnalysis(file) {
    showLoading("Processing Contour Map...", "Parsing contour lines, interpolating DEM grid, routing D8 flow directions...");
    try {
      const formData = new FormData();
      formData.append("contour_map", file);

      const resp = await fetch("/analyzeContour", {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Contour analysis failed.");
      }
      const data = await resp.json();
      currentAnalysisData = data;
      renderResults(currentAnalysisData, `Contour Map: ${data.source_filename}`);
    } catch (err) {
      alert(`Contour Processing Error: ${err.message}`);
    } finally {
      hideLoading();
    }
  }

  async function loadSampleDemo() {
    showLoading("Loading Chhattisgarh Sample Demo...", "Parsing 1,355 contour lines from sample KML and running hydrological pipeline...");
    try {
      // Run the REAL bundled 1m contour survey through the contour pipeline
      map.flyTo([21.2417, 81.2869], 14, { duration: 1.2 });

      const kmlResp = await fetch("/api/sample-contour");
      if (!kmlResp.ok) throw new Error("Sample contour file is not available on this server.");
      const formData = new FormData();
      formData.append("contour_map", await kmlResp.blob(), "contours_1m.kml");

      const resp = await fetch("/analyzeContour", {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Sample contour analysis failed.");
      }
      const data = await resp.json();
      currentAnalysisData = data;
      renderResults(currentAnalysisData, "Chhattisgarh Sample Demo (1m Contours)");
    } catch (err) {
      alert(`Demo Error: ${err.message}`);
    } finally {
      hideLoading();
    }
  }

  // -------------------------------------------------------------
  // Rendering Results & Visual Overlays
  // -------------------------------------------------------------
  function renderResults(data, title) {
    document.getElementById("results-dashboard").style.display = "flex";
    document.getElementById("results-title").textContent = title || "Optimal Pond Planning Results";

    const pond = data.suggested_pond_site || { lat: 0, lon: 0 };
    const areaKm2 = data.catchment_area_km2 || 0;
    const areaHa = (areaKm2 * 100).toFixed(1);
    const volumeM3 = data.expected_water_volume_m3 || data.recommendation?.runoff_m3 || 0;
    const volumeML = (volumeM3 / 1000).toFixed(1);
    const slope = data.avg_slope_percent || 0;
    const rec = data.recommendation || { depth_m: 4.5, surface_area_m2: 0, capacity_m3: 0, suitability_score: 90 };

    // Metric Cards
    document.getElementById("res-coords").textContent = `${pond.lat.toFixed(5)}, ${pond.lon.toFixed(5)}`;
    document.getElementById("res-catchment-area").textContent = areaKm2.toFixed(4);
    document.getElementById("res-catchment-ha").textContent = `≈ ${areaHa} Hectares`;
    document.getElementById("res-water-volume").textContent = Math.round(volumeM3).toLocaleString();
    document.getElementById("res-water-volume-ml").textContent = `≈ ${volumeML} Million Litres`;
    document.getElementById("res-slope").textContent = slope.toFixed(2);

    // Suitability Badge
    const score = Math.round(rec.suitability_score || 85);
    document.getElementById("res-score-badge").textContent = score;

    // Sizing Parameters
    document.getElementById("res-pond-depth").textContent = `${rec.depth_m || 4.5} m`;
    document.getElementById("res-pond-area").textContent = `${Math.round(rec.surface_area_m2 || 0).toLocaleString()} m²`;
    document.getElementById("res-pond-capacity").textContent = `${Math.round(rec.capacity_m3 || 0).toLocaleString()} m³`;

    if (score >= 80) {
      document.getElementById("res-suitability-grade").textContent = `Highly Suitable (${score}/100)`;
      document.getElementById("res-suitability-grade").style.color = "#10b981";
      document.getElementById("res-suitability-desc").textContent = "Excellent natural drainage convergence & gentle slope";
    } else if (score >= 60) {
      document.getElementById("res-suitability-grade").textContent = `Moderately Suitable (${score}/100)`;
      document.getElementById("res-suitability-grade").style.color = "#06b6d4";
      document.getElementById("res-suitability-desc").textContent = "Viable catchment; standard excavation recommended";
    } else {
      document.getElementById("res-suitability-grade").textContent = `Marginal (${score}/100)`;
      document.getElementById("res-suitability-grade").style.color = "#f59e0b";
      document.getElementById("res-suitability-desc").textContent = "Steep terrain or small catchment basin";
    }

    // Precipitation Profile
    const rainfall = data.rainfall || { annual_avg_mm: 1180, seasonal: { monsoon_mm: 940, non_monsoon_mm: 240 }, data_years: 10 };
    document.getElementById("res-annual-rain").textContent = `${rainfall.annual_avg_mm} mm`;
    const monsoon = rainfall.seasonal?.monsoon_mm || 0;
    const nonMonsoon = rainfall.seasonal?.non_monsoon_mm || 0;
    const totalRain = monsoon + nonMonsoon || 1;
    document.getElementById("res-monsoon-rain").textContent = `${monsoon} mm (${((monsoon / totalRain) * 100).toFixed(1)}%)`;
    document.getElementById("res-non-monsoon-rain").textContent = `${nonMonsoon} mm (${((nonMonsoon / totalRain) * 100).toFixed(1)}%)`;

    renderRainfallChart(monsoon, nonMonsoon);

    // Warnings
    const warnBox = document.getElementById("results-warnings-box");
    const warnContent = document.getElementById("results-warnings-content");
    if (data.warnings && data.warnings.length > 0) {
      warnContent.innerHTML = data.warnings.map((w) => `<p>• ${w}</p>`).join("");
      warnBox.style.display = "flex";
    } else {
      warnBox.style.display = "none";
    }

    // Render Map Overlays
    renderMapOverlays(data);
    document.getElementById("zoom-catchment-btn").disabled = false;
  }

  function renderMapOverlays(data) {
    // 1. Clear previous layers
    catchmentLayer.clearLayers();
    if (pondMarker) map.removeLayer(pondMarker);

    // 2. Add Catchment GeoJSON Polygon
    if (data.catchment_polygon && data.catchment_polygon.coordinates && data.catchment_polygon.coordinates.length > 0) {
      catchmentLayer.addData(data.catchment_polygon);
    }

    // 3. Add Suggested Pond Marker
    const pond = data.suggested_pond_site;
    if (pond && pond.lat && pond.lon) {
      const customPondIcon = L.divIcon({
        className: "pond-pulse-marker",
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });

      pondMarker = L.marker([pond.lat, pond.lon], { icon: customPondIcon }).addTo(map);
      pondMarker.bindPopup(`
        <div class="popup-title">💧 Recommended Pond Location</div>
        <table class="popup-table">
          <tr><td>Latitude:</td><td><strong>${pond.lat.toFixed(6)}° N</strong></td></tr>
          <tr><td>Longitude:</td><td><strong>${pond.lon.toFixed(6)}° E</strong></td></tr>
          <tr><td>Recommended Depth:</td><td><strong>${data.recommendation?.depth_m || 4.5} m</strong></td></tr>
          <tr><td>Planned Capacity:</td><td><strong>${(data.recommendation?.capacity_m3 || 0).toLocaleString()} m³</strong></td></tr>
        </table>
      `).openPopup();
    }

    // 4. Zoom to fit
    fitCatchmentBounds();
  }

  function fitCatchmentBounds() {
    if (catchmentLayer && catchmentLayer.getLayers().length > 0) {
      map.fitBounds(catchmentLayer.getBounds(), { padding: [40, 40], maxZoom: 16 });
    } else if (pondMarker) {
      map.setView(pondMarker.getLatLng(), 15);
    }
  }

  function clearMapOverlays() {
    catchmentLayer.clearLayers();
    if (pondMarker) map.removeLayer(pondMarker);
    if (selectionBoxLayer) map.removeLayer(selectionBoxLayer);
    if (clickMarker) map.removeLayer(clickMarker);
  }

  function renderRainfallChart(monsoonMm, nonMonsoonMm) {
    const ctx = document.getElementById("rainfall-chart").getContext("2d");
    if (rainfallChartInstance) {
      rainfallChartInstance.destroy();
    }

    rainfallChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Monsoon (Jun-Sep)", "Non-Monsoon (Oct-May)"],
        datasets: [{
          label: "Precipitation (mm)",
          data: [monsoonMm, nonMonsoonMm],
          backgroundColor: ["#06b6d4", "#3b82f6"],
          borderColor: ["#0891b2", "#2563eb"],
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            ticks: { color: "#9ca3af", font: { size: 10 } }
          },
          x: {
            grid: { display: false },
            ticks: { color: "#e5e7eb", font: { size: 11, weight: "500" } }
          }
        }
      }
    });
  }

  function updateAreaInputsFromBounds(bounds) {
    document.getElementById("area-south").value = bounds.getSouth().toFixed(4);
    document.getElementById("area-north").value = bounds.getNorth().toFixed(4);
    document.getElementById("area-west").value = bounds.getWest().toFixed(4);
    document.getElementById("area-east").value = bounds.getEast().toFixed(4);
  }

  // -------------------------------------------------------------
  // Search Autocomplete Rendering
  // -------------------------------------------------------------
  function renderSearchResults(results) {
    const dropdown = document.getElementById("search-results-dropdown");
    if (!results || results.length === 0) {
      dropdown.innerHTML = '<div class="search-item"><span class="search-item-name">No matching locations found</span></div>';
      dropdown.style.display = "block";
      return;
    }

    dropdown.innerHTML = results.map((v) => `
      <div class="search-item" data-lat="${v.lat}" data-lon="${v.lon}" data-name="${v.name}">
        <div>
          <span class="search-item-name">${v.name}</span>
          <div class="search-item-location">${v.district ? v.district + ", " : ""}${v.state}</div>
        </div>
        <span style="font-size: 11px; color: var(--accent-cyan);">Select ➜</span>
      </div>
    `).join("");

    dropdown.style.display = "block";

    dropdown.querySelectorAll(".search-item").forEach((item) => {
      item.addEventListener("click", () => {
        const lat = parseFloat(item.dataset.lat);
        const lon = parseFloat(item.dataset.lon);
        const name = item.dataset.name;

        document.getElementById("village-search-input").value = name;
        dropdown.style.display = "none";

        map.flyTo([lat, lon], 14, { duration: 1.5 });
        document.getElementById("point-lat").value = lat.toFixed(5);
        document.getElementById("point-lon").value = lon.toFixed(5);

        // Center search coordinates in area mode bounds as well
        document.getElementById("area-south").value = (lat - 0.015).toFixed(4);
        document.getElementById("area-north").value = (lat + 0.015).toFixed(4);
        document.getElementById("area-west").value = (lon - 0.015).toFixed(4);
        document.getElementById("area-east").value = (lon + 0.015).toFixed(4);
      });
    });
  }

  // -------------------------------------------------------------
  // Modals & History
  // -------------------------------------------------------------
  async function openHistoryModal() {
    const modal = document.getElementById("history-modal");
    modal.style.display = "flex";
    const container = document.getElementById("history-list-container");
    container.innerHTML = '<div class="loading-spinner-small">Fetching recent calculations...</div>';

    try {
      const resp = await fetch("/api/analyses/recent");
      const data = await resp.json();
      if (!data.analyses || data.analyses.length === 0) {
        container.innerHTML = '<p style="font-size: 13px; color: var(--text-dim); padding: 12px;">No past analyses recorded yet. Run a point or area analysis to populate history.</p>';
        return;
      }

      container.innerHTML = data.analyses.map((a) => `
        <div class="history-item" data-id="${a.request_id}" data-lat="${a.lat}" data-lon="${a.lon}">
          <div class="hist-left">
            <strong>Request #${a.request_id} — (${a.lat}, ${a.lon})</strong>
            <span>${a.created_at ? new Date(a.created_at).toLocaleString() : "Recently calculated"}</span>
          </div>
          <div class="hist-right">
            <strong>${a.area_km2.toFixed(3)} km²</strong>
            <span>${Math.round(a.runoff_m3).toLocaleString()} m³ runoff</span>
          </div>
        </div>
      `).join("");

      container.querySelectorAll(".history-item").forEach((item) => {
        item.addEventListener("click", () => {
          const lat = parseFloat(item.dataset.lat);
          const lon = parseFloat(item.dataset.lon);
          modal.style.display = "none";
          map.flyTo([lat, lon], 14);
          document.getElementById("point-lat").value = lat;
          document.getElementById("point-lon").value = lon;
          runPointAnalysis(lat, lon);
        });
      });
    } catch (err) {
      container.innerHTML = `<p style="color: #ef4444; font-size: 12px;">Could not load history: ${err.message}</p>`;
    }
  }

  // -------------------------------------------------------------
  // System Health Monitoring
  // -------------------------------------------------------------
  async function checkSystemHealth() {
    try {
      const resp = await fetch("/api/health");
      if (resp.ok) {
        const health = await resp.json();
        const indicator = document.getElementById("system-status-indicator");
        indicator.title = `Server Online | PID: ${health.pid} | Memory: ${health.memory_mb} MB | Uptime: ${health.uptime_seconds}s`;
      }
    } catch (e) {
      const indicator = document.getElementById("system-status-indicator");
      indicator.classList.remove("live");
      indicator.style.borderColor = "#ef4444";
      indicator.style.color = "#ef4444";
      indicator.querySelector(".status-dot").style.background = "#ef4444";
      indicator.querySelector(".status-label").textContent = "Offline";
    }
  }

  // -------------------------------------------------------------
  // Utilities & Exports
  // -------------------------------------------------------------
  function showLoading(title, subtitle) {
    document.getElementById("control-card").style.display = "none";
    document.getElementById("results-dashboard").style.display = "none";
    document.getElementById("loading-card").style.display = "block";
    document.getElementById("loading-title").textContent = title;
    document.getElementById("loading-subtitle").textContent = subtitle;
  }

  function hideLoading() {
    document.getElementById("loading-card").style.display = "none";
    document.getElementById("control-card").style.display = "block";
  }

  function copyCoordinates() {
    const coords = document.getElementById("res-coords").textContent;
    navigator.clipboard.writeText(coords).then(() => {
      const btn = document.getElementById("copy-coords-btn");
      btn.textContent = "✓";
      setTimeout(() => (btn.textContent = "📋"), 1500);
    });
  }

  function exportGeoJSON() {
    if (!currentAnalysisData || !currentAnalysisData.catchment_polygon) {
      alert("No catchment boundary available to export.");
      return;
    }
    const featureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            name: "Delineated Catchment Basin",
            area_km2: currentAnalysisData.catchment_area_km2,
            avg_slope_percent: currentAnalysisData.avg_slope_percent,
            expected_runoff_m3: currentAnalysisData.expected_water_volume_m3,
          },
          geometry: currentAnalysisData.catchment_polygon,
        },
        {
          type: "Feature",
          properties: {
            name: "Recommended Pond Location",
            depth_m: currentAnalysisData.recommendation?.depth_m,
            capacity_m3: currentAnalysisData.recommendation?.capacity_m3,
          },
          geometry: {
            type: "Point",
            coordinates: [
              currentAnalysisData.suggested_pond_site.lon,
              currentAnalysisData.suggested_pond_site.lat,
            ],
          },
        }
      ],
    };

    const blob = new Blob([JSON.stringify(featureCollection, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `catchment_basin_${Date.now()}.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printSummaryReport() {
    window.print();
  }
});
