import calendar
import hashlib
import html
import re
from collections.abc import Callable
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from sqlalchemy.orm import Session
from urllib.parse import urljoin

from app.models import NewsArticle, NewsSource
from app.news_cache import cache_delete_news
from app.config import settings


DEFAULT_SOURCES = [
    {"name": "NVIDIA Technical Blog", "feed_url": "https://developer.nvidia.com/blog/feed/", "site_url": "https://developer.nvidia.com/blog/", "category": "hardware"},
    {"name": "OpenAI News", "feed_url": "https://openai.com/news/rss.xml", "site_url": "https://openai.com/news/", "category": "models"},
    {"name": "Hugging Face Blog", "feed_url": "https://huggingface.co/blog/feed.xml", "site_url": "https://huggingface.co/blog", "category": "opensource"},
    {"name": "Google DeepMind", "feed_url": "https://deepmind.google/blog/rss.xml", "site_url": "https://deepmind.google/blog/", "category": "models"},
    {"name": "Cloudflare Blog", "feed_url": "https://blog.cloudflare.com/rss/", "site_url": "https://blog.cloudflare.com/", "category": "cloud"},
    {"name": "Hugging Face Daily Papers", "feed_url": f"{settings.RSSHUB_BASE_URL.rstrip('/')}/huggingface/daily-papers", "site_url": "https://huggingface.co/papers", "category": "models", "is_official": False},
    {"name": "InfoQ AI & Architecture", "feed_url": f"{settings.RSSHUB_BASE_URL.rstrip('/')}/infoq/recommend", "site_url": "https://www.infoq.cn/", "category": "compute", "is_official": False},
]

CATEGORY_RULES = {
    "hardware": ("gpu", "nvidia", "cuda", "h100", "h200", "blackwell", "accelerator"),
    "models": ("model", "llm", "gpt", "reasoning", "multimodal", "agent"),
    "compute": ("inference", "training", "compute", "算力", "推理", "训练"),
    "cloud": ("cloud", "serverless", "kubernetes", "worker", "data center"),
    "opensource": ("open source", "github", "release", "hugging face", "开源"),
}

COMPUTE_ANCHORS = (
    "gpu", "cuda", "geforce", "rtx", "tesla gpu", "amd instinct", "radeon",
    "h100", "h200", "b100", "b200", "gb200", "a100", "a800", "l40", "mi300", "blackwell",
    "ai accelerator", "hardware accelerator", "ai chip", "inference chip", "算力", "显卡", "英特尔 gpu",
    "加速卡", "智算", "ai 芯片", "gpu 芯片",
)
INFRA_ANCHORS = (
    "data center", "datacenter", "ai factory", "gpu cluster", "compute cluster", "cloud gpu", "gpu cloud",
    "数据中心", "智算中心", "算力中心", "gpu 集群", "计算集群", "云 gpu", "液冷服务器",
)
MARKET_TERMS = (
    "price", "pricing", "rental", "rent", "lease", "cost", "capacity", "supply", "shortage",
    "availability", "inventory", "shipment", "价格", "报价", "租赁", "出租", "成本", "供给",
    "供应", "短缺", "库存", "交付", "产能", "采购", "行情",
)
TECHNICAL_TERMS = (
    "inference", "training", "vram", "memory bandwidth", "quantization", "model serving", "throughput",
    "latency", "deployment", "performance", "nvlink", "rdma", "tensor core", "推理", "训练",
    "显存", "量化", "吞吐", "延迟", "调度", "性能", "部署", "服务平台", "并行计算",
    "模型部署", "推理服务",
)
NEGATIVE_TERMS = (
    "教程", "入门", "课程", "免费领取", "嘉宾", "访谈", "人物", "手机", "汽车", "鸿蒙",
    "flutter", "react native", "agent 教程", "编程教程", "融资", "裁员", "争论", "开炮",
)
POLICY_TERMS = (
    "export control", "sanction", "regulation", "energy policy", "出口管制", "出口限制", "制裁",
    "监管", "能源政策", "产业政策",
)


def seed_sources(db: Session) -> None:
    for item in DEFAULT_SOURCES:
        source = db.query(NewsSource).filter(NewsSource.name == item["name"]).first()
        if source:
            source.feed_url = item["feed_url"]
            source.site_url = item["site_url"]
            source.category = item["category"]
            source.is_official = item.get("is_official", True)
            source.enabled = True
        else:
            values = {**item, "is_official": item.get("is_official", True), "enabled": True}
            db.add(NewsSource(**values))
    db.commit()


def normalize_url(raw_url: str) -> str:
    parsed = urlparse((raw_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"ref", "fbclid", "gclid"}]
    return urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), query=urlencode(query), fragment="")).rstrip("/")


def plain_text(value: str, limit: int = 600) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return value[:limit]


ALLOWED_TAGS = ["p", "br", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre", "code", "strong", "em", "a", "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td"]
ALLOWED_ATTRIBUTES = {"a": ["href", "title"], "img": ["src", "alt", "title", "width", "height", "referrerpolicy"]}


class SafeArticleParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in ALLOWED_TAGS:
            return
        safe_attrs = []
        for name, value in attrs:
            name = name.lower()
            if name not in ALLOWED_ATTRIBUTES.get(tag, []) or not value:
                continue
            if name in {"href", "src"}:
                value = urljoin(self.base_url, value)
                if urlparse(value).scheme not in {"http", "https"}:
                    continue
            safe_attrs.append(f'{name}="{html.escape(value, quote=True)}"')
        if tag == "img" and not any(attribute.startswith('referrerpolicy=') for attribute in safe_attrs):
            safe_attrs.append('referrerpolicy="no-referrer"')
        suffix = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.parts.append(f"<{tag}{suffix}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif not self.skip_depth and tag in ALLOWED_TAGS and tag not in {"br", "img"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(html.escape(data))


def sanitize_article_html(raw: str, base_url: str) -> str:
    parser = SafeArticleParser(base_url)
    parser.feed(raw)
    return trim_non_article_sections("".join(parser.parts).strip())


TRAILING_SECTION_PATTERN = re.compile(
    r"<h([2-4])[^>]*>\s*(?:嘉宾简介|作者简介|讲师简介|演讲嘉宾|关于作者)\s*</h\1>",
    flags=re.IGNORECASE,
)
PROMOTIONAL_SECTION_PATTERN = re.compile(
    r"<h([2-4])[^>]*>\s*(?:一套可以边做边学的极简教程|教程主要讲了什么)\s*</h\1>",
    flags=re.IGNORECASE,
)
PROMOTIONAL_SIGNALS = ("免费领取", "扫描下方海报", "开始学习", "极客时间教研组")


def trim_non_article_sections(content: str) -> str:
    """Remove source-site biographies appended after the actual article body."""
    promo = PROMOTIONAL_SECTION_PATTERN.search(content)
    if promo and sum(signal in content[promo.start():] for signal in PROMOTIONAL_SIGNALS) >= 2:
        content = content[:promo.start()].rstrip()
    match = TRAILING_SECTION_PATTERN.search(content)
    if match and match.start() >= len(content) * 0.5:
        return content[:match.start()].rstrip()
    return content


def article_content(entry, base_url: str) -> str:
    blocks = entry.get("content") or []
    raw = next((block.get("value", "") for block in blocks if block.get("value")), "")
    if not raw:
        raw = entry.get("summary", "") or entry.get("description", "")
    if len(plain_text(raw, 100_000)) < 120:
        return ""
    return sanitize_article_html(raw, base_url)


def classify(title: str, fallback: str) -> tuple[str, list[str]]:
    lowered = title.lower()
    matches = [name for name, keywords in CATEGORY_RULES.items() if any(word in lowered for word in keywords)]
    category = matches[0] if matches else fallback
    tags = []
    for tag in ("NVIDIA", "OpenAI", "GPU", "LLM", "AI Agent", "CUDA", "Cloud", "Open Source"):
        if tag.lower().replace("ai agent", "agent") in lowered:
            tags.append(tag)
    return category, tags[:5]


def entry_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None


def entry_image(entry) -> str | None:
    candidates = entry.get("media_content") or entry.get("media_thumbnail") or entry.get("enclosures") or []
    for candidate in candidates:
        value = normalize_url(candidate.get("url", ""))
        if value:
            return value
    content = " ".join(block.get("value", "") for block in (entry.get("content") or []))
    match = re.search(r'(?i)<img[^>]+src=["\']([^"\']+)', content or entry.get("summary", ""))
    if match:
        return normalize_url(match.group(1)) or None
    return None


def relevance_score(title: str, description: str = "", content: str = "") -> int:
    title_text = f" {plain_text(title, 1000).lower()} "
    haystack = f"{title_text} {plain_text(description, 3000).lower()} {plain_text(content, 5000).lower()}"
    title_has_anchor = any(term in title_text for term in COMPUTE_ANCHORS + INFRA_ANCHORS)
    body_has_anchor = any(term in haystack for term in COMPUTE_ANCHORS + INFRA_ANCHORS)
    title_has_market = any(term in title_text for term in MARKET_TERMS)
    title_has_technical = any(term in title_text for term in TECHNICAL_TERMS)
    if title_has_anchor:
        score = 5
    elif body_has_anchor and (title_has_market or title_has_technical):
        score = 3
    else:
        return -10
    score += 2 if any(term in haystack for term in MARKET_TERMS) else 0
    score += 1 if any(term in haystack for term in TECHNICAL_TERMS) else 0
    score -= 4 if any(term in title_text for term in NEGATIVE_TERMS) else 0
    return score


def publication_status(title: str, description: str = "", content: str = "") -> str:
    return "published" if relevance_score(title, description, content) >= 4 else "filtered"


def market_category(title: str, description: str = "", content: str = "") -> str:
    haystack = f" {plain_text(title, 1000).lower()} {plain_text(description, 3000).lower()} {plain_text(content, 3000).lower()} "
    if any(term in haystack for term in POLICY_TERMS):
        return "policy"
    if any(term in haystack for term in MARKET_TERMS):
        return "market"
    if any(term in haystack for term in COMPUTE_ANCHORS):
        return "hardware"
    return "compute"


def reassess_news(db: Session) -> dict:
    result = {"published": 0, "filtered": 0, "changed": 0}
    for article in db.query(NewsArticle).all():
        next_status = publication_status(article.title, article.summary, article.content)
        article.category = market_category(article.title, article.summary, article.content)
        if article.status != next_status:
            article.status = next_status
            result["changed"] += 1
        result[next_status] += 1
    db.commit()
    return result


def is_rsshub_source(source: NewsSource) -> bool:
    return source.feed_url.startswith(settings.RSSHUB_BASE_URL.rstrip("/")) or "rsshub." in source.feed_url


def sync_news(db: Session, should_stop: Callable[[], bool] | None = None) -> dict:
    seed_sources(db)
    sources = db.query(NewsSource).filter(NewsSource.enabled.is_(True)).all()
    result = {"sources": len(sources), "succeeded": 0, "failed": 0, "inserted": 0, "duplicates": 0}
    now = datetime.now(timezone.utc)
    stopped = False
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "KAI-NewsBot/1.0 (+public RSS reader)"}) as client:
        for source in sources:
            if should_stop and should_stop():
                stopped = True
                break
            inserted_before_source = result["inserted"]
            duplicates_before_source = result["duplicates"]
            try:
                response = client.get(source.feed_url)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if feed.bozo and not feed.entries:
                    raise ValueError(str(feed.bozo_exception))
                for entry in feed.entries[:40]:
                    if should_stop and should_stop():
                        stopped = True
                        break
                    title = plain_text(entry.get("title", ""), 500)
                    raw_description = entry.get("summary", "") or entry.get("description", "")
                    original_url = entry.get("link", "")
                    normalized_url = normalize_url(original_url)
                    if not title or not normalized_url:
                        continue
                    published_at = entry_datetime(entry)
                    fingerprint = hashlib.sha256(f"{title.lower()}|{urlparse(normalized_url).netloc}|{published_at.date() if published_at else ''}".encode()).hexdigest()
                    content = article_content(entry, normalized_url)
                    existing = db.query(NewsArticle).filter(
                        (NewsArticle.normalized_url == normalized_url) | (NewsArticle.content_fingerprint == fingerprint)
                    ).first()
                    if existing:
                        if content and not existing.content:
                            existing.content = content
                            existing.content_format = "html"
                            existing.ingestion_method = "rsshub" if is_rsshub_source(source) else "official_rss"
                        existing.status = publication_status(title, raw_description, content or existing.content)
                        result["duplicates"] += 1
                        continue
                    category, tags = classify(title, source.category)
                    db.add(NewsArticle(
                        source_id=source.id,
                        title=title,
                        title_original=title,
                        summary=plain_text(raw_description),
                        content=content,
                        content_format="html",
                        ingestion_method="rsshub" if is_rsshub_source(source) else "official_rss",
                        original_url=original_url,
                        normalized_url=normalized_url,
                        image_url=entry_image(entry),
                        category=category,
                        tags=tags,
                        language="zh" if re.search(r"[\u4e00-\u9fff]", title) else "en",
                        content_fingerprint=fingerprint,
                        status=publication_status(title, raw_description, content),
                        published_at=published_at,
                    ))
                    result["inserted"] += 1
                if stopped:
                    db.rollback()
                    result["inserted"] = inserted_before_source
                    result["duplicates"] = duplicates_before_source
                    break
                source.last_success_at = now
                source.last_error_message = None
                source.failure_count = 0
                result["succeeded"] += 1
                db.commit()
            except Exception as exc:
                db.rollback()
                source = db.get(NewsSource, source.id)
                source.last_error_at = now
                source.last_error_message = plain_text(str(exc), 500)
                source.failure_count += 1
                db.commit()
                result["failed"] += 1
    if not stopped:
        result["relevance"] = reassess_news(db)
        cache_delete_news()
    result["stopped"] = stopped
    return result
