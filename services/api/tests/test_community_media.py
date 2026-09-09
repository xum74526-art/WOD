import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.deps import get_current_platform, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import User  # noqa: F401
from app.models.community import Post
from app.routers import community as community_router
from app.services.community_video import StandardizedCommunityVideo
from app.utils.response import BizError, error


def image_bytes(image_format: str = "PNG") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), color=(18, 175, 196)).save(stream, format=image_format)
    return stream.getvalue()


def minimal_mp4_bytes() -> bytes:
    # Enough for the server's ISO-BMFF signature validation; the browser owns
    # codec/playability checks for real files selected by the user.
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41" + b"0" * 48


def minimal_mov_bytes() -> bytes:
    return b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"0" * 48


def minimal_webm_bytes() -> bytes:
    return b"\x1a\x45\xdf\xa3\x9f\x42\x82\x84webm" + b"0" * 48


class CommunityMediaTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="13900000011", username="社区媒体测试", password="!")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_patcher = patch.object(community_router, "COMMUNITY_DIR", Path(self.temp_dir.name))
        self.dir_patcher.start()
        self.standardized_video = minimal_mp4_bytes() + b"standardized"
        self.standardize_patcher = patch.object(
            community_router,
            "standardize_community_video",
            side_effect=lambda content, input_extension, max_bytes: StandardizedCommunityVideo(
                content=self.standardized_video,
                duration_seconds=17,
            ),
        )
        self.duration_patcher = patch.object(
            community_router,
            "standardized_video_duration",
            return_value=17,
        )
        self.standardize_patcher.start()
        self.duration_patcher.start()

        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(request: Request, exc: BizError):
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        app.include_router(community_router.router)
        app.include_router(community_router.public_router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_current_platform] = lambda: "legacy"
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.duration_patcher.stop()
        self.standardize_patcher.stop()
        self.dir_patcher.stop()
        self.temp_dir.cleanup()
        self.db.close()

    def upload(self, filename: str, content: bytes, content_type: str):
        return self.client.post(
            "/api/community/media/upload",
            files={"media": (filename, content, content_type)},
        )

    def test_upload_requires_authentication(self):
        app = FastAPI()
        app.include_router(community_router.router)
        response = TestClient(app).post(
            "/api/community/media/upload",
            files={"media": ("image.png", image_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 401)

    def test_post_feed_and_comments_are_publicly_readable(self):
        post = Post(user_id=self.user.id, content="公开算力资讯", content_type="text")
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)

        feed = self.client.get("/api/community/posts?tab=recommend&page=1&page_size=10")
        self.assertEqual(feed.status_code, 200)
        item = feed.json()["data"]["items"][0]
        self.assertEqual(item["content"], "公开算力资讯")
        self.assertFalse(item["is_liked"])
        self.assertFalse(item["is_following"])
        self.assertFalse(item["is_own"])

        comments = self.client.get(f"/api/community/posts/{post.id}/comments")
        self.assertEqual(comments.status_code, 200)
        self.assertEqual(comments.json()["data"], [])
        self.assertEqual(
            self.client.get("/api/community/posts?tab=follow").status_code,
            401,
        )

    def test_valid_png_is_uuid_persisted_and_only_public_route_serves_it(self):
        response = self.upload("photo.png", image_bytes(), "image/png")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["kind"], "image")
        self.assertRegex(
            data["url"],
            rf"^/uploads/community/{self.user.id}/[0-9a-f]{{32}}\.png$",
        )
        stored = Path(self.temp_dir.name) / str(self.user.id) / Path(data["url"]).name
        self.assertTrue(stored.is_file())

        public_path = "/api" + data["url"]
        public = self.client.get(public_path)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.headers["content-type"], "image/png")
        self.assertEqual(public.headers["x-content-type-options"], "nosniff")

    def test_valid_mp4_is_persisted_and_can_be_referenced_with_duration(self):
        uploaded = self.upload("clip.mp4", minimal_mp4_bytes(), "video/mp4")
        self.assertEqual(uploaded.status_code, 200)
        media_url = uploaded.json()["data"]["url"]
        self.assertTrue(media_url.endswith(".mp4"))
        self.assertEqual(uploaded.json()["data"]["content_type"], "video/mp4")
        self.assertEqual(uploaded.json()["data"]["duration"], 17)
        self.assertTrue(uploaded.json()["data"]["standardized"])

        created = self.client.post(
            "/api/community/posts",
            json={"content": "真实视频", "video": media_url, "video_duration": 17},
        )
        self.assertEqual(created.status_code, 200)
        post = created.json()["data"]
        self.assertEqual(post["video"], media_url)
        self.assertEqual(post["video_duration"], 17)
        self.assertEqual(post["content_type"], "video")

        public = self.client.get("/api" + media_url)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.headers["content-type"], "video/mp4")
        self.assertEqual(public.headers["accept-ranges"], "bytes")
        partial = self.client.get("/api" + media_url, headers={"Range": "bytes=4-11"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, self.standardized_video[4:12])
        self.assertTrue(partial.headers["content-range"].startswith("bytes 4-11/"))

    def test_valid_webm_is_standardized_to_public_mp4(self):
        uploaded = self.upload("clip.webm", minimal_webm_bytes(), "video/webm")
        self.assertEqual(uploaded.status_code, 200)
        media_url = uploaded.json()["data"]["url"]
        self.assertTrue(media_url.endswith(".mp4"))
        self.assertTrue(uploaded.json()["data"]["standardized"])
        public = self.client.get("/api" + media_url)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.headers["content-type"], "video/mp4")

    def test_valid_iphone_mov_is_standardized_to_mp4_with_ranges(self):
        uploaded = self.upload("iphone.MOV", minimal_mov_bytes(), "video/quicktime")
        self.assertEqual(uploaded.status_code, 200)
        media_url = uploaded.json()["data"]["url"]
        self.assertTrue(media_url.endswith(".mp4"))
        self.assertEqual(uploaded.json()["data"]["content_type"], "video/mp4")

        public = self.client.get("/api" + media_url)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.headers["content-type"], "video/mp4")
        self.assertEqual(public.headers["accept-ranges"], "bytes")
        partial = self.client.get("/api" + media_url, headers={"Range": "bytes=8-11"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, self.standardized_video[8:12])

    def test_failed_video_standardization_never_publishes_the_original_file(self):
        with patch.object(
            community_router,
            "standardize_community_video",
            side_effect=BizError("视频转换失败，请更换视频后重试"),
        ):
            response = self.upload("broken.mov", minimal_mov_bytes(), "video/quicktime")
        self.assertEqual(response.status_code, 400)
        self.assertIn("转换失败", response.json()["msg"])
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.*")), [])

    def test_extension_and_magic_bytes_must_match(self):
        response = self.upload("not-really.jpg", image_bytes("PNG"), "image/jpeg")
        self.assertEqual(response.status_code, 400)
        self.assertIn("扩展名", response.json()["msg"])
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*.*")), [])

        for filename, content, mime in (
            ("renamed.mov", minimal_mp4_bytes(), "video/quicktime"),
            ("renamed.mp4", minimal_mov_bytes(), "video/mp4"),
        ):
            with self.subTest(filename=filename):
                response = self.upload(filename, content, mime)
                self.assertEqual(response.status_code, 400)
                self.assertIn("扩展名", response.json()["msg"])

    def test_damaged_image_magic_is_rejected(self):
        response = self.upload(
            "damaged.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("损坏", response.json()["msg"])

    def test_image_size_limit_is_enforced_before_decode(self):
        oversized = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        with patch.object(settings, "COMMUNITY_IMAGE_MAX_BYTES", 32):
            response = self.upload("large.png", oversized, "image/png")
        self.assertEqual(response.status_code, 400)
        self.assertIn("32B", response.json()["msg"])

    def test_video_size_limit_is_enforced(self):
        content = minimal_mp4_bytes()
        with patch.object(settings, "COMMUNITY_VIDEO_MAX_BYTES", len(content)):
            accepted = self.upload("exact-limit.mp4", content, "video/mp4")
        self.assertEqual(accepted.status_code, 200)

        with patch.object(settings, "COMMUNITY_VIDEO_MAX_BYTES", len(content) - 1):
            response = self.upload("over-limit.mp4", content, "video/mp4")
        self.assertEqual(response.status_code, 400)
        self.assertIn(f"{len(content) - 1}B", response.json()["msg"])

    def test_default_video_limit_matches_mobile_copy_and_proxy_headroom(self):
        limit = Settings.model_fields["COMMUNITY_VIDEO_MAX_BYTES"].default
        duration_limit = Settings.model_fields["COMMUNITY_VIDEO_MAX_DURATION_SECONDS"].default
        self.assertEqual(limit, 20 * 1024 * 1024)
        self.assertEqual(duration_limit, 300)
        self.assertEqual(community_router._file_size_limit_label(limit), "20MB")

        repository = Path(__file__).resolve().parents[3]
        nginx = (repository / "infra" / "kai-nginx.conf").read_text(encoding="utf-8")
        self.assertIn("client_max_body_size 21m;", nginx)
        self.assertIn("location = /api/v1/canonical/community/media/upload", nginx)
        self.assertIn("location = /api/community/media/upload", nginx)
        self.assertGreaterEqual(nginx.count("proxy_read_timeout 240s;"), 2)
        for environment_template in (
            repository / "services" / "api" / ".env.example",
            repository / "infra" / "api.env.example",
        ):
            environment = environment_template.read_text(encoding="utf-8")
            self.assertIn("COMMUNITY_VIDEO_MAX_BYTES=20971520", environment)
            self.assertIn("COMMUNITY_VIDEO_MAX_DURATION_SECONDS=300", environment)
        for platform in ("android", "ios"):
            copy = (repository / "apps" / platform / "src" / "store" / "i18n.ts").read_text(encoding="utf-8")
            self.assertIn("上传后统一转换为兼容 MP4；最长 5 分钟，不超过 20MB", copy)
            self.assertIn("converted to compatible MP4 after upload; up to 5 minutes and 20 MB", copy)
            self.assertNotIn("社区视频不能超过 50MB", copy)
        dockerfile = (repository / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ffmpeg", dockerfile)

    def test_post_rejects_phone_paths_remote_urls_missing_and_other_user_media(self):
        bad_values = [
            "file:///storage/emulated/0/temporary.jpg",
            "https://example.com/arbitrary.jpg",
            f"/uploads/community/{self.user.id}/{'0' * 32}.jpg",
            f"/uploads/community/{self.user.id + 1}/{'0' * 32}.jpg",
            "../id_cards/id_front_1.jpg",
        ]
        for value in bad_values:
            with self.subTest(value=value):
                response = self.client.post(
                    "/api/community/posts",
                    json={"content": "非法引用", "images": [value]},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("不存在或无权引用", response.json()["msg"])

    def test_post_accepts_uploaded_images_and_limits_count(self):
        first = self.upload("one.png", image_bytes(), "image/png").json()["data"]["url"]
        second = self.upload("two.jpg", image_bytes("JPEG"), "image/jpeg").json()["data"]["url"]
        created = self.client.post(
            "/api/community/posts",
            json={"content": "真实图片", "images": [first, second]},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["data"]["images"], [first, second])
        self.assertEqual(created.json()["data"]["content_type"], "image")

        too_many = self.client.post(
            "/api/community/posts",
            json={"content": "太多图片", "images": [first] * 10},
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertIn("最多", too_many.json()["msg"])

    def test_video_reference_uses_server_duration_and_cannot_mix_with_images(self):
        image_url = self.upload("one.png", image_bytes(), "image/png").json()["data"]["url"]
        video_url = self.upload("one.mp4", minimal_mp4_bytes(), "video/mp4").json()["data"]["url"]
        no_duration = self.client.post(
            "/api/community/posts", json={"content": "缺少时长", "video": video_url},
        )
        self.assertEqual(no_duration.status_code, 200)
        self.assertEqual(no_duration.json()["data"]["video_duration"], 17)

        forged_duration = self.client.post(
            "/api/community/posts",
            json={"content": "伪造时长", "video": video_url, "video_duration": 999},
        )
        self.assertEqual(forged_duration.status_code, 200)
        self.assertEqual(forged_duration.json()["data"]["video_duration"], 17)

        mixed = self.client.post(
            "/api/community/posts",
            json={
                "content": "混合媒体", "images": [image_url],
                "video": video_url, "video_duration": 12,
            },
        )
        self.assertEqual(mixed.status_code, 400)
        self.assertIn("不能同时", mixed.json()["msg"])

    def test_post_rejects_a_legacy_unstandardized_video_container(self):
        user_dir = Path(self.temp_dir.name) / str(self.user.id)
        user_dir.mkdir(parents=True)
        filename = f"{'a' * 32}.mov"
        (user_dir / filename).write_bytes(minimal_mov_bytes())
        response = self.client.post(
            "/api/community/posts",
            json={
                "content": "旧容器",
                "video": f"/uploads/community/{self.user.id}/{filename}",
                "video_duration": 12,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("兼容处理", response.json()["msg"])

    def test_public_route_cannot_traverse_to_private_upload_siblings(self):
        with self.assertRaises(HTTPException) as raised:
            community_router._public_community_media_path(
                self.user.id, "../id_cards/id_front_1.jpg",
            )
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
