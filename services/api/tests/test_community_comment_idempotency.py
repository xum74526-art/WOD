import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_current_platform, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import Comment, Post, User
from app.routers import community as community_router
from app.schemas.community import CommentIn
from app.utils.response import BizError, error
from init_db import _migrate_community_comment_idempotency


class CommunityCommentEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "community-comment.db"
        self.engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=10000")
            finally:
                cursor.close()

        Base.metadata.create_all(self.engine)
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            users = [
                User(phone="13975000001", username="评论用户一", password="!"),
                User(phone="13975000002", username="评论用户二", password="!"),
            ]
            db.add_all(users)
            db.flush()
            posts = [
                Post(user_id=users[0].id, content="评论幂等测试一"),
                Post(user_id=users[0].id, content="评论幂等测试二"),
            ]
            db.add_all(posts)
            db.commit()
            self.user_ids = [user.id for user in users]
            self.post_ids = [post.id for post in posts]

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(_request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        app.include_router(community_router.router)

        def db_override():
            with self.Session() as db:
                db.info["authenticated_user_id"] = self.user_ids[0]
                yield db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.user_ids[0])
        app.dependency_overrides[get_current_platform] = lambda: "android"
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def comment_url(self, post_id=None):
        return f"/api/community/posts/{post_id or self.post_ids[0]}/comments"

    def stored_state(self, post_id=None):
        selected_post_id = post_id or self.post_ids[0]
        with self.Session() as db:
            post = db.get(Post, selected_post_id)
            rows = db.query(Comment).filter(
                Comment.post_id == selected_post_id
            ).order_by(Comment.id.asc()).all()
            return post.comments, [
                (row.id, row.user_id, row.content, row.client_request_id, row.created_platform)
                for row in rows
            ]

    def create_direct(
        self,
        *,
        user_id: int,
        post_id: int,
        content: str,
        client_request_id: str | None,
        barrier: threading.Barrier | None = None,
    ):
        with self.Session() as db:
            db.info["authenticated_user_id"] = user_id
            if barrier:
                barrier.wait(timeout=10)
            return community_router.create_comment(
                post_id,
                CommentIn(content=content, client_request_id=client_request_id),
                SimpleNamespace(id=user_id),
                db,
                "web",
            )["data"]

    def test_same_request_returns_the_original_comment_and_count(self):
        payload = {
            "content": "网络超时后重试",
            "client_request_id": "comment-retry-0001",
        }
        first = self.client.post(self.comment_url(), json=payload)
        second = self.client.post(self.comment_url(), json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(first.json()["data"]["post_comments"], 1)
        self.assertEqual(second.json()["data"]["post_comments"], 1)
        cached_count, rows = self.stored_state()
        self.assertEqual(cached_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3:], ("comment-retry-0001", "android"))

    def test_same_key_with_different_content_or_post_is_rejected(self):
        request_id = "comment-conflict-0001"
        first = self.client.post(self.comment_url(), json={
            "content": "原评论",
            "client_request_id": request_id,
        })
        changed_content = self.client.post(self.comment_url(), json={
            "content": "被修改的评论",
            "client_request_id": request_id,
        })
        changed_post = self.client.post(self.comment_url(self.post_ids[1]), json={
            "content": "原评论",
            "client_request_id": request_id,
        })

        self.assertEqual(first.status_code, 200)
        self.assertEqual(changed_content.status_code, 409)
        self.assertEqual(changed_post.status_code, 409)
        self.assertIn("参数不一致", changed_content.json()["msg"])
        self.assertEqual(self.stored_state()[0], 1)
        self.assertEqual(self.stored_state(self.post_ids[1]), (0, []))

    def test_legacy_requests_without_a_key_still_create_distinct_comments(self):
        first = self.client.post(self.comment_url(), json={"content": "旧客户端评论"})
        second = self.client.post(self.comment_url(), json={"content": "旧客户端评论"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(second.json()["data"]["post_comments"], 2)
        cached_count, rows = self.stored_state()
        self.assertEqual(cached_count, 2)
        self.assertEqual([row[3] for row in rows], [None, None])

    def test_client_request_id_uses_the_shared_validation_contract(self):
        self.assertEqual(
            CommentIn(
                content="有效",
                client_request_id="comment-request-0001",
            ).client_request_id,
            "comment-request-0001",
        )
        for invalid in (
            "short",
            "comment request 0001",
            "comment/request/0001",
            "x" * 65,
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                CommentIn(content="无效", client_request_id=invalid)

    def test_concurrent_same_key_inserts_and_counts_once(self):
        workers = 6
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(
                lambda _index: self.create_direct(
                    user_id=self.user_ids[0],
                    post_id=self.post_ids[0],
                    content="并发重试",
                    client_request_id="comment-concurrent-0001",
                    barrier=barrier,
                ),
                range(workers),
            ))

        self.assertEqual(len({item["id"] for item in results}), 1)
        self.assertTrue(all(item["post_comments"] == 1 for item in results))
        cached_count, rows = self.stored_state()
        self.assertEqual((cached_count, len(rows)), (1, 1))

    def test_concurrent_distinct_comments_increment_the_cached_count_atomically(self):
        workers = 6
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(
                lambda index: self.create_direct(
                    user_id=self.user_ids[index % len(self.user_ids)],
                    post_id=self.post_ids[0],
                    content=f"并发评论 {index}",
                    client_request_id=f"comment-distinct-{index:04d}",
                    barrier=barrier,
                ),
                range(workers),
            ))

        self.assertEqual(len({item["id"] for item in results}), workers)
        cached_count, rows = self.stored_state()
        self.assertEqual((cached_count, len(rows)), (workers, workers))
        self.assertEqual(max(item["post_comments"] for item in results), workers)

    def test_create_response_counts_rows_instead_of_trusting_a_stale_cache(self):
        payload = {
            "content": "权威计数",
            "client_request_id": "comment-count-0001",
        }
        created = self.client.post(self.comment_url(), json=payload)
        self.assertEqual(created.status_code, 200)
        with self.Session() as db:
            db.execute(text(
                "UPDATE posts SET comments = 77 WHERE id = :post_id"
            ), {"post_id": self.post_ids[0]})
            db.commit()

        retried = self.client.post(self.comment_url(), json=payload)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["data"]["post_comments"], 1)

    def test_list_response_keeps_the_legacy_comment_item_shape(self):
        created = self.client.post(self.comment_url(), json={
            "content": "列表兼容",
            "client_request_id": "comment-list-shape-0001",
        })
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["data"]["post_comments"], 1)

        listed = self.client.get(self.comment_url())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["data"]), 1)
        self.assertNotIn("post_comments", listed.json()["data"][0])


class CommunityCommentMigrationTests(unittest.TestCase):
    def test_legacy_migration_adds_key_repairs_counts_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE posts (id INTEGER PRIMARY KEY, comments INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE comments ("
                "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
                "content TEXT NOT NULL, moderation_status VARCHAR(32) DEFAULT 'visible', "
                "created_platform TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO posts (id, comments) VALUES (10, 99), (11, -3)"
            ))
            connection.execute(text(
                "INSERT INTO comments (id, post_id, user_id, content, created_platform) VALUES "
                "(1, 10, 7, '保留一', 'web'), (2, 10, 8, '保留二', 'ios')"
            ))
            connection.execute(text(
                "INSERT INTO comments "
                "(id, post_id, user_id, content, moderation_status, created_platform) "
                "VALUES (3, 10, 9, '待审核评论', 'pending_review', 'web')"
            ))

        first = _migrate_community_comment_idempotency(engine)
        second = _migrate_community_comment_idempotency(engine)
        self.assertEqual(first, {
            "duplicates_removed": 0,
            "counts_repaired": 2,
            "index_created": True,
        })
        self.assertEqual(second, {
            "duplicates_removed": 0,
            "counts_repaired": 0,
            "index_created": False,
        })
        self.assertIn(
            "client_request_id",
            {item["name"] for item in inspect(engine).get_columns("comments")},
        )
        with engine.connect() as connection:
            counts = connection.execute(text(
                "SELECT id, comments FROM posts ORDER BY id"
            )).all()
        self.assertEqual(counts, [(10, 2), (11, 0)])

    def test_migration_deduplicates_only_identical_intents(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE posts (id INTEGER PRIMARY KEY, comments INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE comments ("
                "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
                "content TEXT NOT NULL, client_request_id VARCHAR(64), "
                "moderation_status VARCHAR(32) DEFAULT 'visible', created_platform TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO posts (id, comments) VALUES (10, 99), (11, 99)"
            ))
            connection.execute(text(
                "INSERT INTO comments "
                "(id, post_id, user_id, content, client_request_id, created_platform) VALUES "
                "(1, 10, 7, '重试评论', 'comment-migrate-0001', 'web'), "
                "(2, 10, 7, '重试评论', 'comment-migrate-0001', 'ios'), "
                "(3, 10, 7, '旧评论', NULL, 'legacy'), "
                "(4, 10, 7, '旧评论', NULL, 'legacy'), "
                "(5, 11, 8, '另一用户', 'comment-migrate-0001', 'android')"
            ))
            connection.execute(text(
                "INSERT INTO comments "
                "(id, post_id, user_id, content, client_request_id, moderation_status, created_platform) "
                "VALUES (6, 10, 9, '隐藏评论', NULL, 'pending_review', 'web')"
            ))

        result = _migrate_community_comment_idempotency(engine)
        self.assertEqual(result, {
            "duplicates_removed": 1,
            "counts_repaired": 2,
            "index_created": True,
        })
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, post_id, user_id, client_request_id FROM comments ORDER BY id"
            )).all()
            counts = connection.execute(text(
                "SELECT id, comments FROM posts ORDER BY id"
            )).all()
        self.assertEqual(rows, [
            (1, 10, 7, "comment-migrate-0001"),
            (3, 10, 7, None),
            (4, 10, 7, None),
            (5, 11, 8, "comment-migrate-0001"),
            (6, 10, 9, None),
        ])
        self.assertEqual(counts, [(10, 3), (11, 1)])

    def test_migration_refuses_to_discard_conflicting_intents(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE posts (id INTEGER PRIMARY KEY, comments INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE comments ("
                "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
                "content TEXT NOT NULL, client_request_id VARCHAR(64), created_platform TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO posts (id, comments) VALUES (10, 50), (11, 60)"
            ))
            connection.execute(text(
                "INSERT INTO comments "
                "(id, post_id, user_id, content, client_request_id, created_platform) VALUES "
                "(1, 10, 7, '第一种意图', 'comment-conflict-0001', 'web'), "
                "(2, 10, 7, '第二种意图', 'comment-conflict-0001', 'ios'), "
                "(3, 10, 8, '相同内容', 'comment-conflict-0002', 'web'), "
                "(4, 11, 8, '相同内容', 'comment-conflict-0002', 'android')"
            ))

        with self.assertRaisesRegex(RuntimeError, "conflicting per-user"):
            _migrate_community_comment_idempotency(engine)
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, post_id, content FROM comments ORDER BY id"
            )).all()
            counts = connection.execute(text(
                "SELECT id, comments FROM posts ORDER BY id"
            )).all()
        self.assertEqual(rows, [
            (1, 10, "第一种意图"),
            (2, 10, "第二种意图"),
            (3, 10, "相同内容"),
            (4, 11, "相同内容"),
        ])
        self.assertEqual(counts, [(10, 50), (11, 60)])
        self.assertFalse(any(
            item.get("name") == "uq_comments_user_client_request"
            for item in inspect(engine).get_indexes("comments")
        ))

    def test_runtime_conflict_handling_matches_fresh_and_migrated_partial_indexes(self):
        for migrated in (False, True):
            with self.subTest(migrated=migrated), tempfile.TemporaryDirectory() as folder:
                engine = create_engine(
                    f"sqlite:///{Path(folder) / 'partial-index.db'}",
                    connect_args={"check_same_thread": False, "timeout": 10},
                )
                Base.metadata.create_all(engine)
                if migrated:
                    with engine.begin() as connection:
                        connection.execute(text(
                            "DROP INDEX uq_comments_user_client_request"
                        ))
                    _migrate_community_comment_idempotency(engine)

                with engine.connect() as connection:
                    index_sql = connection.execute(text(
                        "SELECT sql FROM sqlite_master WHERE type = 'index' "
                        "AND name = 'uq_comments_user_client_request'"
                    )).scalar_one()
                self.assertIn("WHERE client_request_id IS NOT NULL", index_sql)

                Session = sessionmaker(bind=engine, expire_on_commit=False)
                with Session() as db:
                    user = User(
                        phone=f"1397600000{int(migrated)}",
                        username="部分索引测试",
                        password="!",
                    )
                    db.add(user)
                    db.flush()
                    post = Post(user_id=user.id, content="部分索引运行时测试")
                    db.add(post)
                    db.commit()
                    user_id = user.id
                    post_id = post.id

                for _attempt in range(2):
                    with Session() as db:
                        db.info["authenticated_user_id"] = user_id
                        community_router.create_comment(
                            post_id,
                            CommentIn(
                                content="相同请求",
                                client_request_id="comment-partial-0001",
                            ),
                            SimpleNamespace(id=user_id),
                            db,
                            "web",
                        )
                with Session() as db:
                    self.assertEqual(db.query(Comment).count(), 1)
                    self.assertEqual(db.get(Post, post_id).comments, 1)
                engine.dispose()

    def test_unique_key_is_scoped_per_user_and_null_remains_compatible(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO comments "
                "(id, post_id, user_id, content, client_request_id, created_platform) VALUES "
                "(1, 10, 7, '一', 'comment-shared-0001', 'web'), "
                "(2, 10, 8, '二', 'comment-shared-0001', 'ios'), "
                "(3, 10, 7, '旧一', NULL, 'legacy'), "
                "(4, 10, 7, '旧二', NULL, 'legacy')"
            ))
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO comments "
                    "(id, post_id, user_id, content, client_request_id, created_platform) "
                    "VALUES (5, 11, 7, '冲突', 'comment-shared-0001', 'web')"
                ))


if __name__ == "__main__":
    unittest.main()
