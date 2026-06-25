(() => {
  const API_BASE = "http://127.0.0.1:8787";
  let currentUrl = "";
  let cues = [];
  let activeCue = null;
  let overlay = null;
  let pill = null;
  let lastLookupAt = 0;

  function ensureOverlay() {
    ensurePill();
    const video = document.querySelector("video");
    const container =
      video?.closest(".bpx-player-video-area") ||
      video?.closest(".bpx-player-video-wrap") ||
      video?.closest("#bilibili-player") ||
      video?.parentElement ||
      document.querySelector("#bilibili-player") ||
      document.body;

    if (!container) return null;

    const useFixed = container === document.body;
    if (!useFixed && getComputedStyle(container).position === "static") {
      container.style.position = "relative";
    }

    if (!overlay || !container.contains(overlay)) {
      overlay = document.createElement("div");
      overlay.className = "biliload-overlay";
      overlay.innerHTML = `
        <div class="biliload-source"></div>
        <div class="biliload-target"></div>
      `;
      container.append(overlay);
    }
    overlay.classList.toggle("biliload-fixed", useFixed);

    return overlay;
  }

  function ensurePill() {
    if (pill) return pill;
    pill = document.createElement("div");
    pill.className = "biliload-pill";
    pill.textContent = "Biliload";
    document.body.append(pill);
    return pill;
  }

  async function loadSubtitleForPage() {
    currentUrl = location.href;
    lastLookupAt = Date.now();
    cues = [];
    activeCue = null;
    updatePill("Biliload: 查询");

    try {
      const params = new URLSearchParams({ url: currentUrl });
      const jobId = new URL(location.href).searchParams.get("biliload_job");
      if (jobId) params.set("job_id", jobId);

      const response = await fetch(`${API_BASE}/api/page-subtitle?${params}`);
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (!data.found) {
        updatePill(`Biliload: ${data.reason || "无字幕"}`);
        clearCue();
        return;
      }
      cues = data.cues || [];
      updatePill(`Biliload: ${cues.length} 条`);
    } catch (error) {
      updatePill("Biliload: 未连接");
      clearCue();
    }
  }

  function updateCue() {
    const video = document.querySelector("video");
    const node = ensureOverlay();
    if (!video || !node || cues.length === 0) return;

    const time = video.currentTime;
    const cue =
      activeCue && time >= activeCue.start && time <= activeCue.end
        ? activeCue
        : cues.find((item) => time >= item.start && time <= item.end);

    if (!cue) {
      activeCue = null;
      clearCue();
      return;
    }

    activeCue = cue;
    node.classList.add("biliload-has-cue");
    node.querySelector(".biliload-source").textContent = cue.source || "";
    node.querySelector(".biliload-target").textContent = cue.target || "";
  }

  function clearCue() {
    if (!overlay) return;
    overlay.classList.remove("biliload-has-cue");
    overlay.querySelector(".biliload-source").textContent = "";
    overlay.querySelector(".biliload-target").textContent = "";
  }

  function updatePill(text) {
    ensurePill();
    if (pill) pill.textContent = text;
  }

  function tick() {
    if (location.href !== currentUrl) {
      loadSubtitleForPage();
    }
    if (cues.length === 0 && Date.now() - lastLookupAt > 5000) {
      loadSubtitleForPage();
    }
    updateCue();
  }

  ensureOverlay();
  loadSubtitleForPage();
  window.setInterval(tick, 250);
})();
