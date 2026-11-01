(() => {
  document.querySelectorAll("[data-geojson-id]").forEach((mapElement) => {
    const payload = document.getElementById(mapElement.dataset.geojsonId);
    const fallback = document.getElementById(mapElement.dataset.fallbackId);
    if (!payload || !window.L) return;

    const data = JSON.parse(payload.textContent);
    const features = data.features || [];
    const points = features.filter((feature) => feature.geometry?.type === "Point");
    const map = L.map(mapElement).setView([-1.94, 29.87], 8);
    let tileErrors = 0;
    let tileFallbackUsed = false;
    const basemapAttribution = "&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>";
    const basemapUrl = () =>
      document.documentElement.dataset.theme === "dark"
        ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
    const tileLayer = L.tileLayer(basemapUrl(), { maxZoom: 19, attribution: basemapAttribution });
    document.addEventListener("farmops:theme", () => {
      if (!tileFallbackUsed) {
        tileErrors = 0;
        tileLayer.setUrl(basemapUrl());
      }
    });
    tileLayer.on("tileerror", () => {
      tileErrors += 1;
      if (tileErrors === 4 && !tileFallbackUsed) {
        tileFallbackUsed = true;
        tileLayer.setUrl("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
        return;
      }
      if (tileErrors >= 12 && fallback) {
        fallback.hidden = false;
        fallback.textContent = "Basemap tiles are unavailable. Report markers and the location list remain available; check connectivity.";
      }
    });
    tileLayer.addTo(map);
    if (fallback) fallback.hidden = true;
    if (!points.length) {
      const emptyNotice = document.createElement("p");
      emptyNotice.className = "map-empty";
      emptyNotice.textContent = "No reports with map coordinates yet. Add coordinates to a report to see it on this map.";
      mapElement.appendChild(emptyNotice);
    }

    const darkMap = document.documentElement.dataset.theme === "dark";
    const palette = darkMap
      ? { report: "#4cc38a", reportEdge: "#1f7a4d", cluster: "#e07864", clusterEdge: "#a33e2c" }
      : { report: "#2f8a5e", reportEdge: "#15583f", cluster: "#d97a5f", clusterEdge: "#963f30" };
    const bounds = [];
    points.forEach((feature) => {
      const [longitude, latitude] = feature.geometry.coordinates;
      const properties = feature.properties || {};
      const cluster = properties.kind === "potential_cluster";
      const marker = L.circleMarker([latitude, longitude], {
        radius: cluster ? 12 : 7,
        color: cluster ? palette.clusterEdge : palette.reportEdge,
        fillColor: cluster ? palette.cluster : palette.report,
        fillOpacity: 0.82,
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
  });
})();
