// Admin analytics page: fetches aggregated counts from /admin/api/analytics,
// filtered by the form above, and (re)draws four Chart.js charts. All data
// comes from the server - nothing here is hardcoded.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("analyticsFilters");
  if (!form) return;

  const emptyState = document.getElementById("analyticsEmptyState");
  const totalLabel = document.getElementById("totalLabel");

  const palette = ["#1b4332", "#2d6a4f", "#40916c", "#52b788", "#74c69d", "#95d5b2", "#b7e4c7"];

  let categoryChart, statusChart, timelineChart, resolvedChart;
  const downloadLink = document.getElementById("downloadSummaryPdf");
  const downloadBaseHref = downloadLink ? downloadLink.getAttribute("href") : "";

  function currentParams() {
    const params = new URLSearchParams();
    const category = document.getElementById("filterCategory").value;
    const from = document.getElementById("filterFrom").value;
    const to = document.getElementById("filterTo").value;
    if (category) params.set("category", category);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    return params;
  }

  function syncDownloadLink() {
    if (!downloadLink) return;
    const query = currentParams().toString();
    downloadLink.href = query ? `${downloadBaseHref}?${query}` : downloadBaseHref;
  }

  function buildOrUpdate(chart, ctx, config) {
    if (chart) {
      chart.data = config.data;
      chart.update();
      return chart;
    }
    return new Chart(ctx, config);
  }

  async function loadAnalytics() {
    syncDownloadLink();

    let data;
    try {
      const resp = await fetch(`/admin/api/analytics?${currentParams().toString()}`);
      data = await resp.json();
    } catch (err) {
      totalLabel.textContent = "Could not load analytics right now.";
      return;
    }

    totalLabel.textContent = `${data.total} complaint${data.total === 1 ? "" : "s"} in this range`;
    emptyState.classList.toggle("d-none", data.total !== 0);

    categoryChart = buildOrUpdate(categoryChart, document.getElementById("categoryChart"), {
      type: "bar",
      data: {
        labels: data.by_category.labels,
        datasets: [{
          label: "Complaints",
          data: data.by_category.values,
          backgroundColor: palette,
        }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });

    statusChart = buildOrUpdate(statusChart, document.getElementById("statusChart"), {
      type: "doughnut",
      data: {
        labels: data.by_status.labels,
        datasets: [{ data: data.by_status.values, backgroundColor: palette }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });

    timelineChart = buildOrUpdate(timelineChart, document.getElementById("timelineChart"), {
      type: "line",
      data: {
        labels: data.timeline.labels,
        datasets: [{
          label: "Submitted",
          data: data.timeline.values,
          borderColor: "#2d6a4f",
          backgroundColor: "rgba(45, 106, 79, 0.15)",
          tension: 0.25,
          fill: true,
        }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });

    resolvedChart = buildOrUpdate(resolvedChart, document.getElementById("resolvedChart"), {
      type: "pie",
      data: {
        labels: ["Resolved", "Unresolved"],
        datasets: [{
          data: [data.resolved_vs_unresolved.resolved, data.resolved_vs_unresolved.unresolved],
          backgroundColor: ["#2d6a4f", "#d8d8d8"],
        }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    loadAnalytics();
  });

  document.getElementById("clearFilters").addEventListener("click", () => {
    form.reset();
    loadAnalytics();
  });

  loadAnalytics();
});