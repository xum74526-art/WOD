import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_current_platform, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import Like, Post, User
from app.routers import community as community_router
from app.utils.response import BizError, error
from init_db import _migrate_community_like_idempotency


class CommunityLikeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "community-like.db"
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
                User(phone="13973000001", username="点赞用户一", password="!"),
                User(phone="13973000002", username="点赞用户二", password="!"),
            ]
            db.add_all(users)
            db.flush()
            post = Post(user_id=users[0].id, content="并发点赞测试")
            db.add(post)
            db.commit()
            self.user_ids = [user.id for user in users]
            self.post_id = post.id

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

    @property
    def like_url(self):
        return f"/api/community/posts/{self.post_id}/like"

    def stored_state(self):
        with self.Session() as db:
            post = db.get(Post, self.post_id)
            rows = db.query(Like).filter(Like.post_id == self.post_id).all()
            return post.likes, [(row.user_id, row.created_platform) for row in rows]

    def set_like_concurrently(self, user_id: int, liked: bool, barrier: threading.Barrier):
        with self.Session() as db:
            db.info["authenticated_user_id"] = user_id
            db.get(User, user_id)
            barrier.wait(timeout=10)
            return community_router._set_like_state(
                self.post_id, user_id, liked, db, "web"
            )["data"]

    def test_explicit_like_and_unlike_are_repeatable_without_changing_the_count_twice(self):
        first = self.client.post(self.like_url, json={"liked": True})
        second = self.client.post(self.like_url, json={"liked": True})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"], {"liked": True, "likes": 1})
        self.assertEqual(second.json()["data"], {"liked": True, "likes": 1})
        self.assertEqual(self.stored_state(), (1, [(self.user_ids[0], "android")]))

        first_unlike = self.client.post(self.like_url, json={"liked": False})
        second_unlike = self.client.post(self.like_url, json={"liked": False})
        self.assertEqual(first_unlike.json()["data"], {"liked": False, "likes": 0})
        self.assertEqual(second_unlike.json()["data"], {"liked": False, "likes": 0})
        self.assertEqual(self.stored_state(), (0, []))

    def test_empty_legacy_request_keeps_toggle_compatibility(self):
        liked = self.client.post(self.like_url)
        unliked = self.client.post(self.like_url)
        self.assertEqual(liked.status_code, 200)
        self.assertEqual(liked.json()["data"], {"liked": True, "likes": 1})
        self.assertEqual(unliked.status_code, 200)
        self.assertEqual(unliked.json()["data"], {"liked": False, "likes": 0})

    def test_like_state_requires_a_real_json_boolean(self):
        for invalid in (1, 0, "true", "false", None):
            response = self.client.post(self.like_url, json={"liked": invalid})
            self.assertEqual(response.status_code, 422, invalid)
        self.assertEqual(self.stored_state(), (0, []))

    def test_same_user_concurrent_like_creates_one_relation_and_one_count(self):
        workers = 6
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(
                lambda _index: self.set_like_concurrently(self.user_ids[0], True, barrier),
                range(workers),
            ))

        self.assertTrue(all(result["liked"] for result in results))
        self.assertEqual(self.stored_state(), (1, [(self.user_ids[0], "web")]))

    def test_different_users_increment_atomically_and_concurrent_unlike_never_underflows(self):
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda user_id: self.set_like_concurrently(user_id, True, barrier),
                self.user_ids,
            ))
        self.assertTrue(all(result["liked"] for result in results))
        self.assertEqual(self.stored_state()[0], 2)

        unlike_barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(
                lambda _index: self.set_like_concurrently(
                    self.user_ids[0], False, unlike_barrier
                ),
                range(2),
            ))
        self.assertEqual(self.stored_state(), (1, [(self.user_ids[1], "web")]))


class CommunityLikeMigrationTests(unittest.TestCase):
    def test_migration_repairs_duplicates_counts_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE posts (id INTEGER PRIMARY KEY, likes INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE likes ("
                "id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
                "created_platform TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO posts (id, likes) VALUES (10, 99), (11, -3)"
            ))
            connection.execute(text(
                "INSERT INTO likes (id, post_id, user_id, created_platform) VALUES "
                "(1, 10, 7, 'web'), (2, 10, 7, 'ios'), (3, 10, 8, 'android')"
            ))

        # Production init calls create_all first. Existing tables must remain
        # untouched until the explicit deduplication migration runs.
        Base.metadata.create_all(engine)
        first = _migrate_community_like_idempotency(engine)
        second = _migrate_community_like_idempotency(engine)
        self.assertEqual(first, {"duplicates_removed": 1, "index_created": True})
        self.assertEqual(second, {"duplicates_removed": 0, "index_created": False})

        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, post_id, user_id, created_platform FROM likes ORDER BY id"
            )).all()
            counts = connection.execute(text(
                "SELECT id, likes FROM posts ORDER BY id"
            )).all()
        self.assertEqual(rows, [(1, 10, 7, "web"), (3, 10, 8, "android")])
        self.assertEqual(counts, [(10, 2), (11, 0)])

        unique_indexes = [
            item for item in inspect(engine).get_indexes("likes") if item.get("unique")
        ]
        self.assertTrue(any(
            item["name"] == "uq_likes_post_user"
            and item["column_names"] == ["post_id", "user_id"]
            for item in unique_indexes
        ))
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO likes (id, post_id, user_id, created_platform) "
                    "VALUES (4, 10, 7, 'web')"
                ))


if __name__ == "__main__":
    unittest.main()
