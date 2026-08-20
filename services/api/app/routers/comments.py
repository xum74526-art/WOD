import hashlib
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import ArticleComment, CommentReport, CommentRestriction, NewsArticle, User
from app.responses import ok
from app.schemas import CommentIn, CommentModerationIn, CommentReportIn
from app.security import (
    ApiError,
    get_optional_user,
    require_admin,
    require_admin_action,
    require_authenticated_action,
)

router = APIRouter(prefix="/api/v1", tags=["comments"])
LINK_RE = re.compile(r"(?:https?://|www\.|[a-z0-9-]+\.(?:com|cn|net|org)\b)", re.I)
CONTACT_RE = re.compile(r"(?:1[3-9]\d{9}|[\w.+-]+@[\w.-]+\.\w+|(?:微信|vx|v信|qq)\s*[:：]?\s*[\w-]{5,})", re.I)
BLOCK_RULES = {"广告与引流": ("加微信", "代理加盟", "稳赚", "返利", "扫码联系"), "辱骂与攻击": ("傻逼", "废物", "去死", "脑残"), "色情低俗": ("色情", "裸聊", "成人视频"), "违法危险内容": ("代开发票", "买卖账号", "枪支", "毒品")}
ASYNC_RULES = {"垃圾内容与刷屏": ("顶顶顶", "111111", "哈哈哈哈哈哈哈哈"), "其他不当内容": ("恶意攻击", "煽动仇恨")}
REPORT_REASONS = {"广告与引流", "辱骂与攻击", "色情低俗", "违法危险内容", "隐私或联系方式", "垃圾内容与刷屏", "其他不当内容"}


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def fingerprint(value: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", value).lower().encode()).hexdigest()


def quick_precheck(content: str) -> tuple[str, str | None]:
    value = content.strip()
    if not value:
        raise ApiError("COMMENT_EMPTY", "请输入留言内容", 422)
    if LINK_RE.search(value): return value, "广告与引流"
    if CONTACT_RE.search(value): return value, "隐私或联系方式"
    if sum(not char.isalnum() and not char.isspace() for char in value) > max(12, len(value) * 0.35): return value, "垃圾内容与刷屏"
    lowered = value.lower()
    for category, words in BLOCK_RULES.items():
        if any(word in lowered for word in words): return value, category
    return value, None


def serialize_comment(comment: ArticleComment, author: User, viewer: User | None = None, reports: int = 0) -> dict:
    own = bool(viewer and viewer.id == comment.user_id)
    privileged = own or bool(viewer and viewer.role == "admin")
    return {"id": comment.id, "content": comment.content, "status": comment.status if privileged else "visible", "violation_category": comment.violation_category if privileged else None, "created_at": comment.created_at, "updated_at": comment.updated_at, "is_own": own, "report_count": reports if viewer and viewer.role == "admin" else None, "author": {"display_name": author.display_name, "avatar_initial": author.display_name[:1].upper()}}


def async_review(comment_id: int) -> None:
    with SessionLocal() as db:
        comment = db.get(ArticleComment, comment_id)
        if not comment or comment.status != "checking": return
        lowered = comment.content.lower()
        for category, words in ASYNC_RULES.items():
            if any(word in lowered for word in words):
                comment.status = "hidden"; comment.violation_category = category; comment.moderation_note = "自动复审未通过"
                break
        else: comment.status = "visible"
        db.commit()


@router.get("/public/news/{article_id}/comments")
def comment_list(article_id: int, sort: str = Query("latest", pattern="^(latest|oldest)$"), user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    if not db.query(NewsArticle.id).filter(NewsArticle.id == article_id, NewsArticle.status == "published").first(): raise ApiError("NEWS_NOT_FOUND", "资讯不存在或尚未发布", 404)
    query = db.query(ArticleComment, User).join(User, User.id == ArticleComment.user_id).filter(ArticleComment.article_id == article_id)
    if user and user.role == "admin": query = query.filter(ArticleComment.status != "deleted")
    elif user: query = query.filter(or_(ArticleComment.status == "visible", ArticleComment.user_id == user.id)).filter(ArticleComment.status != "deleted")
    else: query = query.filter(ArticleComment.status == "visible")
    order = ArticleComment.created_at.asc() if sort == "oldest" else ArticleComment.created_at.desc()
    rows = query.order_by(order).limit(200).all()
    count = db.query(func.count(ArticleComment.id)).filter(ArticleComment.article_id == article_id, ArticleComment.status == "visible").scalar() or 0
    return ok([serialize_comment(c, author, user) for c, author in rows], {"visible_count": count, "sort": sort})


@router.post("/news/{article_id}/comments", status_code=201)
def create_comment(article_id: int, data: CommentIn, tasks: BackgroundTasks, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    if not db.query(NewsArticle.id).filter(NewsArticle.id == article_id, NewsArticle.status == "published").first(): raise ApiError("NEWS_NOT_FOUND", "资讯不存在或尚未发布", 404)
    now = datetime.now(timezone.utc); restriction = db.get(CommentRestriction, user.id)
    if restriction and aware(restriction.restricted_until) > now: raise ApiError("COMMENT_RESTRICTED", "留言功能暂时受限，请稍后再试", 429)
    last = db.query(ArticleComment).filter(ArticleComment.user_id == user.id).order_by(ArticleComment.created_at.desc()).first()
    if last and (now - aware(last.created_at)).total_seconds() < 15: raise ApiError("COMMENT_RATE_LIMIT", "发布过于频繁，请稍后再试", 429)
    if db.query(ArticleComment).filter(ArticleComment.user_id == user.id, ArticleComment.created_at >= now - timedelta(hours=1)).count() >= 20: raise ApiError("COMMENT_RATE_LIMIT", "发布过于频繁，请稍后再试", 429)
    if db.query(ArticleComment).filter(ArticleComment.user_id == user.id, ArticleComment.created_at >= now - timedelta(days=1)).count() >= 100: raise ApiError("COMMENT_RATE_LIMIT", "今日留言次数已达上限", 429)
    content, violation = quick_precheck(data.content)
    if violation: raise ApiError("COMMENT_PRECHECK_FAILED", "留言包含不适合公开展示的内容，请修改后重试。", 422)
    digest = fingerprint(content)
    if db.query(ArticleComment.id).filter(ArticleComment.user_id == user.id, ArticleComment.content_fingerprint == digest, ArticleComment.status != "deleted").first(): raise ApiError("COMMENT_DUPLICATE", "请勿重复提交相同留言", 409)
    comment = ArticleComment(article_id=article_id, user_id=user.id, content=content, content_fingerprint=digest, status="checking")
    db.add(comment); db.commit(); db.refresh(comment); tasks.add_task(async_review, comment.id)
    return ok(serialize_comment(comment, user, user))


@router.put("/comments/{comment_id}")
def revise_comment(comment_id: int, data: CommentIn, tasks: BackgroundTasks, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    comment = db.query(ArticleComment).filter(ArticleComment.id == comment_id, ArticleComment.user_id == user.id).first()
    if not comment or comment.status not in {"hidden", "pending_manual"}: raise ApiError("COMMENT_NOT_EDITABLE", "该留言当前不能修改", 409)
    content, violation = quick_precheck(data.content)
    if violation: raise ApiError("COMMENT_PRECHECK_FAILED", "留言包含不适合公开展示的内容，请修改后重试。", 422)
    comment.content = content; comment.content_fingerprint = fingerprint(content); comment.status = "checking"; comment.violation_category = None; comment.moderation_note = None
    db.commit(); tasks.add_task(async_review, comment.id)
    return ok(serialize_comment(comment, user, user))


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    comment = db.query(ArticleComment).filter(ArticleComment.id == comment_id, ArticleComment.user_id == user.id).first()
    if not comment or comment.status == "deleted": raise ApiError("COMMENT_NOT_FOUND", "留言不存在", 404)
    comment.status = "deleted"; comment.deleted_at = datetime.now(timezone.utc); db.commit()
    return ok({"deleted": True})


@router.post("/comments/{comment_id}/reports", status_code=201)
def report_comment(comment_id: int, data: CommentReportIn, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    if data.reason not in REPORT_REASONS: raise ApiError("REPORT_REASON_INVALID", "请选择有效的举报原因", 422)
    comment = db.query(ArticleComment).filter(ArticleComment.id == comment_id, ArticleComment.status == "visible").first()
    if not comment or comment.user_id == user.id: raise ApiError("COMMENT_NOT_REPORTABLE", "该留言无法举报", 409)
    if db.query(CommentReport.id).filter(CommentReport.comment_id == comment_id, CommentReport.reporter_id == user.id).first(): raise ApiError("REPORT_EXISTS", "你已经举报过该留言", 409)
    db.add(CommentReport(comment_id=comment_id, reporter_id=user.id, reason=data.reason, detail=data.detail))
    if db.query(CommentReport).filter(CommentReport.comment_id == comment_id, CommentReport.status == "open").count() + 1 >= 3: comment.status = "pending_manual"; comment.violation_category = "其他不当内容"
    db.commit(); return ok({"reported": True})


@router.get("/admin/comments")
def admin_comments(status: str | None = None, category: str | None = None, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(ArticleComment, User).join(User, User.id == ArticleComment.user_id)
    if status: query = query.filter(ArticleComment.status == status)
    if category: query = query.filter(ArticleComment.violation_category == category)
    rows = query.order_by(ArticleComment.created_at.desc()).limit(500).all()
    return ok([serialize_comment(c, author, user, db.query(CommentReport).filter(CommentReport.comment_id == c.id).count()) for c, author in rows])


@router.patch("/admin/comments/{comment_id}")
def moderate_comment(comment_id: int, data: CommentModerationIn, user: User = Depends(require_admin_action), db: Session = Depends(get_db)):
    comment = db.get(ArticleComment, comment_id)
    if not comment: raise ApiError("COMMENT_NOT_FOUND", "留言不存在", 404)
    comment.status = data.status; comment.violation_category = data.violation_category; comment.moderation_note = data.note
    if data.status == "deleted": comment.deleted_at = datetime.now(timezone.utc)
    db.commit(); return ok({"id": comment.id, "status": comment.status})
