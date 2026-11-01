(() => {
  const mapElement = document.getElementById("risk-map");
  const payload = document.getElementById("risk-geojson");
  const fallback = document.getElementById("map-fallback");
  if (!mapElement || !payload || !window.L) return;

  const data = JSON.parse(payload.textContent);
  const features = data.features || [];
  const points = features.filter((feature) => feature.geometry?.type === "Point");
  const map = L.map(mapElement).setView([-1.94, 29.87], 8);
  const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  if (fallback) {
    fallback.hidden = true;
    tileLayer.on("tileerror", () => {
      fallback.hidden = false;
      fallback.textContent =
        "Basemap tiles are unavailable. Report markers and the location list remain available; check connectivity to OpenStreetMap.";
    });
  }

  const bounds = [];
  points.forEach((feature) => {
    const [longitude, latitude] = feature.geometry.coordinates;
    const properties = feature.properties || {};
    const cluster = properties.kind === "potential_cluster";
    const marker = L.circleMarker([latitude, longitude], {
      radius: cluster ? 12 : 7,
      color: cluster ? "#a64b34" : "#245b3e",
      fillColor: cluster ? "#d98767" : "#66a477",
      fillOpacity: 0.78,
      weight: cluster ? 3 : 1,
    }).addTo(map);

    const popup = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = cluster
      ? `${properties.label}: ${properties.count} reports`
      : `${properties.is_synthetic ? "SYNTHETIC · " : ""}Case #${properties.case_id} · ${properties.observation_ref} · ${properties.crop}`;
    popup.appendChild(heading);
    const details = document.createElement("p");
    details.textContent = cluster
      ? `${properties.crop} · ${properties.explanation}`
      : `${properties.issue_type} · ${properties.district} · ${properties.review_status}`;
    popup.appendChild(details);
    if (!cluster && properties.url) {
      const link = document.createElement("a");
      link.href = properties.url;
      link.textContent = "Open field report";
      popup.appendChild(link);
    }
    marker.bindPopup(popup);
    bounds.push([latitude, longitude]);
  });

  if (bounds.length) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 11 });
})();
