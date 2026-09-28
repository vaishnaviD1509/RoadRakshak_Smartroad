// Admin pages: draw complaint locations on a Leaflet map.
// Popups are built with textContent (never innerHTML) because the location
// name and category come from user-submitted text.
document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("adminMap");
  const dataEl = document.getElementById("mapData");
  if (!mapEl || !dataEl) return;

  const points = JSON.parse(dataEl.textContent).filter(
    (p) => typeof p.lat === "number" && typeof p.lng === "number"
  );
  if (points.length === 0) return;

  const map = L.map(mapEl).setView([points[0].lat, points[0].lng], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  function line(text, bold) {
    const el = document.createElement(bold ? "strong" : "div");
    el.textContent = text;
    return el;
  }

  const bounds = [];
  points.forEach((p) => {
    const box = document.createElement("div");
    if (p.url) {
      const link = document.createElement("a");
      link.href = p.url;
      link.appendChild(line(p.id, true));
      box.appendChild(link);
    } else {
      box.appendChild(line(p.id, true));
    }
    box.appendChild(line(p.category));
    box.appendChild(line(p.status));
    box.appendChild(line(p.location));

    L.marker([p.lat, p.lng]).addTo(map).bindPopup(box);
    bounds.push([p.lat, p.lng]);
  });

  if (bounds.length > 1) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }
});