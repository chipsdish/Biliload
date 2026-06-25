(() => {
  const API_BASE = "http://127.0.0.1:8787";
  let currentUrl = "";
  let cues = [];
  let activeCue = null;
  let overlay = null;
  let pill = null;

  function ensureOverlay() {
    const video = document.querySelector("video");
    if (!video) return null;

    const container =
      video.closest(".bpx-player-video-area") ||
      video.closest(".bpx-player-video-wrap") ||
      video.parentElement;

    if (!container) return null;

    if (getComputedStyle(container).position === "static") {
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

    if (!pill) {
      pill = document.createElement("div");
      pill.className = "biliload-pill";
      pill.textContent = "Biliload";
      document.body.append(pill);
    }

    return overlay;
  }

  async function loadSubtitleForPage() {
    currentUrl = location.href;
    cues = [];
    activeCue = null;
    updatePill("Biliload: 查询");

    try {
      const response = await fetch(
        `${API_BASE}/api/page-subtitle?url=${encodeURIComponent(currentUrl)}`,
      );
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (!data.found) {
        updatePill("Biliload: 无字幕");
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
    ensureOverlay();
    if (pill) pill.textContent = text;
  }

  function tick() {
    if (location.href !== currentUrl) {
      loadSubtitleForPage();
    }
    updateCue();
  }

  ensureOverlay();
  loadSubtitleForPage();
  window.setInterval(tick, 250);
})();

