import json
import unittest

import httpx

from collector.adapters.vast import fetch_raw_offers, normalize_offer
from collector.config import settings
from collector.ingestion_client import submit_batch


class VastAdapterTests(unittest.TestCase):
    def setUp(self):
        self.authorized = settings.VAST_COLLECTION_AUTHORIZED
        self.token = settings.INGESTION_TOKEN
        settings.VAST_COLLECTION_AUTHORIZED = True
        settings.INGESTION_TOKEN = "local-test-ingestion-token-32-characters"

    def tearDown(self):
        settings.VAST_COLLECTION_AUTHORIZED = self.authorized
        settings.INGESTION_TOKEN = self.token

    def test_fetch_uses_public_search_and_reads_rate_limit(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "console.vast.ai")
            self.assertEqual(json.loads(request.content)["type"], "on-demand")
            return httpx.Response(
                200,
                headers={"x-ratelimit-limit": "5", "x-ratelimit-remaining": "4"},
                json={"offers": [{"id": 1}]},
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            rows, metadata = fetch_raw_offers("on-demand", client=client)
        self.assertEqual(rows, [{"id": 1}])
        self.assertEqual(metadata["limit"], 5)

    def test_normalizer_excludes_network_identity_fields(self):
        record = normalize_offer({
            "id": 101,
            "gpu_name": "B200",
            "num_gpus": 2,
            "gpu_ram": 183500,
            "gpu_total_ram": 367000,
            "dph_base": 4.0,
            "dph_total": 4.1,
            "rentable": True,
            "public_ipaddr": "203.0.113.10",
            "hostname": "private-host-name",
        })
        self.assertIsNotNone(record)
        self.assertEqual(record["gpu_model"], "B200")
        self.assertEqual(record["per_gpu_compute_price_hourly"], 2.0)
        self.assertNotIn("public_ipaddr", record)
        self.assertNotIn("hostname", record)

    def test_ingestion_client_reuses_fixed_internal_contract(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/internal/v1/ingestion/market-offers/batches"))
            self.assertTrue(request.headers["authorization"].startswith("Bearer "))
            return httpx.Response(200, json={"code": 0, "msg": "ok", "data": {"batch_id": "batch-001"}})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = submit_batch({"batch_id": "batch-001"}, client=client)
        self.assertEqual(result["batch_id"], "batch-001")


if __name__ == "__main__":
    unittest.main()
