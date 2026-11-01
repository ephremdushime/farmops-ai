(() => {
  var fields = Array.prototype.slice.call(document.querySelectorAll("[data-evidence]"));
  var fill = document.getElementById("intake-meter-fill");
  var label = document.getElementById("intake-meter-label");
  if (!fields.length || !fill || !label) return;
  function filled(field) {
    if (field.type === "file") return field.files && field.files.length > 0;
    return field.value.trim() !== "";
  }
  function update() {
    var done = fields.filter(filled).length;
    var pct = Math.round((done / fields.length) * 100);
    fill.style.width = pct + "%";
    label.textContent = done + " of " + fields.length + " evidence fields";
  }
  fields.forEach(function (field) {
    field.addEventListener("input", update);
    field.addEventListener("change", update);
  });
  update();
})();
