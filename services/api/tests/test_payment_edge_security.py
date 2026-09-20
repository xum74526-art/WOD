import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[3]
NGINX_CONFIG = (REPOSITORY / "infra" / "kai-nginx.conf").read_text(encoding="utf-8")


def location_body(declaration: str) -> str:
    marker = f"location {declaration} {{"
    start = NGINX_CONFIG.find(marker)
    if start < 0:
        raise AssertionError(f"missing nginx location: {declaration}")

    body_start = start + len(marker)
    depth = 1
    cursor = body_start
    while cursor < len(NGINX_CONFIG) and depth:
        if NGINX_CONFIG[cursor] == "{":
            depth += 1
        elif NGINX_CONFIG[cursor] == "}":
            depth -= 1
        cursor += 1
    if depth:
        raise AssertionError(f"unterminated nginx location: {declaration}")
    return NGINX_CONFIG[body_start : cursor - 1]


class PaymentEdgeSecurityTests(unittest.TestCase):
    def assert_private_proxy(self, declaration: str, port: int) -> str:
        body = location_body(declaration)
        self.assertIn("access_log off;", body)
        self.assertIn("error_log /dev/null crit;", body)
        self.assertIn(f"proxy_pass http://127.0.0.1:{port};", body)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr;", body)
        return body

    def test_signed_provider_callbacks_are_bounded_and_not_access_logged(self):
        for provider in ("qixiang", "qixiangpay", "mapay"):
            for suffix in ("", "/"):
                with self.subTest(provider=provider, suffix=suffix):
                    body = self.assert_private_proxy(
                        f"= /api/payments/{provider}/notify{suffix}",
                        8000,
                    )
                    self.assertIn("client_max_body_size 32k;", body)

    def test_checkout_tokens_are_not_access_logged(self):
        native_paths = (
            "qixiang",
            "qixiangpay",
            "mapay",
        )
        for provider in native_paths:
            with self.subTest(client="native", provider=provider):
                self.assert_private_proxy(
                    f"^~ /api/payments/{provider}/checkout/",
                    8000,
                )

        for namespace in ("canonical", "mobile"):
            for provider in ("qixiang", "mapay"):
                with self.subTest(client="web", namespace=namespace, provider=provider):
                    self.assert_private_proxy(
                        f"^~ /api/v1/{namespace}/payments/{provider}/checkout/",
                        3000,
                    )

    def test_dedicated_browser_return_is_not_access_logged(self):
        for suffix in ("", "/"):
            with self.subTest(suffix=suffix):
                self.assert_private_proxy(f"= /payment/qixiang/return{suffix}", 3000)

    def test_production_api_entrypoints_disable_uvicorn_access_logging(self):
        entrypoints = {
            "systemd": (REPOSITORY / "infra" / "kai-api.service"),
            "docker": (REPOSITORY / "services" / "api" / "docker-entrypoint.sh"),
        }
        for name, path in entrypoints.items():
            with self.subTest(entrypoint=name):
                uvicorn_commands = [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if "uvicorn app.main:app" in line
                ]
                self.assertEqual(len(uvicorn_commands), 1)
                self.assertIn("--no-access-log", uvicorn_commands[0].split())


if __name__ == "__main__":
    unittest.main()
