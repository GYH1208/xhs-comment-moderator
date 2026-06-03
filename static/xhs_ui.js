(function () {
  const panel = document.querySelector("[data-job-id]");
  if (!panel) return;

  const statusUrl = panel.dataset.statusUrl;
  const resultUrl = panel.dataset.resultUrl;
  const statusBox = document.getElementById("statusBox");
  const statusText = document.getElementById("statusText");
  const statusMeta = document.getElementById("statusMeta");
  const continueForm = document.getElementById("continueForm");
  const doneActions = document.getElementById("doneActions");
  const steps = Array.from(document.querySelectorAll("[data-step]"));

  function setVisible(element, visible) {
    if (!element) return;
    element.classList.toggle("hidden", !visible);
  }

  function updateSteps(status) {
    const order = ["opening", "waiting", "collecting", "reviewing", "done"];
    const activeIndex = Math.max(0, order.indexOf(status));
    steps.forEach((step, index) => {
      step.classList.toggle("active", index <= activeIndex);
    });
  }

  async function poll() {
    const response = await fetch(statusUrl, { cache: "no-store" });
    const job = await response.json();

    statusText.textContent = job.message || "";
    statusMeta.textContent = job.updated_at || "";
    statusBox.className = "status-box status-" + job.status;
    setVisible(continueForm, job.status === "waiting");
    setVisible(doneActions, job.status === "done");
    updateSteps(job.status);

    if (job.status === "done") {
      window.location.href = resultUrl;
      return;
    }

    if (job.status !== "error") {
      window.setTimeout(poll, 1500);
    }
  }

  poll();
})();
