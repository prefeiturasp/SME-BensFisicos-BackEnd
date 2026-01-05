(function () {
  function togglePeriodoFinal() {
    var tipo = document.getElementById("id_tipo");
    var rowFim = document.querySelector(".form-row.field-periodo_final");
    if (!tipo || !rowFim) return;

    var v = (tipo.value || "").toLowerCase();

    // ajuste se seus values forem diferentes
    var isAnual = v.includes("anual");
    var isEventual = v.includes("eventual");

    if (isAnual) {
      rowFim.style.display = "none";
    } else if (isEventual) {
      rowFim.style.display = "";
    } else {
      rowFim.style.display = "";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var tipo = document.getElementById("id_tipo");
    if (tipo) tipo.addEventListener("change", togglePeriodoFinal);
    togglePeriodoFinal();
  });
})();