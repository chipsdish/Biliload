from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main
from app.pipeline import download_media, run_pipeline


class AudioPipelineTest(unittest.TestCase):
    def test_audio_job_returns_download_without_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory)
            audio_path = job_dir / "sample.mp3"
            audio_path.write_bytes(b"audio")

            with (
                patch(
                    "app.pipeline.download_media",
                    return_value=(
                        audio_path,
                        {"id": "BV1ngEB6REmS", "title": "Sample"},
                    ),
                ) as download_media,
                patch("app.pipeline.transcribe_audio") as transcribe_audio,
            ):
                metadata = run_pipeline(
                    job_id="audio-job",
                    url="https://www.bilibili.com/video/BV1ngEB6REmS",
                    job_dir=job_dir,
                    source_language="auto",
                    whisper_model="small",
                    translator="google",
                    cookies_browser=None,
                    task_type="audio",
                    progress=lambda *_: None,
                )

            self.assertEqual(metadata["files"], {"audio": "sample.mp3"})
            self.assertEqual(metadata["media_file"], "sample.mp3")
            self.assertEqual(download_media.call_args.kwargs["media_kind"], "audio")
            transcribe_audio.assert_not_called()

    def test_audio_download_uses_mp3_postprocessor(self) -> None:
        captured_options = {}

        class FakeYoutubeDL:
            def __init__(self, options: dict) -> None:
                captured_options.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def extract_info(self, _url: str, download: bool) -> dict:
                self.assert_download(download)
                output_dir = Path(captured_options["outtmpl"]).parent
                (output_dir / "sample.mp3").write_bytes(b"audio")
                return {"id": "BV1ngEB6REmS", "title": "Sample"}

            @staticmethod
            def assert_download(download: bool) -> None:
                if not download:
                    raise AssertionError("download must be enabled")

        fake_yt_dlp = types.ModuleType("yt_dlp")
        fake_yt_dlp.YoutubeDL = FakeYoutubeDL

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("sys.modules", {"yt_dlp": fake_yt_dlp}),
            patch("app.pipeline.shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            path, _ = download_media(
                url="https://www.bilibili.com/video/BV1ngEB6REmS",
                job_dir=Path(directory),
                cookies_browser=None,
                media_kind="audio",
                progress=lambda *_: None,
            )

        postprocessor = captured_options["postprocessors"][0]
        self.assertEqual(path.name, "sample.mp3")
        self.assertEqual(captured_options["format"], "ba/bestaudio/best")
        self.assertEqual(postprocessor["key"], "FFmpegExtractAudio")
        self.assertEqual(postprocessor["preferredcodec"], "mp3")

    def test_audio_job_does_not_replace_subtitle_page_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            index_path = data_dir / "index.json"
            index_path.write_text(
                '{"by_bvid":{"BV1ngEB6REmS":"subtitle-job"},"jobs":{}}',
                encoding="utf-8",
            )
            audio_job = {
                "id": "audio-job",
                "title": "Sample",
                "bvid": "BV1ngEB6REmS",
                "updated_at": "2026-06-29T00:00:00+00:00",
                "task_type": "audio",
            }

            with (
                patch.object(main, "DATA_DIR", data_dir),
                patch.object(main, "INDEX_PATH", index_path),
                patch.dict(main.jobs, {"audio-job": audio_job}, clear=True),
            ):
                main.write_index("audio-job")
                index_data = main.read_index()

        self.assertEqual(index_data["by_bvid"]["BV1ngEB6REmS"], "subtitle-job")
        self.assertIn("audio-job", index_data["jobs"])


if __name__ == "__main__":
    unittest.main()
