from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .subtitles import Cue, cue_to_json, cues_to_srt, cues_to_text
from .translator import translate_lines

ProgressCallback = Callable[[str, float, str], None]

BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")

LANGUAGE_MAP = {
    "auto": None,
    "cantonese": "zh",
    "yue": "zh",
    "zh": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
}


class PipelineError(RuntimeError):
    pass


def extract_bvid(value: str | None) -> str | None:
    if not value:
        return None
    match = BVID_RE.search(value)
    return match.group(1) if match else None


def normalize_bilibili_input(value: str) -> tuple[str, str | None]:
    raw = value.strip()
    if not raw:
        raise PipelineError("请输入 BV 号或 B 站链接")

    bvid = extract_bvid(raw)
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}", bvid

    if raw.startswith(("http://", "https://")):
        return raw, None

    if raw.startswith(("www.bilibili.com/", "bilibili.com/", "b23.tv/")):
        return f"https://{raw}", None

    raise PipelineError("没有识别到 BV 号，请输入 BV 号或 B 站链接")


def run_pipeline(
    *,
    job_id: str,
    url: str,
    job_dir: Path,
    source_language: str,
    whisper_model: str,
    translator: str,
    cookies_browser: str | None,
    task_type: str,
    progress: ProgressCallback,
) -> dict:
    job_dir.mkdir(parents=True, exist_ok=True)

    progress("downloading", 0.05, "读取视频信息并下载媒体")
    media_path, info = download_media(
        url=url,
        job_dir=job_dir,
        cookies_browser=cookies_browser,
        media_kind=task_type,
        progress=progress,
    )

    title = clean_title(info.get("title") or "untitled")
    bvid = extract_bvid(info.get("id")) or extract_bvid(url)

    if task_type in {"video", "audio"}:
        files = {task_type: media_path.name}
        metadata = {
            "job_id": job_id,
            "url": url,
            "title": title,
            "bvid": bvid,
            "detected_language": None,
            "source_language": source_language,
            "whisper_model": whisper_model,
            "translator": translator,
            "task_type": task_type,
            "media_file": str(media_path.name),
            "files": files,
        }
        (job_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        progress(
            "completed",
            1.0,
            "视频下载完成" if task_type == "video" else "音频下载完成",
        )
        return metadata

    progress("extracting_audio", 0.30, "抽取 16k 单声道音频")
    audio_path = job_dir / "audio_16k.wav"
    extract_audio(media_path, audio_path)

    progress("transcribing", 0.40, f"Whisper {whisper_model} 正在识别原语言")
    cues, detected_language = transcribe_audio(
        audio_path=audio_path,
        source_language=source_language,
        whisper_model=whisper_model,
    )

    progress("translating", 0.75, "翻译为中文")
    source_lines = [cue.source for cue in cues]
    target_lines = translate_lines(source_lines, provider=translator, target_language="zh-CN")
    bilingual_cues = [
        Cue(start=cue.start, end=cue.end, source=cue.source, target=target)
        for cue, target in zip(cues, target_lines, strict=False)
    ]

    progress("writing_files", 0.90, "写入字幕和元数据")
    files = write_outputs(job_dir, bilingual_cues)

    metadata = {
        "job_id": job_id,
        "url": url,
        "title": title,
        "bvid": bvid,
        "detected_language": detected_language,
        "source_language": source_language,
        "whisper_model": whisper_model,
        "translator": translator,
        "task_type": task_type,
        "media_file": str(media_path.name),
        "files": files,
    }
    (job_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    progress("completed", 1.0, "完成")
    return metadata


def download_media(
    *,
    url: str,
    job_dir: Path,
    cookies_browser: str | None,
    media_kind: str,
    progress: ProgressCallback,
) -> tuple[Path, dict]:
    try:
        from yt_dlp import YoutubeDL
    except Exception as exc:  # pragma: no cover - dependency guard
        raise PipelineError("yt-dlp is not installed") from exc

    outtmpl = str(job_dir / "%(title).80s [%(id)s].%(ext)s")
    ffmpeg_location = shutil.which("ffmpeg")
    options: dict = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 5,
        "fragment_retries": 5,
        "quiet": True,
        "no_warnings": False,
        "progress_hooks": [lambda event: download_hook(event, progress)],
    }

    if ffmpeg_location:
        options["ffmpeg_location"] = str(Path(ffmpeg_location).parent)

    if cookies_browser:
        options["cookiesfrombrowser"] = (cookies_browser,)

    if media_kind == "video":
        options.update(
            {
                "format": "bestvideo*+bestaudio/best",
                "merge_output_format": "mp4",
            }
        )
    else:
        options.update({"format": "ba/bestaudio/best"})
        if media_kind == "audio":
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ]

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    candidates = [
        path
        for path in job_dir.iterdir()
        if path.is_file()
        and path.suffix.lower()
        in {".mp4", ".mkv", ".webm", ".flv", ".m4a", ".mp3", ".aac", ".opus"}
    ]
    if not candidates:
        raise PipelineError("下载完成但没有找到媒体文件")

    media_path = max(candidates, key=lambda path: path.stat().st_size)
    return media_path, info


def download_hook(event: dict, progress: ProgressCallback) -> None:
    if event.get("status") == "downloading":
        total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
        downloaded = event.get("downloaded_bytes") or 0
        fraction = downloaded / total if total else 0
        progress("downloading", 0.05 + min(fraction, 1) * 0.22, "正在下载媒体")
    elif event.get("status") == "finished":
        progress("downloading", 0.28, "下载完成，准备处理")


def extract_audio(media_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-nostats",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError(f"ffmpeg 抽取音频失败：{completed.stderr[-1000:]}")


def transcribe_audio(
    *,
    audio_path: Path,
    source_language: str,
    whisper_model: str,
) -> tuple[list[Cue], str | None]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - dependency guard
        raise PipelineError("faster-whisper is not installed") from exc

    language = LANGUAGE_MAP.get(source_language, source_language or None)
    model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        task="transcribe",
        beam_size=5,
        no_speech_threshold=1.0,
        log_prob_threshold=-5.0,
        compression_ratio_threshold=10.0,
        condition_on_previous_text=False,
    )

    cues = [
        Cue(start=segment.start, end=segment.end, source=segment.text.strip())
        for segment in segments
        if segment.text.strip()
    ]
    if not cues:
        raise PipelineError("语音识别没有得到任何字幕片段")

    return cues, getattr(info, "language", None)


def write_outputs(job_dir: Path, cues: list[Cue]) -> dict[str, str]:
    files = {
        "json": "subtitles.json",
        "source_srt": "subtitles_source.srt",
        "zh_srt": "subtitles_zh-CN.srt",
        "bilingual_srt": "subtitles_bilingual.srt",
        "transcript": "transcript.txt",
    }
    (job_dir / files["json"]).write_text(
        json.dumps([cue_to_json(cue) for cue in cues], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (job_dir / files["source_srt"]).write_text(
        cues_to_srt(cues, "source"),
        encoding="utf-8",
    )
    (job_dir / files["zh_srt"]).write_text(
        cues_to_srt(cues, "target"),
        encoding="utf-8",
    )
    (job_dir / files["bilingual_srt"]).write_text(
        cues_to_srt(cues, "bilingual"),
        encoding="utf-8",
    )
    (job_dir / files["transcript"]).write_text(cues_to_text(cues), encoding="utf-8")
    return files


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()
