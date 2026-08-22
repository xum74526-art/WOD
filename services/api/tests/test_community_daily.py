import unittest

from app.services.community_daily import (
    BILIBILI_VIDEO_PROVIDER,
    SOURCE_BY_KEY,
    _bilibili_content_en,
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


if __name__ == "__main__":
    unittest.main()
