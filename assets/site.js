/* Progressive enhancement for sandy-sachin7.github.io */
(function () {
  var root = document.documentElement;
  var storageKey = "sachin-theme";

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      var isDark = theme === "dark";
      btn.setAttribute("aria-pressed", String(isDark));
      btn.textContent = isDark ? "Paper" : "Ink";
      btn.setAttribute(
        "aria-label",
        isDark ? "Switch to Archival Paper light theme" : "Switch to Lab Bench dark theme"
      );
    }
  }

  var saved = null;
  try {
    saved = localStorage.getItem(storageKey);
  } catch (_) {}
  var initial =
    saved === "dark" || saved === "light"
      ? saved
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  applyTheme(initial);

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(storageKey, next);
      } catch (_) {}
      applyTheme(next);
    });
  }

  /* Writing index tag filter with empty-state support */
  var filterButtons = document.querySelectorAll("[data-filter]");
  var essayRows = document.querySelectorAll("[data-tags]");
  var emptyState = document.getElementById("filter-empty");
  var resetBtn = document.getElementById("filter-reset");

  function setFilter(tag) {
    var visible = 0;
    filterButtons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-filter") === tag));
    });
    essayRows.forEach(function (row) {
      var tags = (row.getAttribute("data-tags") || "").split(",");
      var show = tag === "all" || tags.indexOf(tag) !== -1;
      row.classList.toggle("hidden", !show);
      if (show) visible += 1;
    });
    if (emptyState) {
      emptyState.classList.toggle("hidden", visible > 0);
    }
  }

  filterButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setFilter(btn.getAttribute("data-filter") || "all");
    });
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      setFilter("all");
    });
  }

  /* Copy buttons for code blocks */
  document.querySelectorAll(".code-block").forEach(function (block) {
    var btn = block.querySelector(".copy-btn");
    var code = block.querySelector("pre code");
    if (!btn || !code) return;
    btn.addEventListener("click", function () {
      var text = code.textContent || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          btn.textContent = "Copied";
          setTimeout(function () {
            btn.textContent = "Copy";
          }, 1600);
        });
      }
    });
  });

  /* Reading progress hairline on article pages */
  var bar = document.getElementById("reading-progress");
  if (bar) {
    window.addEventListener(
      "scroll",
      function () {
        var doc = document.documentElement;
        var max = doc.scrollHeight - doc.clientHeight;
        var pct = max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0;
        bar.style.width = pct.toFixed(1) + "%";
      },
      { passive: true }
    );
  }

  /* Interactive benchmark view switcher (used in deltalens essay & site) */
  document.querySelectorAll("[data-bench-widget]").forEach(function (widget) {
    var tabs = widget.querySelectorAll("[data-bench-mode]");
    var panels = widget.querySelectorAll("[data-bench-panel]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var mode = tab.getAttribute("data-bench-mode");
        tabs.forEach(function (t) {
          t.setAttribute("aria-pressed", String(t === tab));
        });
        panels.forEach(function (p) {
          p.classList.toggle("hidden", p.getAttribute("data-bench-panel") !== mode);
        });
      });
    });
  });
})();
