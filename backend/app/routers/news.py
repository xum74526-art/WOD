import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import NewsArticle, NewsSource, User
from app.news_cache import cache_get, cache_set
from app.news_service import sync_news, trim_non_article_sections
from app.responses import ok
from app.security import ApiError, require_csrf

router = APIRouter(prefix="/api/v1", tags=["news"])

CURATED_VIDEOS = [
    {"id": "nvidia-gtc-2025", "video_id": "_waPvOwL9Z8", "title": "GTC 2025：Blackwell、AI Factory 与下一代算力基础设施", "summary": "NVIDIA CEO Jensen Huang 介绍 Blackwell GPU、规模化推理、AI Factory、Spectrum-X 与下一代数据中心路线。", "category": "hardware", "platform": "NVIDIA", "published_at": "2025-03-18", "duration": "2 小时以上"},
    {"id": "nvidia-ai-factory", "video_id": "t_jiScDhf3M", "title": "AI Factory：Blackwell 算力工厂如何构建", "summary": "了解 NVIDIA 如何使用 Blackwell、网络和数据中心组件组成可扩展的 AI Factory。", "category": "compute", "platform": "NVIDIA", "published_at": "2024-06-03", "duration": None},
    {"id": "amd-mi300x-memory", "video_id": "iYOrR3YjZiI", "title": "AMD MI300X：为什么更大显存能带来更快 AI 推理", "summary": "AMD Developer Central 解释 192GB HBM 如何缓解大模型推理的显存瓶颈，并影响吞吐与成本。", "category": "hardware", "platform": "AMD Developer Central", "published_at": "2025-08-04", "duration": None},
    {"id": "google-ai-infrastructure", "video_id": "jUZhe1aTnFk", "title": "Google Cloud AI 基础设施与 GPU 加速器选择", "summary": "Google Cloud 介绍 GPU、TPU 和超算基础设施，以及如何为机器学习工作负载选择加速器。", "category": "compute", "platform": "Google Cloud Tech", "published_at": "2020-09-15", "duration": None},
]


def video_out(video: dict) -> dict:
    return {**video, "thumbnail_url": f"https://i.ytimg.com/vi/{video['video_id']}/hqdefault.jpg", "embed_url": f"https://www.youtube-nocookie.com/embed/{video['video_id']}", "original_url": f"https://www.youtube.com/watch?v={video['video_id']}", "content_type": "video"}


def serialize(article: NewsArticle, source: NewsSource) -> dict:
    # Existing stored articles predate the no-referrer sanitizer. Inject it at
    # response time so protected third-party images work without a data rewrite.
    content = trim_non_article_sections(article.content or "")
    content = re.sub(r"<img(?![^>]*\breferrerpolicy=)", '<img referrerpolicy="no-referrer"', content, flags=re.IGNORECASE)
    return {
        "id": article.id, "title": article.title, "title_original": article.title_original,
        "summary": article.summary, "category": article.category, "tags": article.tags or [],
        "content": content, "content_format": article.content_format,
        "ingestion_method": article.ingestion_method,
        "content_type": "article", "video_duration": None,
        "image_url": article.image_url, "original_url": article.original_url,
        "published_at": article.published_at, "collected_at": article.collected_at,
        "view_count": article.view_count,
        "source": {"name": source.name, "site_url": source.site_url, "is_official": source.is_official},
    }


@router.get("/public/news")
def news_list(
    page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=50),
    category: str | None = Query(None, max_length=32), source: str | None = Query(None, max_length=128),
    q: str | None = Query(None, max_length=100), sort: str = Query("latest", pattern="^(latest|popular)$"),
    db: Session = Depends(get_db),
):
    cache_key = f"news:list:{sort}:{category or 'all'}:{source or 'all'}:{q or ''}:{page}:{page_size}"
    cached = cache_get(cache_key)
    if cached:
        cached["meta"]["cache_status"] = "hit"
        return cached
    query = db.query(NewsArticle, NewsSource).join(NewsSource).filter(NewsArticle.status == "published")
    if category:
        query = query.filter(NewsArticle.category == category)
    if source:
        query = query.filter(NewsSource.name == source)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(NewsArticle.title.ilike(term), NewsArticle.summary.ilike(term), NewsSource.name.ilike(term)))
    total = query.count()
    order = NewsArticle.view_count.desc() if sort == "popular" else func.coalesce(NewsArticle.published_at, NewsArticle.collected_at).desc()
    rows = query.order_by(order).offset((page - 1) * page_size).limit(page_size).all()
    payload = ok([serialize(article, news_source) for article, news_source in rows], {
        "page": page, "page_size": page_size, "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
        "cache_status": "miss", "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    cache_set(cache_key, payload)
    return payload


@router.get("/public/news/trending")
def trending(db: Session = Depends(get_db)):
    cache_key = "news:trending"
    cached = cache_get(cache_key)
    if cached:
        cached["meta"]["cache_status"] = "hit"
        return cached
    rows = db.query(NewsArticle, NewsSource).join(NewsSource).filter(NewsArticle.status == "published").order_by(
        NewsArticle.view_count.desc(), func.coalesce(NewsArticle.published_at, NewsArticle.collected_at).desc()
    ).limit(5).all()
    payload = ok([serialize(article, source) for article, source in rows], {"cache_status": "miss"})
    cache_set(cache_key, payload, 120)
    return payload


@router.get("/public/news/rsshub")
def rsshub_news(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    query = db.query(NewsArticle, NewsSource).join(NewsSource).filter(
        NewsArticle.status == "published", NewsArticle.ingestion_method == "rsshub"
    )
    total = query.count()
    rows = query.order_by(func.coalesce(NewsArticle.published_at, NewsArticle.collected_at).desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok([serialize(article, source) for article, source in rows], {
        "page": page, "page_size": page_size, "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    })


@router.get("/public/videos")
def public_videos():
    return ok([video_out(video) for video in CURATED_VIDEOS], {"total": len(CURATED_VIDEOS), "selection": "official_sources"})


@router.get("/public/videos/{video_id}")
def public_video_detail(video_id: str):
    video = next((item for item in CURATED_VIDEOS if item["id"] == video_id), None)
    if not video:
        raise ApiError("VIDEO_NOT_FOUND", "视频不存在", 404)
    return ok(video_out(video))


@router.get("/public/news/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.query(NewsArticle.category, func.count(NewsArticle.id)).filter(NewsArticle.status == "published").group_by(NewsArticle.category).all()
    return ok([{"slug": category, "count": count} for category, count in rows])


@router.get("/public/news/sources")
def sources(db: Session = Depends(get_db)):
    rows = db.query(NewsSource).filter(NewsSource.enabled.is_(True)).order_by(NewsSource.name).all()
    return ok([{"name": row.name, "site_url": row.site_url, "is_official": row.is_official,
                "last_success_at": row.last_success_at, "failure_count": row.failure_count} for row in rows])


@router.get("/public/news/{article_id}")
def news_detail(article_id: int, db: Session = Depends(get_db)):
    cache_key = f"news:detail:{article_id}"
    cached = cache_get(cache_key)
    if cached:
        cached["meta"]["cache_status"] = "hit"
        return cached
    row = db.query(NewsArticle, NewsSource).join(NewsSource).filter(
        NewsArticle.id == article_id, NewsArticle.status == "published"
    ).first()
    if not row:
        raise ApiError("NEWS_NOT_FOUND", "资讯不存在或尚未发布", 404)
    article, source = row
    article.view_count += 1
    db.commit()
    payload = ok(serialize(article, source), {"cache_status": "miss"})
    cache_set(cache_key, payload, 900)
    return payload


@router.post("/internal/news/sync")
def manual_sync(user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise ApiError("ADMIN_REQUIRED", "仅管理员可以手动同步资讯", 403)
    return ok(sync_news(db))
