import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


_test_dir = tempfile.TemporaryDirectory(prefix="kai-api-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_dir.name) / 'kai-test.db'}"
os.environ["NEWS_SYNC_ENABLED"] = "false"
os.environ["MARKET_SNAPSHOT_ENABLED"] = "false"
os.environ["EMAIL_NOTIFICATION_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import SESSION_COOKIE  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import kai_auth  # noqa: E402


Base.metadata.create_all(bind=engine)


def _register_native(client: TestClient, phone: str, password: str = "Test-only-password-1") -> dict:
    response = client.post(
        "/api/v1/auth/token/register",
        json={
            "display_name": "移动端测试用户",
            "identifier": phone,
            "password": password,
            "device_name": "iPhone Simulator",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_native_token_registration_login_and_revocation() -> None:
    with TestClient(app) as client:
        session = _register_native(client, "13800000001")
        assert session["token_type"] == "Bearer"
        assert session["user"]["phone"] == "13800000001"
        token = session["access_token"]

        profile = client.get(
            "/api/v1/auth/token/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile.status_code == 200
        assert profile.json()["data"]["user"]["display_name"] == "移动端测试用户"

        revoked = client.post(
            "/api/v1/auth/token/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoked.status_code == 200

        expired = client.get(
            "/api/v1/auth/token/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert expired.status_code == 401
        assert expired.json()["error"]["code"] == "SESSION_EXPIRED"


def test_native_bearer_can_authorize_canonical_state_change() -> None:
    with TestClient(app) as client:
        token = _register_native(client, "13800000002")["access_token"]

        created = client.post(
            "/api/v1/account/addresses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "label": "公司",
                "recipient_name": "测试用户",
                "phone": "13800000002",
                "province": "上海市",
                "city": "上海市",
                "district": "浦东新区",
                "address_line": "测试路 1 号",
                "is_default": True,
            },
        )
        assert created.status_code == 201
        assert created.json()["data"]["recipient_name"] == "测试用户"


def test_native_token_cannot_be_replayed_as_browser_cookie() -> None:
    with TestClient(app) as client:
        token = _register_native(client, "13800000003")["access_token"]
        client.cookies.set(SESSION_COOKIE, token)

        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401


def test_browser_cookie_cannot_be_replayed_as_native_token() -> None:
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/email/register",
            json={
                "name": "网页测试用户",
                "email": "web-channel@example.com",
                "password": "Test-only-password-2",
            },
        )
        assert registered.status_code == 201
        browser_token = client.cookies.get(SESSION_COOKIE)
        assert browser_token

        response = client.get(
            "/api/v1/auth/token/me",
            headers={"Authorization": f"Bearer {browser_token}"},
        )
        assert response.status_code == 401


def test_phone_password_account_created_on_web_logs_in_on_app() -> None:
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/password/register",
            json={
                "display_name": "跨端手机号用户",
                "identifier": "13800000021",
                "password": "Unified-password-21",
            },
        )
        assert registered.status_code == 201
        user_id = registered.json()["data"]["user"]["id"]

        native = client.post(
            "/api/v1/auth/token",
            json={"identifier": "13800000021", "password": "Unified-password-21"},
        )
        assert native.status_code == 200
        assert native.json()["data"]["user"]["id"] == user_id
        assert native.json()["data"]["token_type"] == "Bearer"


def test_email_password_account_created_on_app_logs_in_on_web() -> None:
    with TestClient(app) as client:
        native = client.post(
            "/api/v1/auth/token/register",
            json={
                "display_name": "跨端邮箱用户",
                "identifier": "unified-app@example.com",
                "password": "Unified-password-22",
            },
        )
        assert native.status_code == 201
        user_id = native.json()["data"]["user"]["id"]

        browser = client.post(
            "/api/v1/auth/password/login",
            json={"identifier": "unified-app@example.com", "password": "Unified-password-22"},
        )
        assert browser.status_code == 200
        assert browser.json()["data"]["user"]["id"] == user_id
        assert client.cookies.get(SESSION_COOKIE)


def test_kai_identity_registers_on_web_then_logs_in_on_app(monkeypatch) -> None:
    monkeypatch.setattr(settings, "KAI_AUTH_ISSUER", "https://kai-id.example")
    monkeypatch.setattr(settings, "KAI_AUTH_CLIENT_ID", "kai-test-client")
    monkeypatch.setattr(settings, "KAI_AUTH_CLIENT_SECRET", "kai-test-secret")
    monkeypatch.setattr(settings, "KAI_AUTH_CALLBACK_URL", "http://testserver/api/v1/auth/kai/callback")
    monkeypatch.setattr(settings, "KAI_AUTH_AUTHORIZATION_URL", "https://kai-id.example/authorize")
    monkeypatch.setattr(settings, "KAI_AUTH_APP_REDIRECT_URL", "kai://auth")
    monkeypatch.setattr(kai_auth, "fetch_profile", lambda code, flow: {
        "iss": "https://kai-id.example",
        "sub": "kai-user-1001",
        "name": "Kai 跨端用户",
        "email": "kai-unified@example.com",
        "email_verified": True,
        "phone_number": "+8613800000023",
        "phone_number_verified": True,
    })

    with TestClient(app) as client:
        web_start = client.get(
            "/api/v1/auth/kai/start",
            params={"intent": "register", "return_to": "/account/orders"},
            follow_redirects=False,
        )
        assert web_start.status_code == 302
        web_state = parse_qs(urlparse(web_start.headers["location"]).query)["state"][0]

        web_callback = client.get(
            "/api/v1/auth/kai/callback",
            params={"code": "web-authorization-code", "state": web_state},
            follow_redirects=False,
        )
        assert web_callback.status_code == 302
        assert web_callback.headers["location"] == "http://127.0.0.1:9100/account/orders"
        assert client.cookies.get(SESSION_COOKIE)

        current = client.get("/api/v1/auth/me")
        assert current.status_code == 200
        user_id = current.json()["data"]["user"]["id"]
        assert current.json()["data"]["user"]["email_verified"] is True
        assert current.json()["data"]["user"]["phone_verified"] is True

        app_start = client.post("/api/v1/auth/kai/start", json={"intent": "login"})
        assert app_start.status_code == 200
        app_state = parse_qs(urlparse(app_start.json()["data"]["authorization_url"]).query)["state"][0]

        app_callback = client.get(
            "/api/v1/auth/kai/callback",
            params={"code": "app-authorization-code", "state": app_state},
            follow_redirects=False,
        )
        assert app_callback.status_code == 302
        location = app_callback.headers["location"]
        assert location.startswith("kai://auth?kai_ticket=")
        ticket = parse_qs(urlparse(location).query)["kai_ticket"][0]

        exchanged = client.post("/api/v1/auth/kai/exchange", json={"ticket": ticket})
        assert exchanged.status_code == 200
        assert exchanged.json()["data"]["user"]["id"] == user_id
        assert exchanged.json()["data"]["token_type"] == "Bearer"

        replay = client.post("/api/v1/auth/kai/exchange", json={"ticket": ticket})
        assert replay.status_code == 400


def test_native_profile_password_and_notification_preferences_share_canonical_api() -> None:
    old_password = "Test-only-password-4"
    new_password = "Test-only-password-4-updated"
    with TestClient(app) as client:
        token = _register_native(client, "13800000004", old_password)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        updated = client.patch(
            "/api/v1/account/profile",
            headers=headers,
            json={"display_name": "跨端统一用户"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["display_name"] == "跨端统一用户"

        defaults = client.get("/api/v1/notifications/preferences", headers=headers)
        assert defaults.status_code == 200
        assert defaults.json()["data"]["preferences"]["order_enabled"] is True

        preferences = client.put(
            "/api/v1/notifications/preferences",
            headers=headers,
            json={"order_enabled": False, "wallet_enabled": False},
        )
        assert preferences.status_code == 200
        assert preferences.json()["data"]["preferences"]["order_enabled"] is False
        assert preferences.json()["data"]["preferences"]["wallet_enabled"] is False

        changed = client.post(
            "/api/v1/account/security/password",
            headers=headers,
            json={"current_password": old_password, "new_password": new_password},
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["changed"] is True

        login = client.post(
            "/api/v1/auth/token",
            json={"identifier": "13800000004", "password": new_password},
        )
        assert login.status_code == 200


def test_native_wallet_ledger_contract_returns_real_empty_page() -> None:
    with TestClient(app) as client:
        token = _register_native(client, "13800000005")["access_token"]
        response = client.get(
            "/api/v1/account/wallet/ledger?page=1&page_size=20",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"] == []
        assert response.json()["meta"]["total"] == 0
        assert response.json()["meta"]["real_data_only"] is True

        filtered = client.get(
            "/api/v1/account/wallet/ledger?page=1&page_size=20&type_filter=recharge",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert filtered.status_code == 200
        assert filtered.json()["data"] == []
        assert filtered.json()["meta"]["total"] == 0


def test_native_user_can_favorite_articles_and_videos_for_the_following_feed() -> None:
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.models import NewsArticle, NewsSource

    with SessionLocal() as db:
        source = NewsSource(
            name="收藏测试资讯源",
            feed_url="https://favorite-test.example/feed.xml",
            site_url="https://favorite-test.example",
            category="compute",
        )
        db.add(source); db.flush()
        article = NewsArticle(
            source_id=source.id,
            title="统一收藏测试文章",
            summary="用于验证文章与视频可以进入同一个关注列表。",
            content="<p>测试正文</p>",
            original_url="https://favorite-test.example/article",
            normalized_url="https://favorite-test.example/article",
            category="compute",
            content_fingerprint="favorite-test-article-fingerprint",
            status="published",
            published_at=datetime.now(timezone.utc),
        )
        db.add(article); db.commit(); db.refresh(article)
        article_id = article.id

    with TestClient(app) as client:
        token = _register_native(client, "13800000006")["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        article_favorite = client.post(f"/api/v1/favorites/article/{article_id}", headers=headers)
        video_favorite = client.post("/api/v1/favorites/video/nvidia-gtc-2025", headers=headers)
        assert article_favorite.status_code == 201
        assert video_favorite.status_code == 201

        following = client.get("/api/v1/favorites", headers=headers)
        assert following.status_code == 200
        assert {(item["content_type"], str(item["id"])) for item in following.json()["data"]} == {
            ("article", str(article_id)),
            ("video", "nvidia-gtc-2025"),
        }

        recommended = client.get("/api/v1/feed/recommended", headers=headers)
        assert recommended.status_code == 200
        assert recommended.json()["meta"]["personalized"] is True
        assert {item["content_type"] for item in recommended.json()["data"]} == {"article", "video"}

        removed = client.delete(f"/api/v1/favorites/article/{article_id}", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["data"]["is_favorited"] is False
