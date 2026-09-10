import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routers.platform import router as platform_router


class AppReleaseTests(unittest.TestCase):
    _FIELDS = (
        "APP_ANDROID_RELEASE_ENABLED",
        "APP_ANDROID_LATEST_VERSION_NAME",
        "APP_ANDROID_LATEST_VERSION_CODE",
        "APP_ANDROID_UPDATE_URL",
        "APP_ANDROID_RELEASE_NOTES_ZH",
        "APP_ANDROID_RELEASE_NOTES_EN",
        "APP_IOS_RELEASE_ENABLED",
        "APP_IOS_LATEST_VERSION_NAME",
        "APP_IOS_LATEST_VERSION_CODE",
        "APP_IOS_UPDATE_URL",
        "APP_IOS_RELEASE_NOTES_ZH",
        "APP_IOS_RELEASE_NOTES_EN",
    )

    def setUp(self):
        self.original = {name: getattr(settings, name) for name in self._FIELDS}
        app = FastAPI()
        app.include_router(platform_router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for name, value in self.original.items():
            setattr(settings, name, value)

    def test_android_release_is_public_and_matches_the_published_package(self):
        response = self.client.get("/api/platform/app-release", params={"platform": "android"})

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["platform"], "android")
        self.assertTrue(data["available"])
        self.assertEqual(data["latest_version_name"], "1.1.9")
        self.assertEqual(data["latest_version_code"], 119)
        self.assertEqual(data["update_url"], "https://wod.kai.com/download/wod.apk")

    def test_ios_update_is_unavailable_until_an_app_store_page_is_configured(self):
        response = self.client.get("/api/platform/app-release", params={"platform": "ios"})

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertFalse(data["available"])
        self.assertIsNone(data["update_url"])
        self.assertIsNone(data["latest_version_code"])

    def test_untrusted_or_malformed_release_configuration_fails_closed(self):
        for url in (
            "http://wod.kai.com/download/wod.apk",
            "https://evil.example/wod.apk",
            "https://wod.kai.com/download/wod.apk?next=https://evil.example",
            "https://user:password@wod.kai.com/download/wod.apk",
        ):
            with self.subTest(url=url):
                settings.APP_ANDROID_UPDATE_URL = url
                data = self.client.get(
                    "/api/platform/app-release", params={"platform": "android"}
                ).json()["data"]
                self.assertFalse(data["available"])
                self.assertIsNone(data["update_url"])

    def test_configured_ios_app_store_release_is_returned(self):
        settings.APP_IOS_RELEASE_ENABLED = True
        settings.APP_IOS_LATEST_VERSION_NAME = "1.1.9"
        settings.APP_IOS_LATEST_VERSION_CODE = 119
        settings.APP_IOS_UPDATE_URL = "https://apps.apple.com/cn/app/ztw/id123456789"

        data = self.client.get(
            "/api/platform/app-release", params={"platform": "ios"}
        ).json()["data"]

        self.assertTrue(data["available"])
        self.assertEqual(data["latest_version_code"], 119)

    def test_release_notes_are_trimmed_and_bounded(self):
        settings.APP_ANDROID_RELEASE_NOTES_ZH = " 修复登录 | 优化更新提示 || 提升稳定性 "
        settings.APP_ANDROID_RELEASE_NOTES_EN = "Login fix|Update prompt|Stability"

        data = self.client.get(
            "/api/platform/app-release", params={"platform": "android"}
        ).json()["data"]

        self.assertEqual(data["release_notes_zh"], ["修复登录", "优化更新提示", "提升稳定性"])
        self.assertEqual(data["release_notes_en"], ["Login fix", "Update prompt", "Stability"])

    def test_unknown_platform_is_rejected(self):
        response = self.client.get("/api/platform/app-release", params={"platform": "windows"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
