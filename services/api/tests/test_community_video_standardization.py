import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import community_video
from app.services.community_video import VideoProbe
from app.utils.response import BizError


def probe(
    *,
    duration: float = 12.4,
    width: int = 1280,
    height: int = 720,
    video_codec: str = "h264",
    pixel_format: str = "yuv420p",
    audio_codecs: tuple[str, ...] = ("aac",),
    format_names: tuple[str, ...] = ("mov", "mp4"),
) -> VideoProbe:
    return VideoProbe(
        duration_seconds=duration,
        width=width,
        height=height,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_codecs=audio_codecs,
        format_names=format_names,
    )


class CommunityVideoStandardizationTests(unittest.TestCase):
    def test_compatible_output_requires_cross_platform_mp4_profile(self):
        self.assertTrue(community_video._compatible_mp4(probe()))
        for candidate in (
            probe(video_codec="hevc"),
            probe(pixel_format="yuv444p"),
            probe(audio_codecs=("opus",)),
            probe(format_names=("matroska", "webm")),
            probe(width=1281),
            probe(width=1279),
            probe(height=719),
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(community_video._compatible_mp4(candidate))

    def test_probe_reads_one_video_stream_and_audio_codec(self):
        payload = {
            "format": {"duration": "19.6", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [
                {
                    "codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                    "width": 720, "height": 1280,
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b"")
        with patch.object(community_video, "_tool", return_value="ffprobe"), patch.object(
            community_video, "_run", return_value=completed,
        ):
            result = community_video._probe(Path("ignored.mp4"))
        self.assertEqual(result.duration_seconds, 19.6)
        self.assertEqual(result.audio_codecs, ("aac",))
        self.assertEqual(result.format_names, ("mov", "mp4", "m4a", "3gp", "3g2", "mj2"))

    def test_standardize_always_transcodes_and_returns_verified_output_duration(self):
        source_probe = probe(duration=11.2, video_codec="vp9", format_names=("webm",))
        output_probe = probe(duration=11.0)
        probes = iter((source_probe, output_probe))

        def fake_transcode(source: Path, destination: Path, metadata: VideoProbe, max_bytes: int):
            self.assertTrue(source.is_file())
            self.assertEqual(metadata, source_probe)
            destination.write_bytes(b"standardized-mp4")

        with patch.object(community_video, "_probe", side_effect=lambda path: next(probes)), patch.object(
            community_video, "_transcode", side_effect=fake_transcode,
        ) as transcode:
            result = community_video.standardize_community_video(b"input-webm", "webm", 1024)

        self.assertEqual(result.content, b"standardized-mp4")
        self.assertEqual(result.duration_seconds, 11)
        self.assertEqual(transcode.call_count, 1)

    def test_overlong_video_is_rejected_before_transcoding(self):
        with patch.object(community_video, "_probe", return_value=probe(duration=301)), patch.object(
            community_video, "_transcode",
        ) as transcode:
            with self.assertRaises(BizError) as raised:
                community_video.standardize_community_video(b"input", "mp4", 1024)
        self.assertIn("5 分钟", raised.exception.msg)
        transcode.assert_not_called()

    def test_missing_ffmpeg_dependency_fails_closed(self):
        with patch.object(community_video.shutil, "which", return_value=None):
            with self.assertRaises(BizError) as raised:
                community_video._tool("ffmpeg")
        self.assertEqual(raised.exception.status_code, 503)

    def test_standardized_duration_rejects_nonstandard_server_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.mov"
            path.write_bytes(b"legacy")
            with patch.object(community_video, "_probe", return_value=probe(video_codec="hevc")):
                with self.assertRaises(BizError) as raised:
                    community_video.standardized_video_duration(path)
        self.assertIn("兼容", raised.exception.msg)


if __name__ == "__main__":
    unittest.main()
