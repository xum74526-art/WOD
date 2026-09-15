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
from app.models import Follow, User
from app.routers import community as community_router
from app.utils.response import BizError, error
from init_db import _migrate_community_follow_idempotency


class CommunityFollowEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database = Path(self.tempdir.name) / "community-follow.db"
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
                User(phone="13974000001", username="关注用户一", password="!"),
                User(phone="13974000002", username="关注用户二", password="!"),
                User(phone="13974000003", username="被关注用户", password="!"),
            ]
            db.add_all(users)
            db.commit()
            self.follower_ids = [users[0].id, users[1].id]
            self.target_id = users[2].id

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(_request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        app.include_router(community_router.router)

        def db_override():
            with self.Session() as db:
                db.info["authenticated_user_id"] = self.follower_ids[0]
                yield db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.follower_ids[0])
        app.dependency_overrides[get_current_platform] = lambda: "ios"
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    @property
    def follow_url(self):
        return f"/api/community/users/{self.target_id}/follow"

    def stored_pairs(self):
        with self.Session() as db:
            rows = db.query(Follow).order_by(Follow.follower_id.asc()).all()
            return [
                (row.follower_id, row.following_id, row.created_platform)
                for row in rows
            ]

    def set_follow_concurrently(
        self,
        follower_id: int,
        following: bool,
        barrier: threading.Barrier,
    ):
        with self.Session() as db:
            db.info["authenticated_user_id"] = follower_id
            barrier.wait(timeout=10)
            return community_router._set_follow_state(
                self.target_id, follower_id, following, db, "web"
            )["data"]

    def test_explicit_follow_and_unfollow_are_repeatable(self):
        first = self.client.post(self.follow_url, json={"following": True})
        second = self.client.post(self.follow_url, json={"following": True})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"], {"following": True})
        self.assertEqual(second.json()["data"], {"following": True})
        self.assertEqual(
            self.stored_pairs(),
            [(self.follower_ids[0], self.target_id, "ios")],
        )

        first_unfollow = self.client.post(self.follow_url, json={"following": False})
        second_unfollow = self.client.post(self.follow_url, json={"following": False})
        self.assertEqual(first_unfollow.json()["data"], {"following": False})
        self.assertEqual(second_unfollow.json()["data"], {"following": False})
        self.assertEqual(self.stored_pairs(), [])

    def test_empty_legacy_request_keeps_toggle_compatibility(self):
        followed = self.client.post(self.follow_url)
        unfollowed = self.client.post(self.follow_url)
        self.assertEqual(followed.status_code, 200)
        self.assertEqual(followed.json()["data"], {"following": True})
        self.assertEqual(unfollowed.json()["data"], {"following": False})

    def test_follow_state_requires_a_real_json_boolean(self):
        for invalid in (1, 0, "true", "false", None):
            response = self.client.post(self.follow_url, json={"following": invalid})
            self.assertEqual(response.status_code, 422, invalid)
        self.assertEqual(self.stored_pairs(), [])

    def test_self_follow_and_missing_target_stay_rejected(self):
        self_follow = self.client.post(
            f"/api/community/users/{self.follower_ids[0]}/follow",
            json={"following": True},
        )
        missing = self.client.post(
            "/api/community/users/999999/follow",
            json={"following": True},
        )
        self.assertEqual(self_follow.status_code, 400)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self.stored_pairs(), [])

    def test_same_user_concurrent_follow_creates_one_relationship(self):
        workers = 6
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(
                lambda _index: self.set_follow_concurrently(
                    self.follower_ids[0], True, barrier
                ),
                range(workers),
            ))

        self.assertTrue(all(result["following"] for result in results))
        self.assertEqual(
            self.stored_pairs(),
            [(self.follower_ids[0], self.target_id, "web")],
        )

    def test_different_followers_remain_distinct_and_unfollow_is_repeatable(self):
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda follower_id: self.set_follow_concurrently(
                    follower_id, True, barrier
                ),
                self.follower_ids,
            ))
        self.assertTrue(all(result["following"] for result in results))
        self.assertEqual(len(self.stored_pairs()), 2)

        unfollow_barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda _index: self.set_follow_concurrently(
                    self.follower_ids[0], False, unfollow_barrier
                ),
                range(2),
            ))
        self.assertTrue(all(not result["following"] for result in results))
        self.assertEqual(
            self.stored_pairs(),
            [(self.follower_ids[1], self.target_id, "web")],
        )


class CommunityFollowMigrationTests(unittest.TestCase):
    def test_migration_deduplicates_relationships_and_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE follows ("
                "id INTEGER PRIMARY KEY, follower_id INTEGER NOT NULL, "
                "following_id INTEGER NOT NULL, created_platform TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO follows "
                "(id, follower_id, following_id, created_platform) VALUES "
                "(1, 7, 10, 'web'), (2, 7, 10, 'ios'), (3, 8, 10, 'android')"
            ))

        first = _migrate_community_follow_idempotency(engine)
        second = _migrate_community_follow_idempotency(engine)
        self.assertEqual(first, {"duplicates_removed": 1, "index_created": True})
        self.assertEqual(second, {"duplicates_removed": 0, "index_created": False})

        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, follower_id, following_id, created_platform "
                "FROM follows ORDER BY id"
            )).all()
        self.assertEqual(rows, [(1, 7, 10, "web"), (3, 8, 10, "android")])

        unique_indexes = [
            item for item in inspect(engine).get_indexes("follows") if item.get("unique")
        ]
        self.assertTrue(any(
            item["name"] == "uq_follows_follower_following"
            and item["column_names"] == ["follower_id", "following_id"]
            for item in unique_indexes
        ))
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO follows "
                    "(id, follower_id, following_id, created_platform) "
                    "VALUES (4, 7, 10, 'web')"
                ))


if __name__ == "__main__":
    unittest.main()
