"""社区每日资讯任务。

只读取代码内白名单中的官方 Feed/API，保存标题、短摘要和原链接；视频仅保存
Bilibili 官方账号页面、缩略图和官方播放器地址。外部候选不足时使用KAI星算自有行情摘要补位。
"""
from __future__ import annotations

import hashlib
import html
import re
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.community import ContentIngestRun, ContentSource, Post
from app.models.product import Product
from app.models.user import User

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
YT = "{http://www.youtube.com/xml/schemas/2015}"

BILIBILI_VIDEO_PROVIDER = "bilibili"
PLAYABLE_VIDEO_PROVIDERS = (BILIBILI_VIDEO_PROVIDER,)
BILIBILI_VIDEO_ID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
INTERNAL_SOURCE_KEY = "wod-market"
INTERNAL_SOURCE_NAME = "KAI星算算力行情"
INTERNAL_SOURCE_AUTHOR = "KAI星算"
INTERNAL_SYSTEM_PHONE = "wod-community"
INTERNAL_SYSTEM_USERNAME = "KAI星算平台行情"
INTERNAL_REGION_EN_BY_CODE = {
    "north_china": "North China",
    "east_china": "East China",
    "central_china": "Central China",
    "south_china": "South China",
    "northeast_china": "Northeast China",
    "northwest_china": "Northwest China",
    "southwest_china": "Southwest China",
    "china_unspecified": "Mainland China",
    "asia_pacific": "Asia Pacific",
    "north_america": "North America",
    "europe": "Europe",
    "middle_east": "Middle East",
    "south_america": "South America",
    "africa": "Africa",
    "global_unspecified": "Global / Undisclosed",
}
INTERNAL_REGION_EN_BY_NAME = {
    "华北": "North China",
    "华东": "East China",
    "华中": "Central China",
    "华南": "South China",
    "东北": "Northeast China",
    "西北": "Northwest China",
    "西南": "Southwest China",
    "中国大陆": "Mainland China",
    "亚太": "Asia Pacific",
    "北美": "North America",
    "欧洲": "Europe",
    "中东": "Middle East",
    "南美": "South America",
    "非洲": "Africa",
    "海外": "Overseas",
    "全球/未披露": "Global / Undisclosed",
    "全球／未披露": "Global / Undisclosed",
    "全球 / 未披露": "Global / Undisclosed",
    "未披露": "Undisclosed",
    "平台": "the platform",
}
BILIBILI_OFFICIAL_OWNER_ID = "1320140761"
BILIBILI_SEARCH_QUERIES = (
    "NVIDIA英伟达",
    "NVIDIA英伟达 DGX",
    "NVIDIA英伟达 AI",
    "NVIDIA英伟达 CUDA",
    "NVIDIA英伟达 LLM",
    "NVIDIA英伟达 推理",
    "NVIDIA英伟达 算力",
    "NVIDIA英伟达 AI 工厂",
    "NVIDIA英伟达 Token",
    "NVIDIA英伟达 GTC",
)
BILIBILI_RELEVANT_TERMS = (
    "ai", "人工智能", "算力", "gpu", "cuda", "llm", "大模型", "模型",
    "推理", "训练", "token", "tensorrt", "triton", "dgx", "nemo",
    "机器人", "物理ai", "物理 ai", "ai工厂", "ai 工厂", "ai factory",
    "加速计算", "数据中心", "nvlink", "blackwell", "rubin", "cosmos",
    "智能体", "agent", "生成式", "inference", "开发者", "科研", "集群",
    "omniverse", "isaac", "虚拟孪生", "自动驾驶", "gtc",
)
BILIBILI_BLOCKED_TERMS = (
    "游戏", "电竞", "dota", "dlss", "光线追踪", "gameplay", "gaming",
    "geforce", "rtx on", "预购", "公测", "实机", "steam", "玩家",
    "刺客信条", "战争机器", "影之刃", "诡秘之主", "宣传片",
)
BILIBILI_TITLE_EN = {
    "BV1YTME6fENw": "DGX Spark Livestream Recap – Developer Q&A",
    "BV1opNY6PEwW": "DGX Spark Livestream Recap – Getting Started with NVIDIA NemoClaw",
    "BV1YMME6FEha": "DGX Spark Livestream Recap – Empowering Higher Education and Research",
    "BV1XTME6fE2y": "DGX Spark Livestream Recap – Backend Development with Local LLM Inference",
    "BV1BJuq64EqN": "NVIDIA AI Robotics Session – Full-Stack Technology and Architecture in Practice",
    "BV1M3jmzuEJR": "Inside the NVIDIA Isaac GR00T N1 Embodied Model",
    "BV1KS4y1v7zd": "AI Inference Essentials | Introduction to Triton Inference Server Frameworks",
    "BV1bQtQz2EpT": "Using NVIDIA Isaac Sim Synthetic Data to Power Physical AI",
    "BV14gpJe7EzP": "NVIDIA DRIVE Labs | Enhancing Autonomous Driving Simulation with Generative AI",
    "BV1medJY2EZ8": "Introducing NVIDIA DGX Spark",
    "BV1HK421i7Qu": "I AM AI | NVIDIA GTC 2024 | Official Keynote Introduction",
    "BV1AbwSzeEKD": "NVIDIA CEO Jensen Huang Keynote | GTC 2026",
    "BV1oNyhBxEDV": "NVIDIA AI Robotics Session – Next-Generation Physics Engine Newton",
    "BV1XJLf6tENt": "NVIDIA Introduces Cosmos 3: An Open Physical AI Model That Reasons, Generates, and Acts",
    "BV1mZ421M7U4": "NVIDIA Powers the New Industrial Revolution with AI Factories",
    "BV1447Z6QEVp": "NVIDIA and Dassault Systèmes Build an Industrial AI Platform for Virtual Twins",
    "BV11XEY6DEZy": "NVIDIA Alpamayo's Inner Monologue",
    "BV1a5QRYCE5j": "NVIDIA CEO Jensen Huang Keynote | GTC 2025",
    "BV1NZdbBaEBR": "NVIDIA GTC Automotive Special Session",
}
BILIBILI_FALLBACK_CONTENT_EN = (
    "NVIDIA AI and Compute Official Video\n\n"
    "Watch this AI and accelerated-computing video from the official NVIDIA account. "
    "Open the official source page for the original title and complete details."
)

TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}

RELEVANCE_TERMS = {
    "gpu": 6, "cuda": 6, "pytorch": 6, "vllm": 6, "tensorrt": 6,
    "inference": 5, "training": 4, "llm": 5, "large language model": 5,
    "transformer": 4, "nvidia": 4, "token": 4, "tokens per second": 6, "h100": 5,
    "a100": 5, "b200": 5, "gb200": 5, "gb300": 5, "data center": 3,
    "ai model": 3, "deep learning": 4, "machine learning": 3,
    "robot learning": 3, "accelerator": 4, "显卡": 5, "算力": 6,
    "大模型": 5, "推理": 5, "训练": 4, "令牌": 4,
}

BLOCKED_TERMS = {
    "casino", "gambling", "sports betting", "airdrop", "meme coin",
    "政治博彩", "博彩", "空投币", "gaming", "gameplay", "esports",
    "video game", "geforce", "dlss", "ray tracing", "游戏", "电竞",
    "预购", "公测", "实机演示", "游戏宣传片",
}


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    kind: str
    endpoint: str
    terms_url: str
    daily_limit: int
    allowed_hosts: tuple[str, ...]


@dataclass
class Candidate:
    source_key: str
    source_name: str
    source_item_id: str
    title: str
    summary: str
    url: str | None
    author: str | None
    published_at: datetime
    content_type: str
    bucket: str
    topic_zh: str
    topic_en: str
    video_provider: str | None = None
    video_id: str | None = None
    video_url: str | None = None
    embed_url: str | None = None
    thumbnail_url: str | None = None
    origin: str = "aggregated"
    content_zh: str | None = None
    content_en: str | None = None
    score: int = 0

    @property
    def canonical_url(self) -> str | None:
        return canonicalize_url(self.url) if self.url else None

    @property
    def content_hash(self) -> str:
        normalized = re.sub(r"\W+", " ", self.title.lower()).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


SOURCE_SPECS = (
    SourceSpec(
        key="nvidia-blog",
        name="NVIDIA Technical Blog",
        kind="atom",
        endpoint="https://developer.nvidia.com/blog/feed/",
        terms_url="https://www.nvidia.com/en-us/about-nvidia/legal-info/",
        daily_limit=8,
        allowed_hosts=("developer.nvidia.com", "nvidia.com"),
    ),
    SourceSpec(
        key="arxiv",
        name="arXiv",
        kind="arxiv",
        endpoint=(
            "https://export.arxiv.org/api/query?"
            "search_query=all%3A%28GPU%20OR%20CUDA%20OR%20%22large%20language%20model%22%20OR%20inference%29"
            "&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
        ),
        terms_url="https://info.arxiv.org/help/api/index.html",
        daily_limit=8,
        allowed_hosts=("arxiv.org", "export.arxiv.org"),
    ),
    SourceSpec(
        key="github-vllm",
        name="GitHub · vLLM",
        kind="github",
        endpoint="https://github.com/vllm-project/vllm/releases.atom",
        terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        daily_limit=2,
        allowed_hosts=("github.com",),
    ),
    SourceSpec(
        key="github-pytorch",
        name="GitHub · PyTorch",
        kind="github",
        endpoint="https://github.com/pytorch/pytorch/releases.atom",
        terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        daily_limit=2,
        allowed_hosts=("github.com",),
    ),
    SourceSpec(
        key="github-transformers",
        name="GitHub · Transformers",
        kind="github",
        endpoint="https://github.com/huggingface/transformers/releases.atom",
        terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        daily_limit=2,
        allowed_hosts=("github.com",),
    ),
    SourceSpec(
        key="github-tensorrt-llm",
        name="GitHub · TensorRT-LLM",
        kind="github",
        endpoint="https://github.com/NVIDIA/TensorRT-LLM/releases.atom",
        terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        daily_limit=2,
        allowed_hosts=("github.com",),
    ),
    SourceSpec(
        key="bilibili-nvidia-official",
        name="Bilibili · NVIDIA",
        kind="bilibili-official",
        endpoint="https://search.bilibili.com/all?keyword=NVIDIA%E8%8B%B1%E4%BC%9F%E8%BE%BE",
        terms_url="https://www.bilibili.com/blackboard/protocal/licence.html",
        daily_limit=20,
        allowed_hosts=("bilibili.com", "www.bilibili.com", "player.bilibili.com", "hdslb.com"),
    ),
)

SOURCE_BY_KEY = {source.key: source for source in SOURCE_SPECS}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(value: str | None, limit: int = 500) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html.unescape(value))
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def canonicalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        query = [
            (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_QUERY_KEYS
        ]
        host = (parts.hostname or "").lower()
        netloc = host
        if parts.port and not ((parts.scheme == "https" and parts.port == 443) or (parts.scheme == "http" and parts.port == 80)):
            netloc = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/") or "/", urlencode(query), ""))
    except Exception:
        return value.strip()


def _safe_url(value: str | None, spec: SourceSpec) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower()
        allowed = any(host == item or host.endswith("." + item) for item in spec.allowed_hosts)
        if parts.scheme != "https" or not allowed:
            return None
        return value.strip()
    except Exception:
        return None


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _entry_link(entry: ET.Element) -> str | None:
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("rel", "alternate") == "alternate" and link.attrib.get("href"):
            return link.attrib["href"]
    return None


def _entry_author(entry: ET.Element) -> str | None:
    return entry.findtext(f"{ATOM}author/{ATOM}name")


def _relevance_score(candidate: Candidate) -> int:
    haystack = f"{candidate.title} {candidate.summary}".lower()
    if any(term in haystack for term in BLOCKED_TERMS):
        return -100

    score = sum(weight for term, weight in RELEVANCE_TERMS.items() if term in haystack)
    if candidate.source_key.startswith("github-"):
        score += 8
    elif candidate.source_key == "nvidia-blog":
        score += 5
    elif candidate.source_key == "bilibili-nvidia-official":
        score += 8
    elif candidate.source_key.startswith("youtube-"):
        score += 3

    age = datetime.now(timezone.utc).replace(tzinfo=None) - candidate.published_at
    if age <= timedelta(days=3):
        score += 4
    elif age <= timedelta(days=7):
        score += 2
    elif age > timedelta(days=45):
        score -= 4
    return score


def _parse_atom(xml_text: str, spec: SourceSpec) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    result: list[Candidate] = []
    for entry in root.findall(f"{ATOM}entry"):
        title = strip_html(entry.findtext(f"{ATOM}title"), 240)
        item_id = (entry.findtext(f"{ATOM}id") or "").strip()
        published = _parse_datetime(entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated"))
        author = strip_html(_entry_author(entry), 120) or None
        link = _safe_url(_entry_link(entry), spec)
        if not title or not item_id or not link:
            continue

        if spec.kind == "youtube":
            video_id = (entry.findtext(f"{YT}videoId") or item_id.rsplit(":", 1)[-1]).strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
                continue
            group = entry.find(f"{MEDIA}group")
            thumbnail = None
            if group is not None:
                thumb = group.find(f"{MEDIA}thumbnail")
                thumbnail = _safe_url(thumb.attrib.get("url") if thumb is not None else None, spec)
            candidate = Candidate(
                source_key=spec.key,
                source_name=spec.name,
                source_item_id=video_id,
                title=title,
                summary="",
                url=link,
                author=author,
                published_at=published,
                content_type="video",
                bucket="video",
                topic_zh="官方视频",
                topic_en="Official Video",
                video_provider="youtube",
                video_id=video_id,
                video_url=link,
                embed_url=f"https://www.youtube.com/embed/{video_id}?playsinline=1",
                thumbnail_url=thumbnail or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            )
        else:
            raw_summary = entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content")
            summary = strip_html(raw_summary, 500)
            is_release = spec.kind == "github"
            candidate = Candidate(
                source_key=spec.key,
                source_name=spec.name,
                source_item_id=item_id,
                title=title,
                summary=summary,
                url=link,
                author=author,
                published_at=published,
                content_type="article",
                bucket="release" if is_release else "news",
                topic_zh="版本发布" if is_release else "行业资讯",
                topic_en="Release" if is_release else "Industry News",
            )
        candidate.score = _relevance_score(candidate)
        if candidate.score > 0:
            result.append(candidate)
    result.sort(key=lambda item: (item.score, item.published_at), reverse=True)
    return result[: spec.daily_limit]


def _parse_arxiv(xml_text: str, spec: SourceSpec) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    result: list[Candidate] = []
    for entry in root.findall(f"{ATOM}entry"):
        item_id = (entry.findtext(f"{ATOM}id") or "").strip()
        title = strip_html(entry.findtext(f"{ATOM}title"), 240)
        summary = strip_html(entry.findtext(f"{ATOM}summary"), 500)
        link = _safe_url(_entry_link(entry) or item_id, spec)
        authors = [strip_html(node.text, 80) for node in entry.findall(f"{ATOM}author/{ATOM}name")]
        if not item_id or not title or not link:
            continue
        candidate = Candidate(
            source_key=spec.key,
            source_name=spec.name,
            source_item_id=item_id,
            title=title,
            summary=summary,
            url=link,
            author=", ".join(filter(None, authors[:3])) or None,
            published_at=_parse_datetime(entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")),
            content_type="article",
            bucket="news",
            topic_zh="研究前沿",
            topic_en="Research",
        )
        candidate.score = _relevance_score(candidate)
        if candidate.score >= 5:
            result.append(candidate)
    result.sort(key=lambda item: (item.score, item.published_at), reverse=True)
    return result[: spec.daily_limit]


def _parse_bilibili_date(value: str) -> datetime:
    now = datetime.now(_app_timezone())
    text = strip_html(value, 40).lstrip("· ").strip()
    if text in ("昨天", "yesterday"):
        parsed = now - timedelta(days=1)
    else:
        relative = re.fullmatch(r"(\d+)\s*(分钟前|小时前|天前)", text)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2)
            delta = {
                "分钟前": timedelta(minutes=amount),
                "小时前": timedelta(hours=amount),
                "天前": timedelta(days=amount),
            }[unit]
            parsed = now - delta
        else:
            try:
                parts = [int(part) for part in text.split("-")]
                if len(parts) == 2:
                    parsed = now.replace(month=parts[0], day=parts[1], hour=12, minute=0, second=0, microsecond=0)
                elif len(parts) == 3:
                    parsed = now.replace(
                        year=parts[0], month=parts[1], day=parts[2],
                        hour=12, minute=0, second=0, microsecond=0,
                    )
                else:
                    parsed = now
            except (TypeError, ValueError):
                parsed = now
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _bilibili_content_en(bvid: str) -> str:
    return BILIBILI_TITLE_EN.get(bvid, BILIBILI_FALLBACK_CONTENT_EN)


def _is_relevant_bilibili_video(title: str) -> bool:
    haystack = strip_html(title, 300).lower()
    compact = re.sub(r"\s+", "", haystack)
    if any(term in haystack or term.replace(" ", "") in compact for term in BILIBILI_BLOCKED_TERMS):
        return False
    for term in BILIBILI_RELEVANT_TERMS:
        if term == "ai":
            if re.search(r"(?<![a-z])ai(?![a-z])", haystack):
                return True
        elif term in haystack or term.replace(" ", "") in compact:
            return True
    return False


def _is_playable_video_reference(video_provider: str | None, video_id: str | None) -> bool:
    """Accept only a provider/id pair that every client can reconstruct safely."""
    return (
        video_provider == BILIBILI_VIDEO_PROVIDER
        and bool(BILIBILI_VIDEO_ID_RE.fullmatch(str(video_id or "").strip()))
    )


def _parse_bilibili_official_page(page: str, spec: SourceSpec) -> list[Candidate]:
    result: list[Candidate] = []
    owner_marker = f'//space.bilibili.com/{BILIBILI_OFFICIAL_OWNER_ID}'
    for card in page.split('<div class="bili-video-card"')[1:]:
        if owner_marker not in card:
            continue
        video_match = re.search(
            r'href="//www\.bilibili\.com/video/(?P<bvid>BV[0-9A-Za-z]{10})/"',
            card,
        )
        image_match = re.search(
            r'<img src="(?P<thumbnail>[^"]+)" alt="(?P<title>[^"]+)"',
            card,
        )
        date_match = re.search(
            r'bili-video-card__info--date[^>]*>(?P<date>[^<]+)</span>',
            card,
        )
        if not video_match or not image_match or not date_match:
            continue
        bvid = video_match.group("bvid")
        title = strip_html(html.unescape(image_match.group("title")), 240)
        if not title or not _is_relevant_bilibili_video(title):
            continue
        thumbnail = html.unescape(image_match.group("thumbnail"))
        if thumbnail.startswith("//"):
            thumbnail = "https:" + thumbnail
        thumbnail = _safe_url(thumbnail, spec)
        if not thumbnail:
            continue
        source_url = f"https://www.bilibili.com/video/{bvid}/"
        candidate = Candidate(
            source_key=spec.key,
            source_name=spec.name,
            source_item_id=bvid,
            title=title,
            # Embed only the official player's public video; do not copy the
            # description, transcript, subtitles, or the underlying media file.
            summary="",
            url=source_url,
            author="NVIDIA",
            published_at=_parse_bilibili_date(date_match.group("date")),
            content_type="video",
            bucket="video",
            topic_zh="AI 与算力",
            topic_en="AI & Compute",
            video_provider=BILIBILI_VIDEO_PROVIDER,
            video_id=bvid,
            video_url=source_url,
            embed_url=(
                "https://player.bilibili.com/player.html?"
                f"bvid={bvid}&page=1&high_quality=1&danmaku=0"
            ),
            thumbnail_url=thumbnail,
            content_en=_bilibili_content_en(bvid),
        )
        candidate.score = max(15, _relevance_score(candidate) + 8)
        result.append(candidate)
    return result


def _fetch_bilibili_official(spec: SourceSpec) -> list[Candidate]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    }
    endpoints = [
        spec.endpoint,
        *(
            "https://search.bilibili.com/all?" + urlencode({"keyword": query})
            for query in BILIBILI_SEARCH_QUERIES[1:]
        ),
    ]
    pages: list[str] = []
    with httpx.Client(
        timeout=settings.COMMUNITY_HTTP_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    ) as client:
        def fetch_page(endpoint: str) -> str:
            response = client.get(endpoint)
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError(f"Bilibili page too large: {len(response.content)} bytes")
            return response.text

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="bilibili-search") as pool:
            futures = [pool.submit(fetch_page, endpoint) for endpoint in endpoints]
            for future in as_completed(futures):
                try:
                    pages.append(future.result())
                except Exception:
                    continue

    result: list[Candidate] = []
    seen: set[str] = set()
    for page in pages:
        for candidate in _parse_bilibili_official_page(page, spec):
            if candidate.video_id in seen:
                continue
            result.append(candidate)
            seen.add(candidate.video_id or "")
    result.sort(key=lambda value: value.published_at, reverse=True)
    if not result:
        raise ValueError("Bilibili NVIDIA official account returned no relevant AI/compute videos")
    return result[: spec.daily_limit]


def _fetch_source(spec: SourceSpec) -> list[Candidate]:
    if spec.kind == "bilibili-official":
        return _fetch_bilibili_official(spec)
    headers = {
            "User-Agent": "WOD-Community/1.0",
        "Accept": "application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
    }
    with httpx.Client(timeout=settings.COMMUNITY_HTTP_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(spec.endpoint)
        response.raise_for_status()
        if len(response.content) > 3_000_000:
            raise ValueError(f"feed too large: {len(response.content)} bytes")
        text = response.content.decode(response.encoding or "utf-8", errors="replace")
    return _parse_arxiv(text, spec) if spec.kind == "arxiv" else _parse_atom(text, spec)


def _seed_sources(db: Session) -> dict[str, ContentSource]:
    existing = {row.key: row for row in db.query(ContentSource).all()}
    reviewed_at = datetime(2026, 8, 14)
    for spec in SOURCE_SPECS:
        row = existing.get(spec.key)
        if not row:
            row = ContentSource(
                key=spec.key,
                name=spec.name,
                kind=spec.kind,
                endpoint=spec.endpoint,
                terms_url=spec.terms_url,
                rights_status="allowed",
                enabled=True,
                daily_limit=spec.daily_limit,
                reviewed_at=reviewed_at,
            )
            db.add(row)
            existing[spec.key] = row
        else:
            row.name = spec.name
            row.kind = spec.kind
            row.endpoint = spec.endpoint
            row.terms_url = spec.terms_url
            row.daily_limit = spec.daily_limit
            row.enabled = True
    # Removed sources stay in the audit table but are not fetched again.
    for key, row in existing.items():
        if key not in SOURCE_BY_KEY:
            row.enabled = False
    db.commit()
    return existing


def _get_system_user(db: Session) -> User:
    user = db.query(User).filter(User.phone == INTERNAL_SYSTEM_PHONE).first()
    if user:
        if user.username != INTERNAL_SYSTEM_USERNAME:
            user.username = INTERNAL_SYSTEM_USERNAME
            db.flush()
        return user
    user = User(
        username=INTERNAL_SYSTEM_USERNAME,
        phone=INTERNAL_SYSTEM_PHONE,
        password=hash_password(secrets.token_urlsafe(32)),
        role="personal",
        supplier_status="none",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _remove_disallowed_game_posts(db: Session) -> int:
    """移除旧 GeForce 游戏来源；该来源已退出白名单，不再参与展示或计数。"""
    posts = db.query(Post).filter(Post.source_key == "bilibili-geforce-official").all()
    for post in posts:
        db.delete(post)
    return len(posts)


def _backfill_bilibili_english_content(db: Session) -> int:
    """修正已入库视频的英文内容，避免英文模式继续显示历史中文标题。"""
    updated = 0
    source_key = "bilibili-nvidia-official"
    posts = db.query(Post).filter(Post.source_key == source_key).all()
    for post in posts:
        localized = _bilibili_content_en(post.video_id or "")
        if post.content_en != localized:
            post.content_en = localized
            updated += 1
        if post.source_name != SOURCE_BY_KEY[source_key].name:
            post.source_name = SOURCE_BY_KEY[source_key].name
        if post.source_author != "NVIDIA":
            post.source_author = "NVIDIA"
    return updated


def _backfill_internal_branding(db: Session) -> int:
    """Refresh display-only branding while retaining the legacy source key."""
    updated = 0
    posts = db.query(Post).filter(Post.source_key == INTERNAL_SOURCE_KEY).all()
    for post in posts:
        changed = False
        for field in ("content", "content_en"):
            value = getattr(post, field)
            branded = value
            if branded:
                if field == "content":
                    branded = re.sub(
                        r"(?<![A-Z0-9_-])(?:WOD|ZTW)(?![A-Z0-9_-])",
                        "KAI星算",
                        branded,
                    )
                    branded = branded.replace("来自 KAI星算 最新", "来自KAI星算最新")
                else:
                    branded = re.sub(
                        r"(?<![A-Z0-9_-])(?:WOD|ZTW)(?:\s+market)?(?![A-Z0-9_-])",
                        "KAI Compute Market",
                        branded,
                        flags=re.IGNORECASE,
                    )
                    branded = re.sub(
                        r"Compute Star Map(?:\s+market)?",
                        "KAI Compute Market",
                        branded,
                        flags=re.IGNORECASE,
                    )
                    branded = re.sub(
                        r"KAI星算(?:\s+market)?",
                        "KAI Compute Market",
                        branded,
                        flags=re.IGNORECASE,
                    )
                    branded = re.sub(
                        r"KAI Compute Market(?:\s+market)+",
                        "KAI Compute Market",
                        branded,
                        flags=re.IGNORECASE,
                    )
                    for region_zh, region_en in sorted(
                        INTERNAL_REGION_EN_BY_NAME.items(),
                        key=lambda item: len(item[0]),
                        reverse=True,
                    ):
                        branded = branded.replace(region_zh, region_en)
            if value != branded:
                setattr(post, field, branded)
                changed = True
        if post.source_name != INTERNAL_SOURCE_NAME:
            post.source_name = INTERNAL_SOURCE_NAME
            changed = True
        if post.source_author != INTERNAL_SOURCE_AUTHOR:
            post.source_author = INTERNAL_SOURCE_AUTHOR
            changed = True
        if changed:
            updated += 1
    return updated


def _internal_region_en(region_name: str | None, region_code: str | None) -> str:
    """Return an English-only region label for first-party generated posts."""

    code = str(region_code or "").strip().lower()
    if code in INTERNAL_REGION_EN_BY_CODE:
        return INTERNAL_REGION_EN_BY_CODE[code]

    name = str(region_name or "平台").strip()
    if name in INTERNAL_REGION_EN_BY_NAME:
        return INTERNAL_REGION_EN_BY_NAME[name]
    # Upstream identifiers such as EU-West are already suitable for English.
    # Do not leak an unrecognised Chinese label into the English copy.
    return "the listed region" if re.search(r"[\u3400-\u9fff]", name) else name


def _app_timezone():
    try:
        return ZoneInfo(settings.COMMUNITY_TIMEZONE)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8))


def _batch_date() -> str:
    return datetime.now(_app_timezone()).date().isoformat()


def _same_title(left: str, right: str) -> bool:
    clean_left = re.sub(r"\W+", " ", left.lower()).strip()
    clean_right = re.sub(r"\W+", " ", right.lower()).strip()
    return SequenceMatcher(None, clean_left, clean_right).ratio() >= 0.92


def _deduplicate(db: Session, candidates: list[Candidate], batch: str) -> tuple[list[Candidate], int]:
    item_pairs = {
        (key, item_id) for key, item_id in db.query(Post.source_key, Post.source_item_id)
        .filter(Post.source_item_id.isnot(None)).all()
    }
    urls = {
        value for (value,) in db.query(Post.canonical_url).filter(Post.canonical_url.isnot(None)).all()
    }
    hashes = {
        value for (value,) in db.query(Post.content_hash).filter(Post.content_hash.isnot(None)).all()
    }
    batch_video_pairs = {
        (key, item_id) for key, item_id in db.query(Post.source_key, Post.source_item_id)
        .filter(
            Post.publish_batch == batch,
            Post.content_type == "video",
            Post.source_item_id.isnot(None),
        ).all()
    }
    recent_titles = [
        (value or "").split("\n", 1)[0] for (value,) in db.query(Post.content)
        .order_by(Post.id.desc()).limit(200).all()
    ]

    kept: list[Candidate] = []
    skipped = 0
    for candidate in sorted(candidates, key=lambda item: (item.score, item.published_at), reverse=True):
        pair = (candidate.source_key, candidate.source_item_id)
        url = candidate.canonical_url
        digest = candidate.content_hash
        if candidate.content_type == "video":
            duplicate = pair in batch_video_pairs
        else:
            duplicate = pair in item_pairs or (url and url in urls) or digest in hashes
        if duplicate:
            skipped += 1
            continue
        if candidate.content_type != "video" and any(
            _same_title(candidate.title, title) for title in recent_titles if title
        ):
            skipped += 1
            continue
        if any(_same_title(candidate.title, item.title) for item in kept):
            skipped += 1
            continue
        kept.append(candidate)
        if candidate.content_type == "video":
            batch_video_pairs.add(pair)
        else:
            item_pairs.add(pair)
            if url:
                urls.add(url)
            hashes.add(digest)
    return kept, skipped


def _choose_candidates(
    db: Session,
    batch: str,
    candidates: list[Candidate],
    missing_total: int,
    video_target: int,
) -> list[Candidate]:
    existing = db.query(Post).filter(Post.publish_batch == batch).all()
    video_need = max(0, video_target - sum(
        1 for post in existing
        if post.content_type == "video"
        and _is_playable_video_reference(post.video_provider, post.video_id)
    ))
    release_need = max(0, 2 - sum(1 for post in existing if (post.source_key or "").startswith("github-")))
    news_target = max(0, settings.COMMUNITY_DAILY_TARGET - video_target - 2)
    news_need = max(0, news_target - sum(
        1 for post in existing
        if post.content_type != "video" and not (post.source_key or "").startswith("github-") and post.origin != "internal"
    ))

    pools = {
        "video": [
            item for item in candidates
            if item.bucket == "video"
            and _is_playable_video_reference(item.video_provider, item.video_id)
        ],
        "news": [item for item in candidates if item.bucket == "news"],
        "release": [item for item in candidates if item.bucket == "release"],
    }
    pools["video"].sort(key=lambda value: value.published_at, reverse=True)
    selected: list[Candidate] = []
    selected.extend(pools["video"][:video_need])

    # 视频补量可以替换当天无人互动的自动文章；普通资讯只填充总量缺口。
    regular_slots = max(0, missing_total - len(selected))
    for bucket, amount in (("news", news_need), ("release", release_need)):
        for item in pools[bucket][:amount]:
            if regular_slots <= 0:
                break
            selected.append(item)
            regular_slots -= 1

    for item in sorted(candidates, key=lambda value: (value.score, value.published_at), reverse=True):
        if regular_slots <= 0:
            break
        if item.content_type == "video" and not _is_playable_video_reference(
            item.video_provider, item.video_id,
        ):
            continue
        if item not in selected:
            selected.append(item)
            regular_slots -= 1
    return selected


def _internal_candidates(db: Session, batch: str, count: int, start_index: int = 0) -> list[Candidate]:
    products = db.query(Product).filter(Product.status == "on").order_by(Product.id.desc()).limit(max(20, count * 3)).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result: list[Candidate] = []
    for offset in range(count):
        index = start_index + offset
        product = products[index % len(products)] if products else None
        if product:
            name = product.name
            region = product.region_name or "平台"
            region_en = _internal_region_en(product.region_name, product.region_code)
            price = f"{float(product.price):.2f}"
            stock = product.stock or 0
            content_zh = f"{name} 今日算力观察\n\n{region}当前参考价为 {price} 卡时/h，可租 {stock} 台。价格和库存来自KAI星算最新站内行情，实际下单前请再次确认。"
            content_en = f"{name} Daily Compute Snapshot\n\nThe current reference price in {region_en} is {price} CH/h, with {stock} units available. Price and availability come from the latest KAI Compute Market data; confirm again before ordering."
            title = f"{name} {batch} compute snapshot {index}"
        else:
            content_zh = f"今日算力使用提示 #{index + 1}\n\n开始训练前先确认显存、CUDA 版本和预计运行时长，可减少环境不匹配和闲置成本。"
            content_en = f"Daily Compute Tip #{index + 1}\n\nCheck VRAM, the CUDA version, and expected runtime before training to reduce environment mismatches and idle cost."
            title = f"KAI Compute Market tip {batch} {index}"
        result.append(Candidate(
            source_key=INTERNAL_SOURCE_KEY,
            source_name=INTERNAL_SOURCE_NAME,
            source_item_id=f"{INTERNAL_SOURCE_KEY}:{batch}:{index}",
            title=title,
            summary="",
            url=None,
            author=INTERNAL_SOURCE_AUTHOR,
            published_at=now,
            content_type="article",
            bucket="internal",
            topic_zh="算力行情",
            topic_en="Compute Market",
            origin="internal",
            content_zh=content_zh,
            content_en=content_en,
            score=1,
        ))
    return result


def _post_content(candidate: Candidate) -> tuple[str, str]:
    content = candidate.title
    if candidate.summary:
        content = f"{candidate.title}\n\n{candidate.summary}"
    return candidate.content_zh or content, candidate.content_en or content


def _save_candidate(db: Session, user: User, candidate: Candidate, batch: str) -> Post:
    content_zh, content_en = _post_content(candidate)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    post = Post(
        user_id=user.id,
        content=content_zh,
        content_en=content_en,
        topic=candidate.topic_zh,
        created_platform="system",
        last_modified_platform="system",
        topic_en=candidate.topic_en,
        origin=candidate.origin,
        content_type=candidate.content_type,
        source_key=candidate.source_key,
        source_name=candidate.source_name,
        source_url=candidate.url,
        source_item_id=candidate.source_item_id,
        source_author=candidate.author,
        source_published_at=candidate.published_at,
        summary=candidate.summary,
        rights_status="allowed",
        rights_checked_at=now,
        video_provider=candidate.video_provider,
        video_id=candidate.video_id,
        video_url=candidate.video_url,
        embed_url=candidate.embed_url,
        thumbnail_url=candidate.thumbnail_url,
        canonical_url=candidate.canonical_url,
        content_hash=candidate.content_hash,
        ingested_at=now,
        publish_batch=batch,
        likes=0,
        comments=0,
        shares=0,
    )
    db.add(post)
    return post


def generate_daily_posts(count: int | None = None) -> int:
    """补齐今天的社区自动内容；重复调用只补缺口。"""
    target = max(1, min(int(count or settings.COMMUNITY_DAILY_TARGET), 20))
    batch = _batch_date()
    db: Session = SessionLocal()
    run_id: int | None = None
    try:
        source_rows = _seed_sources(db)
        system_user = _get_system_user(db)
        removed_games = _remove_disallowed_game_posts(db)
        localized_videos = _backfill_bilibili_english_content(db)
        branded_internal_posts = _backfill_internal_branding(db)
        if removed_games or localized_videos or branded_internal_posts:
            db.commit()
        existing_count = db.query(Post).filter(Post.publish_batch == batch).count()

        run = ContentIngestRun(batch=batch, target_count=target, status="running")
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        video_target = max(0, min(settings.COMMUNITY_DAILY_VIDEO_TARGET, target))
        existing_video_count = db.query(Post).filter(
            Post.publish_batch == batch,
            Post.content_type == "video",
            Post.video_provider.in_(PLAYABLE_VIDEO_PROVIDERS),
        ).count()
        missing_total = max(0, target - existing_count)
        missing_videos = max(0, video_target - existing_video_count)
        if missing_total == 0 and missing_videos == 0:
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            print(
                f"[community_daily] {batch} 已有 {existing_count}/{target} 条，"
                f"视频 {existing_video_count}/{video_target}，无需补充"
            )
            return 0

        candidates: list[Candidate] = []
        errors: list[str] = []
        if settings.COMMUNITY_ONLINE_ENABLED:
            enabled_specs = [
                SOURCE_BY_KEY[key] for key, row in source_rows.items()
                if key in SOURCE_BY_KEY and row.enabled and row.rights_status == "allowed"
            ]
            with ThreadPoolExecutor(max_workers=4, thread_name_prefix="community-source") as pool:
                future_map = {pool.submit(_fetch_source, spec): spec for spec in enabled_specs}
                for future in as_completed(future_map):
                    spec = future_map[future]
                    row = source_rows[spec.key]
                    try:
                        fetched = future.result()
                        candidates.extend(fetched)
                        row.last_success_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        row.last_error = None
                    except Exception as exc:
                        message = f"{spec.key}: {type(exc).__name__}: {str(exc)[:240]}"
                        errors.append(message)
                        row.last_error = message
            db.commit()

        candidates, skipped = _deduplicate(db, candidates, batch)
        selected = _choose_candidates(db, batch, candidates, missing_total, video_target)

        replacement_needed = max(0, len(selected) - missing_total)
        replaced = 0
        if replacement_needed > 0:
            replacement_priority = case((Post.content_type == "video", 0), else_=1)
            replaceable = db.query(Post).filter(
                Post.publish_batch == batch,
                or_(
                    Post.content_type != "video",
                    Post.video_provider.is_(None),
                    Post.video_provider.notin_(PLAYABLE_VIDEO_PROVIDERS),
                ),
                Post.origin.in_(("aggregated", "internal")),
                Post.likes == 0,
                Post.comments == 0,
            ).order_by(replacement_priority.asc(), Post.id.desc()).limit(replacement_needed).all()
            for post in replaceable:
                db.delete(post)
                replaced += 1

        for candidate in selected:
            _save_candidate(db, system_user, candidate, batch)

        remaining = max(0, target - (existing_count - replaced + len(selected)))
        if remaining > 0:
            internal_existing = db.query(Post).filter(
                Post.publish_batch == batch, Post.origin == "internal"
            ).count()
            for candidate in _internal_candidates(db, batch, remaining, internal_existing):
                _save_candidate(db, system_user, candidate, batch)

        db.flush()
        created = len(selected) + max(0, remaining)
        final_count = db.query(Post).filter(Post.publish_batch == batch).count()
        final_video_count = db.query(Post).filter(
            Post.publish_batch == batch,
            Post.content_type == "video",
            Post.video_provider.in_(PLAYABLE_VIDEO_PROVIDERS),
        ).count()
        run.candidate_count = len(candidates)
        run.published_count = created
        run.skipped_count = skipped
        run.failed_count = len(errors)
        run.status = "completed" if final_count >= target and final_video_count >= video_target else "partial"
        run.error_summary = "\n".join(errors)[:2000] or None
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        print(
            f"[community_daily] {batch} 新增 {created} 条、替换 {replaced} 条（总计 {final_count}/{target} / "
            f"视频 {final_video_count}/{video_target} / 外部 {len(selected)} / 站内 {max(0, remaining)} / "
            f"候选 {len(candidates)} / 来源失败 {len(errors)}）"
        )
        return created
    except Exception as exc:
        db.rollback()
        if run_id:
            failed_run = db.query(ContentIngestRun).filter(ContentIngestRun.id == run_id).first()
            if failed_run:
                failed_run.status = "failed"
                failed_run.failed_count = max(1, failed_run.failed_count)
                failed_run.error_summary = f"{type(exc).__name__}: {str(exc)[:1800]}"
                failed_run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
        print(f"[community_daily] error: {type(exc).__name__}: {exc}")
        return 0
    finally:
        db.close()


def generate_posts(count: int = 10) -> int:
    """兼容旧调用名。"""
    return generate_daily_posts(count)


if __name__ == "__main__":
    generate_daily_posts()
