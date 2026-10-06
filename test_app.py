import unittest
import shutil
import tempfile
from pathlib import Path

from app import DownloadHistory, YtDlpDesktop


class AppChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = YtDlpDesktop()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def test_playlist_index_ranges(self):
        self.assertEqual(YtDlpDesktop._parse_indices("2,7,10-12"), [2, 7, 10, 11, 12])
        with self.assertRaises(ValueError):
            YtDlpDesktop._parse_indices("0,3")

    def test_video_format_and_height_cap(self):
        fmt, postprocessors = self.app._formats({
            "kind": "Video", "container": "mp4", "quality": "720p",
        })
        self.assertEqual(fmt, "bestvideo[height<=720]+bestaudio/best[height<=720]")
        self.assertIsNone(postprocessors)

    def test_audio_format_and_quality(self):
        fmt, postprocessors = self.app._formats({
            "kind": "Audio", "container": "mp3", "quality": "128 kbps",
        })
        self.assertEqual(fmt, "bestaudio/best")
        self.assertEqual(postprocessors[0]["preferredcodec"], "mp3")
        self.assertEqual(postprocessors[0]["preferredquality"], "128")

    def test_live_and_playlist_options(self):
        options = self.app._download_opts(lambda _data: None, {
            "kind": "Video", "container": "mkv", "quality": "Best available",
            "live_from_start": True, "output_dir": "C:/dlp", "cookies": "",
            "ffmpeg": "", "playlist_items": "1,3-4",
        })
        self.assertTrue(options["live_from_start"])
        self.assertEqual(options["playlist_items"], "1,3-4")
        self.assertEqual(options["merge_output_format"], "mkv")

    def test_cookie_file_is_defaulted_from_app_folder(self):
        self.assertEqual(self.app.cookies.get(), r"C:\dlp\cookies.txt")

    def test_node_runtime_is_enabled_when_available(self):
        node = shutil.which("node")
        options = self.app._yt_options()
        if node:
            self.assertEqual(options["js_runtimes"], {"node": {"path": node}})

    def test_liked_preview_renders_all_loaded_entries(self):
        entries = [{"title": f"Liked video {index}"} for index in range(1, 152)]
        self.app.events.put(("liked", entries))
        self.app._drain_events()
        preview = self.app.liked_preview.get("1.0", "end")
        self.assertIn("151. Liked video 151", preview)
        self.assertNotIn("and 121 more", preview)

    def test_batch_and_download_counters_update(self):
        self.app.batch_total = 3
        self.app.batch_done = 0
        self.app.downloaded_count = 0
        self.app.events.put(("job_done", True, "downloaded"))
        self.app._drain_events()
        self.assertEqual(self.app.downloaded_metric.cget("text"), "1")
        self.assertEqual(self.app.batch_progress_label.cget("text"), "Done 1 / 3")

    def test_skip_current_sets_skip_signal(self):
        class RunningWorker:
            @staticmethod
            def is_alive():
                return True

        self.app.worker = RunningWorker()
        self.app.skip_current_event.clear()
        self.app.skip_current()
        self.assertTrue(self.app.skip_current_event.is_set())
        self.app.skip_current_event.clear()

    def test_download_history_persists_details_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            history = DownloadHistory(Path(directory) / "history.sqlite3")
            row_id = history.add(
                {"id": "abc123", "title": "Example", "width": 640, "height": 360,
                 "http_headers": {"Cookie": "private"}, "url": "https://signed.example/?token=private",
                 "duration": 42},
                {"kind": "Audio", "container": "mp3", "quality": "128 kbps"},
                output_path=None,
            )
            row = history.get(row_id)
            self.assertEqual(history.count(), 1)
            self.assertEqual(row["quality"], "128 kbps")
            self.assertEqual(row["resolution"], "640x360")
            self.assertNotIn("http_headers", row["metadata_json"])
            self.assertNotIn('"url"', row["metadata_json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
