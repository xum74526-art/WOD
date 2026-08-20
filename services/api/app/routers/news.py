import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import ContentFavorite, NewsArticle, NewsSource, User
from app.news_cache import cache_get, cache_set
from app.news_service import dedupe_article_images, remove_leading_feed_excerpt, remove_trailing_source_link, sync_news, trim_non_article_sections
from app.responses import ok
from app.security import ApiError, get_current_user, get_optional_user, require_authenticated_action

router = APIRouter(prefix="/api/v1", tags=["news"])

CURATED_VIDEOS = [
    {"id": "nvidia-gtc-2025", "video_id": "_waPvOwL9Z8", "title": "GTC 2025：Blackwell、AI Factory 与下一代算力基础设施", "summary": "NVIDIA CEO Jensen Huang 介绍 Blackwell GPU、规模化推理、AI Factory、Spectrum-X 与下一代数据中心路线。", "category": "hardware", "platform": "NVIDIA", "published_at": "2025-03-18", "duration": "2 小时以上"},
    {"id": "nvidia-ai-factory", "video_id": "t_jiScDhf3M", "title": "AI Factory：Blackwell 算力工厂如何构建", "summary": "了解 NVIDIA 如何使用 Blackwell、网络和数据中心组件组成可扩展的 AI Factory。", "category": "compute", "platform": "NVIDIA", "published_at": "2024-06-03", "duration": None},
    {"id": "amd-mi300x-memory", "video_id": "iYOrR3YjZiI", "title": "AMD MI300X：为什么更大显存能带来更快 AI 推理", "summary": "AMD Developer Central 解释 192GB HBM 如何缓解大模型推理的显存瓶颈，并影响吞吐与成本。", "category": "hardware", "platform": "AMD Developer Central", "published_at": "2025-08-04", "duration": None},
    {"id": "google-ai-infrastructure", "video_id": "jUZhe1aTnFk", "title": "Google Cloud AI 基础设施与 GPU 加速器选择", "summary": "Google Cloud 介绍 GPU、TPU 和超算基础设施，以及如何为机器学习工作负载选择加速器。", "category": "compute", "platform": "Google Cloud Tech", "published_at": "2020-09-15", "duration": None},
]


def video_out(video: dict, *, is_favorited: bool = False) -> dict:
    return {**video, "thumbnail_url": f"https://i.ytimg.com/vi/{video['video_id']}/hqdefault.jpg", "embed_url": f"https://www.youtube-nocookie.com/embed/{video['video_id']}", "original_url": f"https://www.youtube.com/watch?v={video['video_id']}", "content_type": "video", "is_favorited": is_favorited}


def serialize(article: NewsArticle, source: NewsSource, *, include_content: bool = True, is_favorited: bool = False) -> dict:
    # Existing stored articles predate the no-referrer sanitizer. Inject it at
    # response time so protected third-party images work without a data rewrite.
    content = trim_non_article_sections(article.content or "")
    content = re.sub(r"<img(?![^>]*\breferrerpolicy=)", '<img referrerpolicy="no-referrer"', content, flags=re.IGNORECASE)
    content = dedupe_article_images(content)
    content = remove_leading_feed_excerpt(content, article.summary)
    content = remove_trailing_source_link(content)
    return {
        "id": article.id, "title": article.title, "title_original": article.title_original,
        "summary": article.summary, "category": article.category, "tags": article.tags or [],
        "content": content if include_content else None, "content_format": article.content_format,
        "ingestion_method": article.ingestion_method,
        "content_type": "article", "video_duration": None,
        "image_url": article.image_url, "original_url": article.original_url,
        "published_at": article.published_at, "collected_at": article.collected_at,
        "view_count": article.view_count,
        "is_favorited": is_favorited,
        "source": {"name": source.name, "site_url": source.site_url, "is_official": source.is_official},
    }


def favorite_keys(db: Session, user: User | None) -> set[tuple[str, str]]:
    if not user:
        return set()
    return {
        (row.content_type, row.content_id)
        for row in db.query(ContentFavorite).filter(ContentFavorite.user_id == user.id).all()
    }


def published_timestamp(item: dict) -> float:
    value = item.get("published_at") or item.get("collected_at")
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return 0
    else:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def mixed_feed_items(db: Session, user: User | None) -> tuple[list[dict], list[dict]]:
    keys = favorite_keys(db, user)
    rows = db.query(NewsArticle, NewsSource).join(NewsSource).filter(NewsArticle.status == "published").all()
    articles = [
        serialize(article, source, include_content=False, is_favorited=("article", str(article.id)) in keys)
        for article, source in rows
    ]
    videos = [video_out(video, is_favorited=("video", video["id"]) in keys) for video in CURATED_VIDEOS]
    return articles, videos


def recommendation_categories(db: Session, user: User | None) -> set[str]:
    if not user:
        return set()
    favorites = db.query(ContentFavorite).filter(ContentFavorite.user_id == user.id).all()
    categories = {
        video["category"]
        for favorite in favorites if favorite.content_type == "video"
        for video in CURATED_VIDEOS if video["id"] == favorite.content_id
    }
    article_ids = [int(favorite.content_id) for favorite in favorites if favorite.content_type == "article" and favorite.content_id.isdigit()]
    if article_ids:
        categories.update(category for (category,) in db.query(NewsArticle.category).filter(NewsArticle.id.in_(article_ids)).all())
    return categories


def ranked_recommendations(db: Session, user: User | None) -> list[dict]:
    articles, videos = mixed_feed_items(db, user)
    preferred = recommendation_categories(db, user)
    now = datetime.now(timezone.utc).timestamp()

    def score(item: dict) -> float:
        age_days = max(0, (now - published_timestamp(item)) / 86400) if published_timestamp(item) else 3650
        freshness = max(0.0, 1.0 - age_days / 730)
        popularity = math.log1p(max(0, int(item.get("view_count") or 0))) / 8
        preference = 1.5 if item.get("category") in preferred else 0
        saved = 0.25 if item.get("is_favorited") else 0
        return round(preference + freshness + popularity + saved, 6)

    for item in articles + videos:
        item["recommendation_score"] = score(item)
    articles.sort(key=lambda item: (item["recommendation_score"], published_timestamp(item)), reverse=True)
    videos.sort(key=lambda item: (item["recommendation_score"], published_timestamp(item)), reverse=True)

    # Preserve content diversity: at most two articles before the next video.
    mixed: list[dict] = []
    while articles or videos:
        mixed.extend(articles[:2]); del articles[:2]
        if videos:
            mixed.append(videos.pop(0))
    return mixed


def validate_favorite_target(db: Session, content_type: str, content_id: str) -> None:
    if content_type == "article":
        if not content_id.isdigit() or not db.query(NewsArticle.id).filter(NewsArticle.id == int(content_id), NewsArticle.status == "published").first():
            raise ApiError("NEWS_NOT_FOUND", "资讯不存在或尚未发布", 404)
        return
    if content_type == "video":
        if not any(video["id"] == content_id for video in CURATED_VIDEOS):
            raise ApiError("VIDEO_NOT_FOUND", "视频不存在", 404)
        return
    raise ApiError("CONTENT_TYPE_INVALID", "只能收藏文章或视频", 422)


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
    payload = ok([serialize(article, news_source, include_content=False) for article, news_source in rows], {
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
    payload = ok([serialize(article, source, include_content=False) for article, source in rows], {"cache_status": "miss"})
    cache_set(cache_key, payload, 120)
    return payload


@router.get("/public/news/rsshub")
def rsshub_news(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    query = db.query(NewsArticle, NewsSource).join(NewsSource).filter(
        NewsArticle.status == "published", NewsArticle.ingestion_method == "rsshub"
    )
    total = query.count()
    rows = query.order_by(func.coalesce(NewsArticle.published_at, NewsArticle.collected_at).desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok([serialize(article, source, include_content=False) for article, source in rows], {
        "page": page, "page_size": page_size, "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    })


@router.get("/feed/recommended")
def recommended_feed(user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    items = ranked_recommendations(db, user)
    return ok(items, {
        "total": len(items),
        "ranking": "category_preference+freshness+popularity+content_diversity",
        "personalized": bool(user),
    })


@router.get("/feed/latest")
def latest_feed(
    content_type: str | None = Query(None, pattern="^(article|video)$"),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    articles, videos = mixed_feed_items(db, user)
    items = articles if content_type == "article" else videos if content_type == "video" else articles + videos
    items.sort(key=published_timestamp, reverse=True)
    return ok(items, {"total": len(items), "sort": "latest", "content_type": content_type or "all"})


@router.get("/favorites")
def list_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ContentFavorite).filter(ContentFavorite.user_id == user.id).order_by(ContentFavorite.created_at.desc()).all()
    article_ids = [int(row.content_id) for row in rows if row.content_type == "article" and row.content_id.isdigit()]
    article_map = {
        str(article.id): serialize(article, source, include_content=False, is_favorited=True)
        for article, source in db.query(NewsArticle, NewsSource).join(NewsSource).filter(
            NewsArticle.status == "published", NewsArticle.id.in_(article_ids)
        ).all()
    } if article_ids else {}
    video_map = {video["id"]: video_out(video, is_favorited=True) for video in CURATED_VIDEOS}
    items = []
    for row in rows:
        item = article_map.get(row.content_id) if row.content_type == "article" else video_map.get(row.content_id)
        if item:
            items.append({**item, "favorited_at": row.created_at})
    return ok(items, {"total": len(items)})


@router.post("/favorites/{content_type}/{content_id}", status_code=201)
def add_favorite(content_type: str, content_id: str, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    validate_favorite_target(db, content_type, content_id)
    favorite = db.query(ContentFavorite).filter(
        ContentFavorite.user_id == user.id,
        ContentFavorite.content_type == content_type,
        ContentFavorite.content_id == content_id,
    ).first()
    if not favorite:
        favorite = ContentFavorite(user_id=user.id, content_type=content_type, content_id=content_id)
        db.add(favorite); db.commit(); db.refresh(favorite)
    return ok({"content_type": content_type, "content_id": content_id, "is_favorited": True, "favorited_at": favorite.created_at})


@router.delete("/favorites/{content_type}/{content_id}")
def remove_favorite(content_type: str, content_id: str, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    favorite = db.query(ContentFavorite).filter(
        ContentFavorite.user_id == user.id,
        ContentFavorite.content_type == content_type,
        ContentFavorite.content_id == content_id,
    ).first()
    if favorite:
        db.delete(favorite); db.commit()
    return ok({"content_type": content_type, "content_id": content_id, "is_favorited": False})


@router.get("/public/videos")
def public_videos(user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    keys = favorite_keys(db, user)
    return ok([video_out(video, is_favorited=("video", video["id"]) in keys) for video in CURATED_VIDEOS], {"total": len(CURATED_VIDEOS), "selection": "official_sources"})


@router.get("/public/videos/{video_id}")
def public_video_detail(video_id: str, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    video = next((item for item in CURATED_VIDEOS if item["id"] == video_id), None)
    if not video:
        raise ApiError("VIDEO_NOT_FOUND", "视频不存在", 404)
    return ok(video_out(video, is_favorited=("video", video_id) in favorite_keys(db, user)))


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
def news_detail(article_id: int, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    cache_key = f"news:detail:{article_id}"
    cached = cache_get(cache_key) if not user else None
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
    payload = ok(serialize(article, source, is_favorited=("article", str(article.id)) in favorite_keys(db, user)), {"cache_status": "miss"})
    if not user:
        cache_set(cache_key, payload, 900)
    return payload


@router.post("/internal/news/sync")
def manual_sync(user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise ApiError("ADMIN_REQUIRED", "仅管理员可以手动同步资讯", 403)
    return ok(sync_news(db))
