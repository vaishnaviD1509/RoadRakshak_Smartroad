// Live map page: fetches marker data from /map/api/points, filtered by
// the form above, and redraws without a full page reload. Popups are
// built with textContent (never innerHTML) since the values come from
// user-submitted data.
document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("liveMap");
  if (!mapEl) return;

  const map = L.map(mapEl).setView([20.5937, 78.9629], 5); // India, zoomed out
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  let markers = L.layerGroup().addTo(map);
  let hasFittedOnce = false;

  const form = document.getElementById("mapFilters");
  const emptyState = document.getElementById("mapEmptyState");
  const countLabel = document.getElementById("filterCount");

  function currentParams() {
    const params = new URLSearchParams();
    const complaintId = document.getElementById("filterComplaintId").value.trim();
    const category = document.getElementById("filterCategory").value;
    const status = document.getElementById("filterStatus").value;
    const from = document.getElementById("filterFrom").value;
    const to = document.getElementById("filterTo").value;
    if (complaintId) params.set("complaint_id", complaintId);
    if (category) params.set("category", category);
    if (status) params.set("status", status);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    return params;
  }

  function popupContent(point) {
    const box = document.createElement("div");
    const idLine = document.createElement("strong");
    idLine.textContent = point.id;
    box.appendChild(idLine);
    [point.category, point.status, point.date].forEach((text) => {
      const line = document.createElement("div");
      line.textContent = text;
      box.appendChild(line);
    });
    const link = document.createElement("a");
    link.href = `/track?complaint_id=${encodeURIComponent(point.id)}`;
    link.textContent = "View details";
    box.appendChild(link);
    return box;
  }

  async function loadPoints() {
    let points;
    try {
      const resp = await fetch(`/map/api/points?${currentParams().toString()}`);
      points = await resp.json();
    } catch (err) {
      countLabel.textContent = "Could not load complaints right now.";
      return;
    }

    markers.clearLayers();
    countLabel.textContent = `${points.length} complaint${points.length === 1 ? "" : "s"} shown`;
    emptyState.classList.toggle("d-none", points.length !== 0);

    const bounds = [];
    let placedMarkers = [];
    points.forEach((p) => {
      const marker = L.marker([p.lat, p.lng]).addTo(markers).bindPopup(popupContent(p));
      placedMarkers.push(marker);
      bounds.push([p.lat, p.lng]);
    });

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
      hasFittedOnce = true;
      // A complaint-ID search narrowing to exactly one marker: open its
      // popup right away instead of making the person click it.
      if (document.getElementById("filterComplaintId").value.trim() && placedMarkers.length === 1) {
        placedMarkers[0].openPopup();
      }
    } else if (!hasFittedOnce) {
      map.setView([20.5937, 78.9629], 5);
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    loadPoints();
  });

  document.getElementById("clearFilters").addEventListener("click", () => {
    form.reset();
    loadPoints();
  });

  loadPoints();
});