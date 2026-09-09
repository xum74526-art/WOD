import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.community_daily import (
    BILIBILI_VIDEO_PROVIDER,
    SOURCE_BY_KEY,
    _backfill_internal_branding,
    _bilibili_content_en,
    _get_system_user,
    _internal_candidates,
    _is_relevant_bilibili_video,
    canonicalize_url,
    strip_html,
)


class CommunityDailyTests(unittest.TestCase):
    def test_strip_html_is_short_and_plain(self):
        value = strip_html("<p>Hello <strong>GPU</strong></p>" + "x" * 30, 18)
        self.assertNotIn("<", value)
        self.assertLessEqual(len(value), 18)

    def test_canonical_url_removes_tracking_but_keeps_video_id(self):
        value = canonicalize_url("https://www.youtube.com/watch?v=abc123&utm_source=x#fragment")
        self.assertEqual(value, "https://www.youtube.com/watch?v=abc123")

    def test_bilibili_source_uses_the_official_embeddable_player(self):
        source = SOURCE_BY_KEY["bilibili-nvidia-official"]
        self.assertEqual(source.kind, "bilibili-official")
        self.assertIn("search.bilibili.com", source.endpoint)
        self.assertIn("player.bilibili.com", source.allowed_hosts)
        self.assertEqual(BILIBILI_VIDEO_PROVIDER, "bilibili")

    def test_bilibili_videos_always_have_english_content(self):
        translated = _bilibili_content_en("BV1YTME6fENw")
        fallback = _bilibili_content_en("BV0000000000")
        self.assertIn("DGX Spark", translated)
        self.assertIn("Official Video", fallback)
        self.assertNotRegex(translated + fallback, r"[\u3400-\u9fff]")

    def test_bilibili_filter_keeps_ai_compute_and_blocks_games(self):
        self.assertTrue(_is_relevant_bilibili_video("DGX Spark：本地 LLM 推理"))
        self.assertTrue(_is_relevant_bilibili_video("NVIDIA AI 工厂与算力集群"))
        self.assertFalse(_is_relevant_bilibili_video("DOTA2 TI 2026 电竞宣传片"))
        self.assertFalse(_is_relevant_bilibili_video("新游戏公测 | DLSS 画面演示"))

    def test_internal_fallback_uses_ztw_display_name_and_legacy_source_key(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        candidate = _internal_candidates(db, "2026-09-09", 1)[0]

        self.assertEqual(candidate.source_key, "wod-market")
        self.assertEqual(candidate.source_name, "ZTW 算力行情")
        self.assertEqual(candidate.author, "ZTW")
        self.assertTrue(candidate.title.startswith("ZTW compute tip"))

    def test_internal_brand_backfill_keeps_legacy_source_key(self):
        post = MagicMock(
            content="价格来自 WOD 最新站内行情，优惠码 WOD10 继续有效",
            content_en="Latest WOD market data",
            source_name="WOD 算力行情",
            source_author="WOD",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [post]

        self.assertEqual(_backfill_internal_branding(db), 1)
        self.assertEqual(post.content, "价格来自 ZTW 最新站内行情，优惠码 WOD10 继续有效")
        self.assertEqual(post.content_en, "Latest ZTW market data")
        self.assertEqual(post.source_name, "ZTW 算力行情")
        self.assertEqual(post.source_author, "ZTW")

    def test_existing_internal_author_is_renamed_without_changing_identity(self):
        user = SimpleNamespace(username="WOD资讯", phone="wod-community")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        self.assertIs(_get_system_user(db), user)
        self.assertEqual(user.username, "ZTW资讯")
        self.assertEqual(user.phone, "wod-community")
        db.flush.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
