/**
 * Urja Meter Ops — Frontend Application Engine
 */

let mapInstance = null;
let mapMarkersLayer = null;
let energyChartInstance = null;
let currentDirectoryPage = 1;
let currentDirectoryTotalPages = 1;
let allMetersCache = [];

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initEventListeners();
  await checkHealth();
  await loadOverviewAnalytics();
  initMap();
  await loadHierarchy();
  await populateMeterSelect();
  await loadMeterEnergy("J100000");
  await loadDirectoryTable();
});

// Tab Navigation
function initTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      
      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }

      // If map tab activated, invalidate map size for correct rendering
      if (targetId === "tab-overview" && mapInstance) {
        setTimeout(() => mapInstance.invalidateSize(), 100);
      }
    });
  });
}

function initEventListeners() {
  document.getElementById("btn-refresh").addEventListener("click", refreshCache);
  document.getElementById("btn-spatial-search").addEventListener("click", executeSpatialSearch);
  document.getElementById("btn-load-energy").addEventListener("click", () => {
    const meterId = document.getElementById("energy-meter-select").value;
    if (meterId) loadMeterEnergy(meterId);
  });
  document.getElementById("btn-apply-filters").addEventListener("click", () => {
    currentDirectoryPage = 1;
    loadDirectoryTable();
  });
  document.getElementById("btn-prev-page").addEventListener("click", () => {
    if (currentDirectoryPage > 1) {
      currentDirectoryPage--;
      loadDirectoryTable();
    }
  });
  document.getElementById("btn-next-page").addEventListener("click", () => {
    if (currentDirectoryPage < currentDirectoryTotalPages) {
      currentDirectoryPage++;
      loadDirectoryTable();
    }
  });
  document.getElementById("dir-search").addEventListener("keyup", (e) => {
    if (e.key === "Enter") {
      currentDirectoryPage = 1;
      loadDirectoryTable();
    }
  });
}

// Health Check
async function checkHealth() {
  try {
    const res = await fetch("/api/v1/health");
    const data = await res.json();
    const pill = document.getElementById("health-pill");
    const text = document.getElementById("health-text");

    if (data.status === "healthy") {
      pill.style.borderColor = "rgba(16, 185, 129, 0.4)";
      text.innerText = `Online (${data.indexed_meters} Meters)`;
    } else {
      text.innerText = "Indexing upstream...";
    }
  } catch (err) {
    document.getElementById("health-text").innerText = "Connecting...";
  }
}

// Overview & Analytics
async function loadOverviewAnalytics() {
  try {
    const res = await fetch("/api/v1/analytics/summary");
    const data = await res.json();

    document.getElementById("kpi-total-meters").innerText = data.total_meters;
    document.getElementById("kpi-health-rate").innerText = `${data.operational_health_score}%`;
    document.getElementById("kpi-installed-count").innerText = data.status_distribution["Installed"] || 0;
    document.getElementById("kpi-faulty-meters").innerText = data.status_distribution["Faulty"] || 0;
    document.getElementById("kpi-decom-meters").innerText = data.status_distribution["Decommissioned"] || 0;
    document.getElementById("kpi-total-dts").innerText = data.total_transformers;
  } catch (err) {
    console.error("Failed to load analytics summary:", err);
  }
}

// Leaflet Map Initialization
function initMap() {
  const mapContainer = document.getElementById("grid-map");
  if (!mapContainer) return;

  // Center around Jaipur Rajasthan utility service area
  mapInstance = L.map("grid-map").setView([26.9124, 75.7873], 12);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19
  }).addTo(mapInstance);

  mapMarkersLayer = L.layerGroup().addTo(mapInstance);

  // Click on map to populate proximity search
  mapInstance.on("click", (e) => {
    document.getElementById("spatial-lat").value = e.latlng.lat.toFixed(4);
    document.getElementById("spatial-lng").value = e.latlng.lng.toFixed(4);
    executeSpatialSearch();
  });

  loadAllMetersOnMap();
}

async function loadAllMetersOnMap() {
  try {
    const res = await fetch("/api/v1/meters?page=1&page_size=100");
    const data = await res.json();
    
    // Fetch all 403 meters across pages or bulk
    let meters = data.data || [];
    if (data.total > 100) {
      const p2 = await (await fetch("/api/v1/meters?page=2&page_size=100")).json();
      const p3 = await (await fetch("/api/v1/meters?page=3&page_size=100")).json();
      const p4 = await (await fetch("/api/v1/meters?page=4&page_size=100")).json();
      const p5 = await (await fetch("/api/v1/meters?page=5&page_size=100")).json();
      meters = meters.concat(p2.data || [], p3.data || [], p4.data || [], p5.data || []);
    }
    allMetersCache = meters;

    mapMarkersLayer.clearLayers();
    const bounds = [];

    meters.forEach(m => {
      if (m.geo && m.geo.latitude && m.geo.longitude) {
        const lat = m.geo.latitude;
        const lng = m.geo.longitude;
        bounds.push([lat, lng]);

        let color = "#10b981"; // Installed
        if (m.install_status === "Faulty") color = "#f59e0b";
        else if (m.install_status === "Decommissioned") color = "#ef4444";

        const marker = L.circleMarker([lat, lng], {
          radius: 5,
          fillColor: color,
          color: "#ffffff",
          weight: 1,
          opacity: 0.9,
          fillOpacity: 0.8
        });

        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px;">
            <strong style="font-size: 14px;">${m.meter_id}</strong> (${m.serial_no})<br>
            <strong>Status:</strong> <span style="color: ${color}; font-weight: bold;">${m.install_status}</span><br>
            <strong>Make / Phase:</strong> ${m.make} • ${m.phase_type}<br>
            <strong>Transformer:</strong> ${m.dt_code}<br>
            <div style="margin-top: 8px;">
              <button onclick="inspectMeterFromMap('${m.meter_id}')" style="background: #3b82f6; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 12px;">View Energy</button>
            </div>
          </div>
        `);

        mapMarkersLayer.addLayer(marker);
      }
    });

    if (bounds.length > 0) {
      mapInstance.fitBounds(bounds, { padding: [20, 20] });
    }
  } catch (err) {
    console.error("Failed to load map meters:", err);
  }
}

window.inspectMeterFromMap = function(meterId) {
  const select = document.getElementById("energy-meter-select");
  select.value = meterId;
  loadMeterEnergy(meterId);
  // Switch to energy tab
  document.querySelector('[data-tab="tab-energy"]').click();
};

// Spatial Proximity Search
async function executeSpatialSearch() {
  const lat = parseFloat(document.getElementById("spatial-lat").value);
  const lng = parseFloat(document.getElementById("spatial-lng").value);
  const radius = parseFloat(document.getElementById("spatial-radius").value);
  const resultsContainer = document.getElementById("spatial-results");

  resultsContainer.innerHTML = '<div class="empty-state">Calculating Haversine distances...</div>';

  try {
    const res = await fetch(`/api/v1/spatial/nearby?latitude=${lat}&longitude=${lng}&radius_km=${radius}&limit=50`);
    const data = await res.json();

    if (!data.meters || data.meters.length === 0) {
      resultsContainer.innerHTML = `<div class="empty-state">No meters found within ${radius} km radius.</div>`;
      return;
    }

    let html = `<div style="font-size: 12px; margin-bottom: 8px; color: #94a3b8;">Found <strong>${data.total_found}</strong> meters within ${radius} km:</div>`;
    data.meters.forEach(item => {
      const m = item.meter;
      let badgeColor = m.install_status === "Installed" ? "dot-installed" : (m.install_status === "Faulty" ? "dot-faulty" : "dot-decom");
      html += `
        <div class="nearby-item" onclick="inspectMeterFromMap('${m.meter_id}')" style="cursor: pointer;">
          <div>
            <span class="legend-dot ${badgeColor}"></span>
            <strong>${m.meter_id}</strong> <span style="color: #94a3b8;">(${m.make})</span>
            <div style="font-size: 11px; color: #94a3b8;">${m.dt_code} • ${m.phase_type}</div>
          </div>
          <div class="nearby-distance">${item.distance_km} km</div>
        </div>
      `;
    });
    resultsContainer.innerHTML = html;
  } catch (err) {
    resultsContainer.innerHTML = `<div class="empty-state" style="color: #ef4444;">Spatial query error: ${err.message}</div>`;
  }
}

// Network Hierarchy
async function loadHierarchy() {
  try {
    const res = await fetch("/api/v1/hierarchy");
    const data = await res.json();
    const stats = data.stats;

    // Render stats bar
    const statsBar = document.getElementById("hierarchy-stats-bar");
    statsBar.innerHTML = `
      <div class="tier-pill">Zones: <strong>${stats.total_zones}</strong></div>
      <div class="tier-pill">Circles: <strong>${stats.total_circles}</strong></div>
      <div class="tier-pill">Divisions: <strong>${stats.total_divisions}</strong></div>
      <div class="tier-pill">Sub-Divisions: <strong>${stats.total_subdivisions}</strong></div>
      <div class="tier-pill">Substations: <strong>${stats.total_substations}</strong></div>
      <div class="tier-pill">Feeders: <strong>${stats.total_feeders}</strong></div>
      <div class="tier-pill">Transformers: <strong>${stats.total_dts}</strong></div>
      <div class="tier-pill">Meters: <strong>${stats.total_meters}</strong></div>
    `;

    document.getElementById("hierarchy-healing-badge").innerText = `✨ ${stats.healed_records_count} Records Automatically Healed`;

    // Render Tree
    const treeContainer = document.getElementById("hierarchy-tree-container");
    treeContainer.innerHTML = renderTreeNodes(data.tree);

    // Tree click to toggle
    treeContainer.querySelectorAll(".tree-node-content").forEach(el => {
      el.addEventListener("click", (e) => {
        const children = el.parentElement.querySelector(".tree-children");
        if (children) {
          const isHidden = children.style.display === "none";
          children.style.display = isHidden ? "block" : "none";
          const toggle = el.querySelector(".tree-toggle");
          if (toggle) toggle.innerText = isHidden ? "▼" : "▶";
        }
      });
    });
  } catch (err) {
    console.error("Failed to load hierarchy:", err);
  }
}

function renderTreeNodes(nodes) {
  if (!nodes || nodes.length === 0) return "";
  let html = "";
  nodes.forEach(node => {
    const hasChildren = node.children && node.children.length > 0;
    html += `
      <div class="tree-node">
        <div class="tree-node-content">
          <span class="tree-toggle">${hasChildren ? "▼" : "•"}</span>
          <span class="tree-tag">${node.type}</span>
          <strong>${node.name}</strong> <span style="color: #64748b;">[${node.code}]</span>
          <span class="tree-count">${node.meter_count} meters</span>
        </div>
        ${hasChildren ? `<div class="tree-children">${renderTreeNodes(node.children)}</div>` : ""}
      </div>
    `;
  });
  return html;
}

// Energy Telemetry & Chart
async function populateMeterSelect() {
  try {
    const res = await fetch("/api/v1/meters?page=1&page_size=50");
    const data = await res.json();
    const select = document.getElementById("energy-meter-select");
    select.innerHTML = "";

    (data.data || []).forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.meter_id;
      opt.innerText = `${m.meter_id} — ${m.make} (${m.dt_code}, ${m.install_status})`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to populate meter select:", err);
  }
}

async function loadMeterEnergy(meterId) {
  try {
    const res = await fetch(`/api/v1/meters/${meterId}/energy`);
    if (!res.ok) throw new Error(`Energy status ${res.status}`);
    const data = await res.json();

    document.getElementById("kpi-energy-kwh").innerText = `${data.total_active_kwh_delta} kWh`;
    document.getElementById("kpi-energy-kvah").innerText = `${data.total_apparent_kvah_delta} kVAh`;
    document.getElementById("kpi-energy-pf").innerText = data.average_power_factor;
    document.getElementById("kpi-energy-vavg").innerText = `${data.avg_voltage_v} V`;
    document.getElementById("kpi-energy-dips").innerText = data.voltage_dip_count;

    renderEnergyChart(data.readings);
  } catch (err) {
    console.error(`Failed to load energy for ${meterId}:`, err);
  }
}

function renderEnergyChart(readings) {
  const ctx = document.getElementById("energy-chart").getContext("2d");

  // Subsample every 4th point for clean visualization (84 points instead of 337)
  const sampled = readings.filter((_, i) => i % 3 === 0);
  const labels = sampled.map(r => r.timestamp.split(" ")[1] || r.timestamp);
  const kwhData = sampled.map(r => r.kwh);
  const voltageData = sampled.map(r => r.volt_r);

  if (energyChartInstance) {
    energyChartInstance.destroy();
  }

  energyChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Active Energy (kWh)",
          data: kwhData,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.1)",
          yAxisID: "y-kwh",
          tension: 0.2,
          pointRadius: 2
        },
        {
          label: "R-Phase Voltage (V)",
          data: voltageData,
          borderColor: "#10b981",
          backgroundColor: "transparent",
          yAxisID: "y-volt",
          tension: 0.1,
          pointRadius: 2,
          borderDash: [4, 4]
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false
      },
      plugins: {
        legend: {
          labels: { color: "#94a3b8" }
        }
      },
      scales: {
        x: {
          ticks: { color: "#64748b", maxTicksLimit: 14 },
          grid: { color: "rgba(51, 65, 85, 0.4)" }
        },
        "y-kwh": {
          type: "linear",
          position: "left",
          ticks: { color: "#3b82f6" },
          grid: { color: "rgba(51, 65, 85, 0.4)" },
          title: { display: true, text: "Active kWh", color: "#3b82f6" }
        },
        "y-volt": {
          type: "linear",
          position: "right",
          min: 190,
          max: 250,
          ticks: { color: "#10b981" },
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Voltage (V)", color: "#10b981" }
        }
      }
    }
  });
}

// Meter Directory Table
async function loadDirectoryTable() {
  const tbody = document.getElementById("meters-table-body");
  const search = document.getElementById("dir-search").value;
  const status = document.getElementById("dir-filter-status").value;
  const phase = document.getElementById("dir-filter-phase").value;
  const make = document.getElementById("dir-filter-make").value;

  let url = `/api/v1/meters?page=${currentDirectoryPage}&page_size=15`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  if (phase) url += `&phase=${encodeURIComponent(phase)}`;
  if (make) url += `&make=${encodeURIComponent(make)}`;

  tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">Loading meters...</td></tr>';

  try {
    const res = await fetch(url);
    const data = await res.json();

    currentDirectoryTotalPages = data.total_pages;
    document.getElementById("pagination-info").innerText = `Showing page ${data.page} of ${data.total_pages} (${data.total} meters)`;
    document.getElementById("btn-prev-page").disabled = (data.page <= 1);
    document.getElementById("btn-next-page").disabled = (data.page >= data.total_pages);

    if (!data.data || data.data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No meters found matching filters.</td></tr>';
      return;
    }

    let rows = "";
    data.data.forEach(m => {
      let badgeClass = "badge-installed";
      if (m.install_status === "Faulty") badgeClass = "badge-faulty";
      else if (m.install_status === "Decommissioned") badgeClass = "badge-decommissioned";

      const healedBadge = m.is_hierarchy_repaired
        ? '<span class="badge badge-healed">✓ Repaired</span>'
        : '<span style="color: #64748b;">—</span>';

      const zoneName = (m.hierarchy && m.hierarchy.zone) ? m.hierarchy.zone.name : "—";
      const feederCode = (m.hierarchy && m.hierarchy.feeder) ? m.hierarchy.feeder.code : "—";

      rows += `
        <tr>
          <td><strong>${m.meter_id}</strong></td>
          <td><code>${m.serial_no}</code></td>
          <td>${m.make}</td>
          <td>${m.phase_type}</td>
          <td><span class="badge ${badgeClass}">${m.install_status}</span></td>
          <td><strong>${m.dt_code}</strong></td>
          <td>${zoneName} / ${feederCode}</td>
          <td>${healedBadge}</td>
          <td>
            <button class="btn btn-sm btn-primary" onclick="inspectMeterFromMap('${m.meter_id}')">Inspect</button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rows;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="color: #ef4444;">Error loading meters: ${err.message}</td></tr>`;
  }
}

// Force Cache Purge & Re-ingestion
async function refreshCache() {
  const btn = document.getElementById("btn-refresh");
  btn.innerText = "Syncing...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/v1/cache/refresh", { method: "POST" });
    const data = await res.json();
    alert(`Upstream sync complete! ${data.total_meters} meters indexed.`);
    await checkHealth();
    await loadOverviewAnalytics();
    await loadAllMetersOnMap();
    await loadHierarchy();
    await loadDirectoryTable();
  } catch (err) {
    alert(`Sync error: ${err.message}`);
  } finally {
    btn.innerText = "↻ Sync";
    btn.disabled = false;
  }
}
