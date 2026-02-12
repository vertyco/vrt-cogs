/* ── LevelUp Settings: Dynamic Table Rows ── */
(function () {
  "use strict";

  /**
   * Reindex all visible rows in a dynamic table so field names are sequential.
   * e.g. prestige_0_level, prestige_1_level, …
   */
  function reindexTable(table) {
    var prefix = table.getAttribute("data-prefix");
    var rows = table.querySelectorAll("tbody tr.lu-dynamic-row");
    for (var i = 0; i < rows.length; i++) {
      var inputs = rows[i].querySelectorAll("input, select");
      for (var j = 0; j < inputs.length; j++) {
        var name = inputs[j].getAttribute("name") || "";
        // Replace prefix_<digits>_ with prefix_<i>_
        var re = new RegExp("^" + prefix + "_\\d+_");
        if (re.test(name)) {
          inputs[j].setAttribute("name", name.replace(re, prefix + "_" + i + "_"));
        }
      }
    }
  }

  /**
   * Add a new row to a dynamic table by cloning the template from the
   * associated <script type="text/html"> tag.
   */
  function addRow(table) {
    var prefix = table.getAttribute("data-prefix");
    var templateScript = document.querySelector(
      'script.lu-row-template[data-table="' + prefix + '"]'
    );
    if (!templateScript) return;

    var tbody = table.querySelector("tbody");
    var existingRows = tbody.querySelectorAll("tr.lu-dynamic-row");
    var newIndex = existingRows.length;

    // Parse template HTML and replace _NEW_ placeholder with index
    var html = templateScript.innerHTML.replace(/_NEW_/g, String(newIndex));

    // Create a temporary container to parse the HTML
    var temp = document.createElement("tbody");
    temp.innerHTML = html;
    var newRow = temp.querySelector("tr");
    if (!newRow) return;

    // Attach remove handler
    var removeBtn = newRow.querySelector(".lu-remove-row");
    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        removeRow(this, table);
      });
    }

    tbody.appendChild(newRow);
  }

  /**
   * Remove a row and reindex the remaining rows.
   */
  function removeRow(btn, table) {
    var row = btn.closest("tr");
    if (row) {
      row.remove();
      reindexTable(table);
    }
  }

  // ── Initialise on DOM ready ──
  document.addEventListener("DOMContentLoaded", function () {
    // Attach click handlers to all Add buttons
    var addButtons = document.querySelectorAll(".lu-add-row");
    for (var i = 0; i < addButtons.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var table = btn.closest(".lu-dynamic-table");
          if (table) addRow(table);
        });
      })(addButtons[i]);
    }

    // Attach click handlers to all existing Remove buttons
    var removeButtons = document.querySelectorAll(".lu-remove-row");
    for (var j = 0; j < removeButtons.length; j++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var table = btn.closest(".lu-dynamic-table");
          if (table) removeRow(btn, table);
        });
      })(removeButtons[j]);
    }
  });
})();
