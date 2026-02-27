(function () {
  function togglePeriodoFinal() {
    const tipo = document.getElementById("id_tipo");
    const rowFim = document.querySelector(".form-row.field-periodo_final");
    if (!tipo || !rowFim) return;

    const v = (tipo.value || "").toLowerCase();

    // ajuste se seus values forem diferentes
    const isAnual = v.includes("anual");
    const isEventual = v.includes("eventual");

    if (isAnual) {
      rowFim.style.display = "none";
    } else if (isEventual) {
      rowFim.style.display = "";
    } else {
      rowFim.style.display = "";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const tipo = document.getElementById("id_tipo");
    if (tipo) tipo.addEventListener("change", togglePeriodoFinal);
    togglePeriodoFinal();
  });
})();