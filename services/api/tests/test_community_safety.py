import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import (
    get_current_platform,
    get_current_user,
    get_optional_current_user,
    require_admin,
)
from app.core.config import Settings, settings
from app.db.base import Base
from app.db.session import get_db
from app.models import CommunityBlock, CommunityReport, Comment, ContentSource, Follow, Like, Post, User
from app.routers import admin as admin_router
from app.routers import community as community_router
from app.schemas.community import CommunityReportIn, CommunityReportReviewIn
from app.utils.response import BizError, error
from init_db import _ensure_columns


class CommunitySafetyEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

        self.author = User(
            phone="13981000001", username="内容作者", password="!",
        )
        self.reporters = [
            User(phone=f"1398100000{index}", username=f"举报用户{index}", password="!")
            for index in range(2, 5)
        ]
        self.viewer = User(
            phone="13981000005", username="普通读者", password="!",
        )
        self.other_author = User(
            phone="13981000006", username="其他作者", password="!",
        )
        self.admin = User(
            phone="13981000007", username="审核管理员", password="!", role="admin",
        )
        self.db.add_all([
            self.author,
            *self.reporters,
            self.viewer,
            self.other_author,
            self.admin,
        ])
        self.db.flush()

        self.author_post = Post(
            user_id=self.author.id,
            content="作者公开动态",
            origin="user",
            content_type="text",
        )
        self.other_post = Post(
            user_id=self.other_author.id,
            content="其他作者动态",
            origin="user",
            content_type="text",
            comments=1,
        )
        self.viewer_post = Post(
            user_id=self.viewer.id,
            content="普通读者动态",
            origin="user",
            content_type="text",
        )
        self.db.add_all([self.author_post, self.other_post, self.viewer_post])
        self.db.flush()
        self.author_comment = Comment(
            post_id=self.other_post.id,
            user_id=self.author.id,
            content="作者留在其他动态下的评论",
        )
        self.db.add(self.author_comment)
        self.db.commit()

        self.current_user_id = self.viewer.id
        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(_request: Request, exc: BizError):
            return JSONResponse(
                status_code=exc.status_code,
                content=error(exc.msg, exc.code),
            )

        app.include_router(community_router.router)
        app.include_router(admin_router.router)

        def db_override():
            yield self.db

        def user_override():
            return self.db.get(User, self.current_user_id)

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = user_override
        app.dependency_overrides[get_optional_current_user] = user_override
        app.dependency_overrides[get_current_platform] = lambda: "ios"
        app.dependency_overrides[require_admin] = lambda: self.db.get(User, self.admin.id)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def use_user(self, user: User):
        self.current_user_id = user.id

    def visible_post_ids(self) -> list[int]:
        response = self.client.get("/api/community/posts?page_size=50")
        self.assertEqual(response.status_code, 200, response.text)
        return [item["id"] for item in response.json()["data"]["items"]]

    def visible_comment_ids(self, post_id: int) -> list[int]:
        response = self.client.get(f"/api/community/posts/{post_id}/comments")
        self.assertEqual(response.status_code, 200, response.text)
        return [item["id"] for item in response.json()["data"]]

    def report(self, reporter: User, target_type: str, target_id: int, **extra):
        self.use_user(reporter)
        return self.client.post(
            "/api/community/reports",
            json={
                "target_type": target_type,
                "target_id": target_id,
                "reason": extra.pop("reason", "harassment"),
                **extra,
            },
        )

    def test_public_post_and_comment_text_are_filtered_before_persistence(self):
        self.use_user(self.viewer)
        accepted = self.client.post(
            "/api/community/posts",
            json={"content": "  正常的社区分享  ", "topic": "  GPU 交流  "},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["data"]["content"], "正常的社区分享")
        self.assertEqual(accepted.json()["data"]["topic"], "GPU 交流")

        rejected_values = (
            "-----BEGIN PRIVATE KEY----- secret",
            "我的身份证是11010519491231002X",
            "这里可以代办假证",
            "go kill yourself",
        )
        for content in rejected_values:
            with self.subTest(content=content):
                response = self.client.post(
                    "/api/community/posts", json={"content": content},
                )
                self.assertEqual(response.status_code, 400, response.text)

        blocked_comment = self.client.post(
            f"/api/community/posts/{self.other_post.id}/comments",
            json={"content": "出售毒品请联系我"},
        )
        self.assertEqual(blocked_comment.status_code, 400, blocked_comment.text)
        self.assertEqual(
            self.db.query(Post).filter(Post.user_id == self.viewer.id).count(),
            2,
        )
        self.assertEqual(
            self.db.query(Comment).filter(Comment.user_id == self.viewer.id).count(),
            0,
        )

        out_of_scope_posts = (
            "转载新闻：某公共事务最新进展",
            "突发事件报道：现场情况持续更新",
            "Breaking news about current affairs",
        )
        for content in out_of_scope_posts:
            with self.subTest(content=content):
                response = self.client.post(
                    "/api/community/posts",
                    json={"content": content, "topic": "GPU 交流"},
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("社区仅限算力产品", response.text)

    def test_text_post_returns_success_and_inserts_exactly_one_row(self):
        before = self.db.query(Post).filter(Post.user_id == self.viewer.id).count()
        response = self.client.post(
            "/api/community/posts",
            json={"content": "首版文字动态", "topic": "发布验证"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        created_id = response.json()["data"]["id"]
        self.assertEqual(
            self.db.query(Post).filter(Post.user_id == self.viewer.id).count(),
            before + 1,
        )
        self.assertEqual(
            self.db.query(Post).filter(Post.id == created_id).count(),
            1,
        )

    def test_aggregated_content_requires_server_policy_for_list_and_detail(self):
        source = ContentSource(
            key="review-source",
            name="审核来源",
            kind="article",
            endpoint="https://example.com/feed",
            rights_status="allowed",
            enabled=True,
        )
        self.db.add(source)
        self.db.flush()
        aggregated = Post(
            user_id=self.author.id,
            content="第三方聚合内容",
            origin="aggregated",
            content_type="article",
            source_key=source.key,
        )
        self.db.add(aggregated)
        self.db.commit()

        self.assertFalse(
            Settings.model_fields["COMMUNITY_AGGREGATED_CONTENT_ENABLED"].default,
        )
        with patch.object(settings, "COMMUNITY_AGGREGATED_CONTENT_ENABLED", False):
            forced = self.client.get(
                "/api/community/posts?page_size=50&allow_aggregated=true",
            )
            detail = self.client.get(f"/api/community/posts/{aggregated.id}")
        self.assertEqual(forced.status_code, 200)
        self.assertNotIn(
            aggregated.id,
            [item["id"] for item in forced.json()["data"]["items"]],
        )
        self.assertEqual(detail.status_code, 404)

        with patch.object(settings, "COMMUNITY_AGGREGATED_CONTENT_ENABLED", True):
            client_opt_out = self.client.get("/api/community/posts?page_size=50")
            server_and_client_opt_in = self.client.get(
                "/api/community/posts?page_size=50&allow_aggregated=true",
            )
            allowed_detail = self.client.get(f"/api/community/posts/{aggregated.id}")
        self.assertNotIn(
            aggregated.id,
            [item["id"] for item in client_opt_out.json()["data"]["items"]],
        )
        self.assertIn(
            aggregated.id,
            [item["id"] for item in server_and_client_opt_in.json()["data"]["items"]],
        )
        self.assertEqual(allowed_detail.status_code, 200)

    def test_review_policy_hides_historical_user_media_from_reads_and_interactions(self):
        image_post = Post(
            user_id=self.author.id,
            content="历史图片动态",
            origin="user",
            content_type="image",
            images='["/uploads/community/1/00000000000000000000000000000000.jpg"]',
        )
        video_post = Post(
            user_id=self.author.id,
            content="历史视频动态",
            origin="user",
            content_type="video",
            video="/uploads/community/1/00000000000000000000000000000000.mp4",
        )
        disguised_media_post = Post(
            user_id=self.author.id,
            content="带媒体字段的历史文本动态",
            origin="user",
            content_type="text",
            images='["/uploads/community/1/11111111111111111111111111111111.jpg"]',
        )
        self.db.add_all([image_post, video_post, disguised_media_post])
        self.db.commit()
        media_post_ids = {image_post.id, video_post.id, disguised_media_post.id}

        self.assertFalse(
            Settings.model_fields["COMMUNITY_USER_MEDIA_ENABLED"].default,
        )
        with patch.object(settings, "COMMUNITY_USER_MEDIA_ENABLED", False):
            feed = self.client.get("/api/community/posts?page_size=50")
            self.assertEqual(feed.status_code, 200, feed.text)
            visible_ids = {item["id"] for item in feed.json()["data"]["items"]}
            self.assertTrue(media_post_ids.isdisjoint(visible_ids))

            for post_id in media_post_ids:
                with self.subTest(post_id=post_id):
                    detail = self.client.get(f"/api/community/posts/{post_id}")
                    comments = self.client.get(
                        f"/api/community/posts/{post_id}/comments",
                    )
                    like = self.client.post(
                        f"/api/community/posts/{post_id}/like",
                        json={"liked": True},
                    )
                    comment = self.client.post(
                        f"/api/community/posts/{post_id}/comments",
                        json={"content": "不应写入隐藏动态"},
                    )
                    self.assertEqual(detail.status_code, 404, detail.text)
                    self.assertEqual(comments.status_code, 404, comments.text)
                    self.assertEqual(like.status_code, 404, like.text)
                    self.assertEqual(comment.status_code, 404, comment.text)

        self.assertEqual(
            self.db.query(Like).filter(Like.post_id.in_(media_post_ids)).count(),
            0,
        )
        self.assertEqual(
            self.db.query(Comment).filter(Comment.post_id.in_(media_post_ids)).count(),
            0,
        )

        with patch.object(settings, "COMMUNITY_USER_MEDIA_ENABLED", True):
            feed = self.client.get("/api/community/posts?page_size=50")
            visible_ids = {item["id"] for item in feed.json()["data"]["items"]}
            self.assertTrue(media_post_ids.issubset(visible_ids))
            for post_id in media_post_ids:
                self.assertEqual(
                    self.client.get(f"/api/community/posts/{post_id}").status_code,
                    200,
                )

    def test_public_community_output_hides_avatars_and_sanitizes_legacy_names(self):
        self.author.username = "代办假证"
        self.author.avatar = "/user/avatars/avatar_1.png?v=unsafe"
        self.db.commit()

        feed = self.client.get("/api/community/posts?page_size=50")
        self.assertEqual(feed.status_code, 200, feed.text)
        post = next(
            item for item in feed.json()["data"]["items"]
            if item["id"] == self.author_post.id
        )
        self.assertEqual(post["author_name"], "社区用户")
        self.assertIsNone(post["author_avatar"])

        comments = self.client.get(
            f"/api/community/posts/{self.other_post.id}/comments",
        )
        self.assertEqual(comments.status_code, 200, comments.text)
        comment = next(
            item for item in comments.json()["data"]
            if item["id"] == self.author_comment.id
        )
        self.assertEqual(comment["author_name"], "社区用户")

    def test_feed_output_queries_remain_bounded_as_page_size_grows(self):
        def feed_query_count() -> int:
            count = 0

            def record_query(*_args):
                nonlocal count
                count += 1

            event.listen(self.engine, "before_cursor_execute", record_query)
            try:
                response = self.client.get("/api/community/posts?page_size=50")
                self.assertEqual(response.status_code, 200, response.text)
            finally:
                event.remove(self.engine, "before_cursor_execute", record_query)
            return count

        baseline_queries = feed_query_count()
        self.db.add_all([
            Post(
                user_id=self.author.id,
                content=f"批量预取动态 {index}",
                origin="user",
                content_type="text",
            )
            for index in range(20)
        ])
        self.db.commit()
        expanded_queries = feed_query_count()

        self.assertLessEqual(expanded_queries, baseline_queries + 1)

    def test_reports_are_idempotent_hidden_for_reporter_and_auto_hide_at_three(self):
        first = self.report(
            self.reporters[0], "post", self.author_post.id,
            details="  恶意骚扰  ",
        )
        retried = self.report(
            self.reporters[0], "post", self.author_post.id,
            details="重复提交不应新增记录",
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(
            first.json()["data"]["report_id"],
            retried.json()["data"]["report_id"],
        )
        self.assertEqual(self.db.query(CommunityReport).count(), 1)
        stored = self.db.query(CommunityReport).one()
        self.assertEqual(stored.details, "恶意骚扰")
        self.assertNotIn(self.author_post.id, self.visible_post_ids())

        self.use_user(self.viewer)
        self.assertIn(self.author_post.id, self.visible_post_ids())
        second = self.report(self.reporters[1], "post", self.author_post.id)
        self.assertEqual(second.status_code, 200, second.text)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "visible")

        third = self.report(self.reporters[2], "post", self.author_post.id)
        self.assertEqual(third.status_code, 200, third.text)
        self.assertEqual(self.db.query(CommunityReport).count(), 3)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "pending_review")
        self.assertEqual(self.author_post.moderation_reason, "multiple_user_reports")

        self.use_user(self.viewer)
        self.assertNotIn(self.author_post.id, self.visible_post_ids())
        detail = self.client.get(f"/api/community/posts/{self.author_post.id}")
        self.assertEqual(detail.status_code, 404, detail.text)

    def test_blocking_removes_the_users_posts_comments_and_follow_relationships(self):
        self.db.add_all([
            Follow(follower_id=self.viewer.id, following_id=self.author.id),
            Follow(follower_id=self.author.id, following_id=self.viewer.id),
        ])
        self.db.commit()
        self.use_user(self.viewer)
        self.assertIn(self.author_post.id, self.visible_post_ids())
        self.assertIn(
            self.author_comment.id,
            self.visible_comment_ids(self.other_post.id),
        )

        blocked = self.client.post(
            f"/api/community/users/{self.author.id}/block",
            json={"blocked": True},
        )
        self.assertEqual(blocked.status_code, 200, blocked.text)
        self.assertEqual(blocked.json()["data"], {"blocked": True})
        self.assertEqual(self.db.query(CommunityBlock).count(), 1)
        self.assertEqual(self.db.query(Follow).count(), 0)
        self.assertNotIn(self.author_post.id, self.visible_post_ids())
        self.assertNotIn(
            self.author_comment.id,
            self.visible_comment_ids(self.other_post.id),
        )
        detail = self.client.get(f"/api/community/posts/{self.author_post.id}")
        self.assertEqual(detail.status_code, 404, detail.text)

        # A block is mutual for visibility and interactions even though only
        # the user who created it can remove the relationship.
        self.use_user(self.author)
        self.assertNotIn(self.viewer_post.id, self.visible_post_ids())
        reverse_detail = self.client.get(
            f"/api/community/posts/{self.viewer_post.id}"
        )
        reverse_comment = self.client.post(
            f"/api/community/posts/{self.viewer_post.id}/comments",
            json={"content": "被拉黑后不能继续互动"},
        )
        reverse_like = self.client.post(
            f"/api/community/posts/{self.viewer_post.id}/like",
            json={"liked": True},
        )
        reverse_follow = self.client.post(
            f"/api/community/users/{self.viewer.id}/follow",
            json={"following": True},
        )
        self.assertEqual(reverse_detail.status_code, 404, reverse_detail.text)
        self.assertEqual(reverse_comment.status_code, 404, reverse_comment.text)
        self.assertEqual(reverse_like.status_code, 404, reverse_like.text)
        self.assertEqual(reverse_follow.status_code, 400, reverse_follow.text)

        self.use_user(self.viewer)
        repeated = self.client.post(
            f"/api/community/users/{self.author.id}/block",
            json={"blocked": True},
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(self.db.query(CommunityBlock).count(), 1)

        unblocked = self.client.post(
            f"/api/community/users/{self.author.id}/block",
            json={"blocked": False},
        )
        self.assertEqual(unblocked.json()["data"], {"blocked": False})
        self.assertIn(self.author_post.id, self.visible_post_ids())
        self.assertIn(
            self.author_comment.id,
            self.visible_comment_ids(self.other_post.id),
        )
        self.use_user(self.author)
        self.assertIn(self.viewer_post.id, self.visible_post_ids())

    def test_authors_can_delete_their_own_posts_and_comments_idempotently(self):
        self.use_user(self.author)
        comment_response = self.client.post(
            f"/api/community/posts/{self.author_post.id}/comments",
            json={"content": "稍后由作者删除的评论"},
        )
        self.assertEqual(comment_response.status_code, 200, comment_response.text)
        comment_id = comment_response.json()["data"]["id"]
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.comments, 1)

        reported = self.report(self.viewer, "comment", comment_id)
        self.assertEqual(reported.status_code, 200, reported.text)
        self.use_user(self.author)

        deleted = self.client.delete(f"/api/community/comments/{comment_id}")
        repeated = self.client.delete(f"/api/community/comments/{comment_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        stored_comment = self.db.get(Comment, comment_id)
        self.db.refresh(self.author_post)
        self.assertIsNone(stored_comment)
        self.assertEqual(
            self.db.query(CommunityReport).filter(
                CommunityReport.target_type == "comment",
                CommunityReport.target_id == comment_id,
            ).count(),
            1,
        )
        self.assertEqual(self.author_post.comments, 0)
        self.assertNotIn(comment_id, self.visible_comment_ids(self.author_post.id))

        audit = self.client.get("/api/admin/community/reports?status=pending")
        self.assertEqual(audit.status_code, 200, audit.text)
        audit_item = next(
            item for item in audit.json()["data"]["items"]
            if item["target_type"] == "comment" and item["target_id"] == comment_id
        )
        self.assertFalse(audit_item["target"]["exists"])

        self.use_user(self.viewer)
        denied = self.client.delete(f"/api/community/posts/{self.author_post.id}")
        self.assertEqual(denied.status_code, 404, denied.text)

        self.use_user(self.author)
        post_deleted = self.client.delete(f"/api/community/posts/{self.author_post.id}")
        post_repeated = self.client.delete(f"/api/community/posts/{self.author_post.id}")
        self.assertEqual(post_deleted.status_code, 200, post_deleted.text)
        self.assertEqual(post_repeated.status_code, 200, post_repeated.text)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "deleted")
        self.assertEqual(self.author_post.content, "[内容已删除]")
        self.assertNotIn(self.author_post.id, self.visible_post_ids())

    def test_admin_queue_exposes_reports_and_resolves_all_reports_for_target(self):
        for reporter in self.reporters[:2]:
            response = self.report(reporter, "post", self.author_post.id)
            self.assertEqual(response.status_code, 200, response.text)

        queue = self.client.get("/api/admin/community/reports")
        self.assertEqual(queue.status_code, 200, queue.text)
        queue_data = queue.json()["data"]
        self.assertEqual(queue_data["total"], 2)
        self.assertEqual(len(queue_data["items"]), 2)
        first_item = queue_data["items"][0]
        self.assertEqual(first_item["target_type"], "post")
        self.assertEqual(first_item["target"]["excerpt"], "作者公开动态")
        self.assertEqual(first_item["target"]["author"]["id"], self.author.id)

        reviewed = self.client.patch(
            f"/api/admin/community/reports/{first_item['id']}",
            json={"resolution": "content_removed", "note": "确认违规并下架"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "removed")
        self.assertEqual(self.author_post.moderated_by, self.admin.id)
        reports = self.db.query(CommunityReport).order_by(CommunityReport.id).all()
        self.assertEqual([row.status for row in reports], ["resolved", "resolved"])
        self.assertEqual(
            [row.resolution for row in reports],
            ["content_removed", "content_removed"],
        )
        self.assertTrue(all(row.reviewed_by == self.admin.id for row in reports))
        first_audit = (
            reports[0].status,
            reports[0].resolution,
            reports[0].resolution_note,
            reports[0].reviewed_by,
            reports[0].reviewed_at,
        )

        repeated = self.client.patch(
            f"/api/admin/community/reports/{first_item['id']}",
            json={"resolution": "dismissed", "note": "不得覆盖首次审核"},
        )
        self.assertEqual(repeated.status_code, 409, repeated.text)
        self.db.refresh(reports[0])
        self.db.refresh(self.author_post)
        self.assertEqual(
            (
                reports[0].status,
                reports[0].resolution,
                reports[0].resolution_note,
                reports[0].reviewed_by,
                reports[0].reviewed_at,
            ),
            first_audit,
        )
        self.assertEqual(self.author_post.moderation_status, "removed")

        pending = self.client.get("/api/admin/community/reports")
        resolved = self.client.get("/api/admin/community/reports?status=resolved")
        self.assertEqual(pending.json()["data"]["total"], 0)
        self.assertEqual(resolved.json()["data"]["total"], 2)

    def test_admin_can_dismiss_auto_hidden_content_or_restrict_its_author(self):
        for reporter in self.reporters:
            response = self.report(reporter, "post", self.author_post.id)
            self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "pending_review")

        report_id = self.db.query(CommunityReport.id).order_by(
            CommunityReport.id.asc()
        ).first()[0]
        dismissed = self.client.patch(
            f"/api/admin/community/reports/{report_id}",
            json={"resolution": "dismissed", "note": "未发现违规"},
        )
        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        self.db.refresh(self.author_post)
        self.assertEqual(self.author_post.moderation_status, "visible")

        # Account restriction must finalize content that was already in the
        # automatic review state, and repair the legacy cached comment count.
        self.author_post.moderation_status = "pending_review"
        self.author_post.moderation_reason = "multiple_user_reports"
        self.author_comment.moderation_status = "pending_review"
        self.author_comment.moderation_reason = "multiple_user_reports"
        self.other_post.comments = 1
        extra_post = Post(
            user_id=self.author.id,
            content="同一作者的另一条待处理动态",
            origin="user",
            content_type="text",
        )
        self.db.add(extra_post)
        self.db.commit()

        extra_post_report = self.report(
            self.reporters[0], "post", extra_post.id, reason="spam",
        )
        comment_report = self.report(
            self.reporters[1], "comment", self.author_comment.id,
            reason="harassment",
        )
        unrelated_report = self.report(
            self.reporters[2], "post", self.other_post.id, reason="spam",
        )
        self.assertEqual(extra_post_report.status_code, 200, extra_post_report.text)
        self.assertEqual(comment_report.status_code, 200, comment_report.text)
        self.assertEqual(unrelated_report.status_code, 200, unrelated_report.text)

        user_report = self.report(
            self.viewer, "user", self.author.id, reason="scam",
        )
        self.assertEqual(user_report.status_code, 200, user_report.text)
        user_report_id = user_report.json()["data"]["report_id"]
        restricted = self.client.patch(
            f"/api/admin/community/reports/{user_report_id}",
            json={"resolution": "user_restricted", "note": "确认账号欺诈"},
        )
        self.assertEqual(restricted.status_code, 200, restricted.text)
        self.db.refresh(self.author)
        self.db.refresh(self.author_post)
        self.db.refresh(self.author_comment)
        self.assertEqual(self.author.account_status, "suspended")
        self.assertEqual(self.author_post.moderation_status, "removed")
        self.assertEqual(self.author_comment.moderation_status, "removed")
        self.db.refresh(extra_post)
        self.assertEqual(extra_post.moderation_status, "removed")
        self.db.refresh(self.other_post)
        self.assertEqual(self.other_post.comments, 0)
        related_report_ids = {
            extra_post_report.json()["data"]["report_id"],
            comment_report.json()["data"]["report_id"],
            user_report_id,
        }
        related_reports = self.db.query(CommunityReport).filter(
            CommunityReport.id.in_(related_report_ids)
        ).all()
        self.assertEqual(len(related_reports), 3)
        self.assertTrue(all(row.status == "resolved" for row in related_reports))
        self.assertTrue(all(
            row.resolution == "user_restricted" for row in related_reports
        ))
        pending_ids = {
            row[0] for row in self.db.query(CommunityReport.id).filter(
                CommunityReport.status == "pending"
            ).all()
        }
        self.assertEqual(
            pending_ids,
            {unrelated_report.json()["data"]["report_id"]},
        )


class CommunitySafetyMigrationTests(unittest.TestCase):
    def test_existing_community_tables_gain_visible_moderation_defaults(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL, "
                "phone VARCHAR(20) NOT NULL, password VARCHAR(255) NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE posts ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "content TEXT NOT NULL, images TEXT, video VARCHAR(512), "
                "topic VARCHAR(64), likes INTEGER DEFAULT 0, "
                "comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "CREATE TABLE comments ("
                "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, content TEXT NOT NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "INSERT INTO users (id, username, phone, password) "
                "VALUES (1, '旧用户', '13982000001', '!')"
            ))
            connection.execute(text(
                "INSERT INTO posts (id, user_id, content) "
                "VALUES (1, 1, '旧动态')"
            ))
            connection.execute(text(
                "INSERT INTO comments (id, post_id, user_id, content) "
                "VALUES (1, 1, 1, '旧评论')"
            ))

        # This is the production startup order: create additive tables first,
        # then patch columns on pre-existing SQLite tables.
        Base.metadata.create_all(engine)
        _ensure_columns(engine)
        _ensure_columns(engine)

        inspector = inspect(engine)
        self.assertIn("community_blocks", inspector.get_table_names())
        self.assertIn("community_reports", inspector.get_table_names())
        for table in ("posts", "comments"):
            columns = {item["name"] for item in inspector.get_columns(table)}
            self.assertTrue({
                "moderation_status",
                "moderation_reason",
                "moderated_by",
                "moderated_at",
            }.issubset(columns))
            with engine.connect() as connection:
                status = connection.execute(text(
                    f"SELECT moderation_status FROM {table} WHERE id = 1"
                )).scalar_one()
            self.assertEqual(status, "visible")
            indexes = {
                item["name"]: item["column_names"]
                for item in inspector.get_indexes(table)
            }
            self.assertEqual(
                indexes[f"ix_{table}_moderation_status"],
                ["moderation_status"],
            )

        engine.dispose()


class CommunityModerationConcurrencyTests(unittest.TestCase):
    def test_concurrent_reports_reliably_cross_the_auto_hide_threshold(self):
        tempdir = tempfile.TemporaryDirectory()
        database = Path(tempdir.name) / "community-report-threshold.db"
        engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=10000")
            finally:
                cursor.close()

        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as db:
            author = User(phone="13984000001", username="阈值作者", password="!")
            reporters = [
                User(
                    phone=f"1398400000{index}",
                    username=f"阈值举报人{index}",
                    password="!",
                )
                for index in (2, 3, 4)
            ]
            db.add_all([author, *reporters])
            db.flush()
            post = Post(
                user_id=author.id,
                content="并发举报阈值目标",
                origin="user",
                content_type="text",
            )
            db.add(post)
            db.commit()
            post_id = post.id
            reporter_ids = [reporter.id for reporter in reporters]

        barrier = threading.Barrier(3)

        def report(reporter_id: int):
            with Session() as db:
                barrier.wait(timeout=10)
                return community_router.report_community_content(
                    CommunityReportIn(
                        target_type="post",
                        target_id=post_id,
                        reason="harassment",
                    ),
                    SimpleNamespace(id=reporter_id),
                    db,
                    "ios",
                )

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(report, reporter_ids))

        self.assertTrue(all(result["data"]["status"] == "pending" for result in results))
        with Session() as db:
            self.assertEqual(
                db.query(CommunityReport).filter(
                    CommunityReport.target_type == "post",
                    CommunityReport.target_id == post_id,
                    CommunityReport.status == "pending",
                ).count(),
                community_router.AUTO_HIDE_REPORT_THRESHOLD,
            )
            stored_post = db.get(Post, post_id)
            self.assertEqual(stored_post.moderation_status, "pending_review")
            self.assertEqual(stored_post.moderation_reason, "multiple_user_reports")

        engine.dispose()
        tempdir.cleanup()

    def test_first_admin_decision_claims_all_reports_for_the_same_target(self):
        tempdir = tempfile.TemporaryDirectory()
        database = Path(tempdir.name) / "community-review.db"
        engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=10000")
            finally:
                cursor.close()

        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as db:
            author = User(phone="13983000001", username="并发作者", password="!")
            reporters = [
                User(
                    phone=f"1398300000{index}",
                    username=f"并发举报人{index}",
                    password="!",
                )
                for index in (2, 3)
            ]
            admins = [
                User(
                    phone=f"1398300000{index}",
                    username=f"并发管理员{index}",
                    password="!",
                    role="admin",
                )
                for index in (4, 5)
            ]
            db.add_all([author, *reporters, *admins])
            db.flush()
            post = Post(user_id=author.id, content="并发审核目标")
            db.add(post)
            db.flush()
            reports = [
                CommunityReport(
                    reporter_user_id=reporter.id,
                    target_type="post",
                    target_id=post.id,
                    reason="harassment",
                )
                for reporter in reporters
            ]
            db.add_all(reports)
            db.commit()
            post_id = post.id
            report_ids = [row.id for row in reports]
            admin_ids = [row.id for row in admins]

        barrier = threading.Barrier(2)

        def review(index: int):
            resolution = "content_removed" if index == 0 else "dismissed"
            with Session() as db:
                barrier.wait(timeout=10)
                try:
                    result = admin_router.review_community_report(
                        report_ids[index],
                        CommunityReportReviewIn(
                            resolution=resolution,
                            note=f"并发决策 {index}",
                        ),
                        SimpleNamespace(id=admin_ids[index]),
                        db,
                    )
                    return "ok", result["data"]["resolution"], admin_ids[index]
                except BizError as exc:
                    return "error", exc.status_code, admin_ids[index]

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(review, range(2)))

        self.assertEqual(sorted(item[0] for item in outcomes), ["error", "ok"])
        error = next(item for item in outcomes if item[0] == "error")
        winner = next(item for item in outcomes if item[0] == "ok")
        self.assertEqual(error[1], 409)

        with Session() as db:
            stored_reports = db.query(CommunityReport).order_by(
                CommunityReport.id.asc()
            ).all()
            self.assertEqual(len(stored_reports), 2)
            expected_status = (
                "dismissed" if winner[1] == "dismissed" else "resolved"
            )
            self.assertTrue(all(
                row.status == expected_status for row in stored_reports
            ))
            self.assertTrue(all(
                row.resolution == winner[1] for row in stored_reports
            ))
            self.assertTrue(all(
                row.reviewed_by == winner[2] for row in stored_reports
            ))
            stored_post = db.get(Post, post_id)
            self.assertEqual(
                stored_post.moderation_status,
                "removed" if winner[1] == "content_removed" else "visible",
            )

        engine.dispose()
        tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
