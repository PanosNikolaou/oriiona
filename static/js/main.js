document.addEventListener("DOMContentLoaded", () => {
  const loader = document.getElementById("page-loader");
  if (loader) loader.style.display = "none";

  const modal = document.getElementById("importExportModal");
  const modalClose = document.getElementById("modalClose");
  const importExportBtn = document.getElementById("importExportBtn");
  const applyBtn = document.getElementById("applyImport");
  const sidebar = document.getElementById("sidebar");
  const menuToggle = document.getElementById("menu-toggle");
  let importedCoords = [];

  // Sidebar toggle (mobile)
  if (menuToggle) {
    menuToggle.addEventListener("click", () => {
      sidebar.classList.toggle("active");
    });
  }

  // Modal handlers
  if (importExportBtn) {
    importExportBtn.addEventListener("click", (e) => {
      e.preventDefault();
      modal.style.display = "flex";
    });
  }

  if (modalClose) {
    modalClose.addEventListener("click", () => {
      modal.style.display = "none";
    });
  }

  window.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.style.display = "none";
    }
  });

  // Toast helper
  function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.style.borderColor = type === "error" ? "var(--danger)" : "var(--primary)";
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }

  // Import handler
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      importedCoords = [];
      const csvFile = document.getElementById("uploadCSV").files[0];
      const gpxFile = document.getElementById("uploadGPX").files[0];

      if (!csvFile && !gpxFile) {
        showToast("⚠️ Please select at least one file (CSV or GPX).", "error");
        return;
      }

      if (csvFile) {
        const reader = new FileReader();
        reader.onload = function (e) {
          try {
            const lines = e.target.result.split("\n");
            for (let line of lines) {
              const parts = line.trim().split(",");
              if (parts.length === 3) {
                const lat = parseFloat(parts[1]);
                const lng = parseFloat(parts[2]);
                if (!isNaN(lat) && !isNaN(lng)) {
                  importedCoords.push([lat, lng]);
                }
              }
            }
            if (importedCoords.length) {
              drawRoute(importedCoords, "orange");
              showToast("✅ CSV imported and drawn.");
            } else {
              showToast("⚠️ No valid coordinates in CSV.", "error");
            }
          } catch {
            showToast("❌ Failed to parse CSV.", "error");
          }
        };
        reader.readAsText(csvFile);
      }

      if (gpxFile) {
        const reader = new FileReader();
        reader.onload = function (e) {
          try {
            const parser = new DOMParser();
            const xml = parser.parseFromString(e.target.result, "application/xml");
            const trkpts = xml.getElementsByTagName("trkpt");
            for (let i = 0; i < trkpts.length; i++) {
              const lat = parseFloat(trkpts[i].getAttribute("lat"));
              const lon = parseFloat(trkpts[i].getAttribute("lon"));
              if (!isNaN(lat) && !isNaN(lon)) {
                importedCoords.push([lat, lon]);
              }
            }
            if (importedCoords.length) {
              drawRoute(importedCoords, "purple");
              showToast("✅ GPX imported and drawn.");
            } else {
              showToast("⚠️ No valid coordinates in GPX.", "error");
            }
          } catch {
            showToast("❌ Failed to parse GPX.", "error");
          }
        };
        reader.readAsText(gpxFile);
      }

      modal.style.display = "none";
    });
  }
});
