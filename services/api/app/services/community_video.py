from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.utils.response import BizError


@dataclass(frozen=True)
class VideoProbe:
    duration_seconds: float
    width: int
    height: int
    video_codec: str
    pixel_format: str
    audio_codecs: tuple[str, ...]
    format_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardizedCommunityVideo:
    content: bytes
    duration_seconds: int


_TRANSCODE_GATE = threading.BoundedSemaphore(
    max(1, int(settings.COMMUNITY_VIDEO_TRANSCODE_CONCURRENCY))
)


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise BizError("视频处理服务暂不可用，请稍后重试", status_code=503)
    return executable


def _run(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BizError("视频处理超时，请缩短视频后重试") from exc
    except OSError as exc:
        raise BizError("视频处理服务暂不可用，请稍后重试", status_code=503) from exc


def _probe(path: Path, timeout_seconds: int = 20) -> VideoProbe:
    result = _run([
        _tool("ffprobe"),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ], timeout_seconds)
    if result.returncode != 0 or len(result.stdout) > 1_000_000:
        raise BizError("视频文件已损坏或编码无法识别")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
        streams = payload.get("streams") if isinstance(payload, dict) else None
        metadata = payload.get("format") if isinstance(payload, dict) else None
        if not isinstance(streams, list) or not isinstance(metadata, dict):
            raise ValueError
        if not all(isinstance(item, dict) for item in streams):
            raise ValueError
        videos = [item for item in streams if item.get("codec_type") == "video"]
        audios = [item for item in streams if item.get("codec_type") == "audio"]
        if len(videos) != 1:
            raise ValueError
        video = videos[0]
        duration_values = [metadata.get("duration"), video.get("duration")]
        duration = next(
            (float(value) for value in duration_values if value not in (None, "N/A")),
            0.0,
        )
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        format_names = tuple(
            item.strip().lower()
            for item in str(metadata.get("format_name") or "").split(",")
            if item.strip()
        )
    except (UnicodeDecodeError, TypeError, ValueError, OverflowError, StopIteration) as exc:
        raise BizError("视频文件已损坏或编码无法识别") from exc
    if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
        raise BizError("视频文件已损坏或编码无法识别")
    if width > 7680 or height > 4320 or width * height > 33_177_600:
        raise BizError("视频分辨率过高，请压缩后重试")
    return VideoProbe(
        duration_seconds=duration,
        width=width,
        height=height,
        video_codec=str(video.get("codec_name") or "").lower(),
        pixel_format=str(video.get("pix_fmt") or "").lower(),
        audio_codecs=tuple(str(item.get("codec_name") or "").lower() for item in audios),
        format_names=format_names,
    )


def _compatible_mp4(probe: VideoProbe) -> bool:
    return (
        probe.video_codec == "h264"
        and probe.pixel_format == "yuv420p"
        and all(codec == "aac" for codec in probe.audio_codecs)
        and bool({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}.intersection(probe.format_names))
        and probe.width <= 1280
        and probe.width % 2 == 0
        and probe.height % 2 == 0
    )


def _video_bitrate(duration_seconds: float, has_audio: bool, max_bytes: int) -> int:
    audio_bitrate = 96_000 if has_audio else 0
    available = (max_bytes * 8 * 0.88 / duration_seconds) - audio_bitrate
    if available < 320_000:
        raise BizError("视频时长和文件大小不适合转换，请缩短视频后重试")
    return min(2_500_000, int(available))


def _transcode(source: Path, destination: Path, probe: VideoProbe, max_bytes: int) -> None:
    video_bitrate = _video_bitrate(probe.duration_seconds, bool(probe.audio_codecs), max_bytes)
    result = _run([
        _tool("ffmpeg"),
        "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-sn", "-dn", "-map_metadata", "-1",
        # Keep both dimensions even for yuv420p while preserving aspect ratio.
        "-vf", "scale=trunc(min(1280\\,iw)/2)*2:-2",
        "-r", "30",
        "-c:v", "libx264", "-profile:v", "main", "-level:v", "4.0",
        "-tag:v", "avc1", "-pix_fmt", "yuv420p",
        "-b:v", str(video_bitrate),
        "-maxrate", str(int(video_bitrate * 1.25)),
        "-bufsize", str(video_bitrate * 2),
        "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "48000",
        "-movflags", "+faststart",
        "-y", str(destination),
    ], int(settings.COMMUNITY_VIDEO_TRANSCODE_TIMEOUT_SECONDS))
    if result.returncode != 0 or not destination.is_file():
        raise BizError("视频转换失败，请更换视频后重试")


def _validate_duration(probe: VideoProbe) -> None:
    maximum = max(1, int(settings.COMMUNITY_VIDEO_MAX_DURATION_SECONDS))
    if probe.duration_seconds > maximum + 0.5:
        minutes = maximum // 60
        raise BizError(f"社区视频不能超过 {minutes} 分钟")


def standardize_community_video(
    content: bytes,
    input_extension: str,
    max_bytes: int,
) -> StandardizedCommunityVideo:
    if not _TRANSCODE_GATE.acquire(timeout=1):
        raise BizError("视频处理繁忙，请稍后重试", status_code=503)
    try:
        with tempfile.TemporaryDirectory(prefix="ztw-community-video-") as directory:
            root = Path(directory)
            source = root / f"source.{input_extension}"
            destination = root / "standardized.mp4"
            source.write_bytes(content)
            input_probe = _probe(source)
            _validate_duration(input_probe)
            _transcode(source, destination, input_probe, max_bytes)
            output_probe = _probe(destination)
            _validate_duration(output_probe)
            if not _compatible_mp4(output_probe):
                raise BizError("视频转换结果不兼容，请更换视频后重试")
            normalized = destination.read_bytes()
            if not normalized or len(normalized) > max_bytes:
                raise BizError("转换后的视频超过 20MB，请缩短视频后重试")
            return StandardizedCommunityVideo(
                content=normalized,
                duration_seconds=max(1, int(round(output_probe.duration_seconds))),
            )
    finally:
        _TRANSCODE_GATE.release()


def standardized_video_duration(path: Path) -> int:
    probe = _probe(path)
    _validate_duration(probe)
    if not _compatible_mp4(probe):
        raise BizError("视频未完成兼容处理，请重新上传")
    return max(1, int(round(probe.duration_seconds)))
