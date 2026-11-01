(() => {
  var payload = document.getElementById("trend-data");
  var container = document.getElementById("intake-chart");
  if (!payload || !container) return;
  var days = [];
  try {
    days = JSON.parse(payload.textContent) || [];
  } catch (error) {
    container.textContent = "Trend data is unavailable.";
    return;
  }
  var NS = "http://www.w3.org/2000/svg";
  var W = 560, H = 220, PAD_L = 34, PAD_B = 26, PAD_T = 10;

  function el(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function render(windowDays) {
    var data = days.slice(-windowDays);
    while (container.firstChild) container.removeChild(container.firstChild);
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", "aria-label": "Daily intake for the last " + data.length + " days" }, container);
    var max = 1;
    var hasData = false;
    data.forEach(function (d) {
      max = Math.max(max, d.total);
      if (d.total > 0) hasData = true;
    });
    var plotW = W - PAD_L - 8, plotH = H - PAD_T - PAD_B;
    [0, 0.5, 1].forEach(function (frac) {
      var value = Math.round(max * frac);
      var y = PAD_T + plotH - (plotH * frac);
      el("line", { x1: PAD_L, y1: y, x2: W - 8, y2: y, "class": "grid-line" }, svg);
      var label = el("text", { x: PAD_L - 6, y: y + 3, "class": "axis-label", "text-anchor": "end" }, svg);
      label.textContent = value;
    });
    if (!data.length || !hasData) {
      var empty = el("text", { x: W / 2, y: H / 2 - 6, "class": "chart-empty", "text-anchor": "middle" }, svg);
      empty.textContent = "No intake in this window.";
      return;
    }
    var slot = plotW / data.length;
    var barW = Math.max(4, Math.min(26, slot * 0.55));
    var step = Math.max(1, Math.ceil(data.length / 7));
    data.forEach(function (d, i) {
      var x = PAD_L + slot * i + (slot - barW) / 2;
      var baseH = (plotH * d.total) / max;
      var urgH = (plotH * Math.min(d.urgent, d.total)) / max;
      var g = el("g", {}, svg);
      var title = el("title", {}, g);
      title.textContent = d.label + " — " + d.total + " reports (" + d.urgent + " urgent)";
      if (d.total > 0) {
        el("rect", { x: x.toFixed(1), y: (PAD_T + plotH - baseH).toFixed(1), width: barW.toFixed(1), height: Math.max(baseH, 2).toFixed(1), rx: 2, "class": "bar-total" }, g);
        if (d.urgent > 0 && urgH > 0) {
          el("rect", { x: x.toFixed(1), y: (PAD_T + plotH - baseH).toFixed(1), width: barW.toFixed(1), height: Math.max(urgH, 2).toFixed(1), rx: 2, "class": "bar-urgent" }, g);
        }
      }
      if (i % step === 0 || i === data.length - 1) {
        var tick = el("text", { x: (x + barW / 2).toFixed(1), y: H - 8, "class": "axis-label", "text-anchor": "middle" }, svg);
        tick.textContent = d.label;
      }
    });
  }

  var buttons = Array.prototype.slice.call(document.querySelectorAll(".window-toggle button"));
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      buttons.forEach(function (other) {
        var on = other === button;
        if (on) other.classList.add("active"); else other.classList.remove("active");
        other.setAttribute("aria-pressed", String(on));
      });
      render(parseInt(button.getAttribute("data-days"), 10) || 14);
    });
  });
  var initial = document.querySelector(".window-toggle button.active");
  render(initial ? parseInt(initial.getAttribute("data-days"), 10) || 14 : 14);
})();
