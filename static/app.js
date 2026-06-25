const form = document.querySelector("#job-form");
const submitButton = document.querySelector("#submit-button");
const refreshButton = document.querySelector("#refresh-button");
const jobsEl = document.querySelector("#jobs");
const template = document.querySelector("#job-template");

let pollTimer = null;

const fileLabels = {
  bilingual_srt: "双语 SRT",
  source_srt: "原文 SRT",
  zh_srt: "中文 SRT",
  transcript: "转写 TXT",
  json: "JSON",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;

  const payload = {
    url: document.querySelector("#url").value.trim(),
    source_language: document.querySelector("#source-language").value,
    whisper_model: document.querySelector("#whisper-model").value,
    translator: document.querySelector("#translator").value,
    cookies_browser: document.querySelector("#cookies-browser").value,
    download_video: document.querySelector("#download-video").checked,
  };

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text);
    }
    form.reset();
    document.querySelector("#download-video").checked = true;
    await loadJobs();
    startPolling();
  } catch (error) {
    window.alert(`创建任务失败：${error.message}`);
  } finally {
    submitButton.disabled = false;
  }
});

refreshButton.addEventListener("click", loadJobs);

async function loadJobs() {
  const response = await fetch("/api/jobs");
  if (!response.ok) {
    throw new Error("Failed to load jobs");
  }
  const jobs = await response.json();
  renderJobs(jobs);
  if (jobs.some((job) => !["completed", "failed"].includes(job.status))) {
    startPolling();
  } else {
    stopPolling();
  }
}

function renderJobs(jobs) {
  jobsEl.innerHTML = "";

  if (jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "暂无任务";
    jobsEl.append(empty);
    return;
  }

  for (const job of jobs) {
    const card = template.content.firstElementChild.cloneNode(true);
    card.querySelector(".job-title").textContent =
      job.title || job.url || `任务 ${job.id}`;
    card.querySelector(".job-meta").textContent = [
      job.bvid,
      job.detected_language ? `识别语言 ${job.detected_language}` : null,
      `模型 ${job.whisper_model}`,
      `任务 ${job.id}`,
    ]
      .filter(Boolean)
      .join(" · ");

    const status = card.querySelector(".status");
    status.textContent = statusText(job.status);
    status.classList.toggle("failed", job.status === "failed");

    card.querySelector(".progress-bar").style.width = `${Math.round(
      (job.progress || 0) * 100,
    )}%`;
    card.querySelector(".message").textContent =
      job.error || job.message || "处理中";

    const links = card.querySelector(".file-links");
    if (job.status === "completed") {
      for (const [kind, label] of Object.entries(fileLabels)) {
        if (job.files?.[kind]) {
          const link = document.createElement("a");
          link.href = `/api/jobs/${job.id}/files/${kind}`;
          link.textContent = label;
          link.target = "_blank";
          links.append(link);
        }
      }
      if (job.url) {
        const open = document.createElement("a");
        open.href = job.url;
        open.textContent = "打开B站";
        open.target = "_blank";
        open.rel = "noreferrer";
        links.append(open);
      }
    }

    jobsEl.append(card);
  }
}

function statusText(status) {
  const map = {
    queued: "排队",
    downloading: "下载",
    extracting_audio: "抽音频",
    transcribing: "识别",
    translating: "翻译",
    writing_files: "写文件",
    completed: "完成",
    failed: "失败",
  };
  return map[status] || status;
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = window.setInterval(() => {
    loadJobs().catch(() => {});
  }, 2000);
}

function stopPolling() {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = null;
}

loadJobs().catch((error) => {
  jobsEl.innerHTML = `<div class="empty">加载失败：${error.message}</div>`;
});

