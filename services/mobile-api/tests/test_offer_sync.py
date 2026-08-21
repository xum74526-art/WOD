import unittest
from unittest.mock import patch

from app.services.offer_sync import _autodl_groups, sync_offers


class OfferSyncTests(unittest.TestCase):
    def test_provider_failures_do_not_short_circuit_other_provider(self):
        with patch(
            "app.services.offer_sync._sync_autodl_products",
            side_effect=RuntimeError("credentials_missing"),
        ) as autodl, patch(
            "app.services.offer_sync._sync_vast_products",
            return_value={"status": "live", "upserted": 3},
        ) as vast:
            result = sync_offers()

        autodl.assert_called_once_with()
        vast.assert_called_once_with()
        self.assertEqual(result["autodl"]["error_code"], "credentials_missing")
        self.assertEqual(result["vast"], {"status": "live", "upserted": 3})

    def test_autodl_products_keep_model_and_memory_variants_separate(self):
        gib = 1024 ** 3
        groups = _autodl_groups([
            {
                "gpu_name": "RTX 4090",
                "gpu_idle_num": 2,
                "payg_price": 1000,
                "gpu_memory": 24 * gib,
                "region_name": "华北",
            },
            {
                "gpu_name": "RTX 4090D",
                "gpu_idle_num": 1,
                "payg_price": 900,
                "gpu_memory": 24 * gib,
                "region_name": "华东",
            },
            {
                "gpu_name": "RTX 4090",
                "gpu_idle_num": 5,
                "payg_price": 1100,
                "gpu_memory": 24 * gib,
                "region_name": "华东",
            },
            {
                "gpu_name": "A100-PCIE-40GB",
                "gpu_idle_num": 3,
                "payg_price": 2000,
                "gpu_memory": 40 * gib,
                "region_name": "华南",
            },
            {
                "gpu_name": "A100-SXM4-80GB",
                "gpu_idle_num": 4,
                "payg_price": 3000,
                "gpu_memory": 80 * gib,
                "region_name": "华南",
            },
        ])

        self.assertIn(("RTX4090", "24GB", "华北"), groups)
        self.assertIn(("RTX4090", "24GB", "华东"), groups)
        self.assertEqual(groups[("RTX4090", "24GB", "华北")]["stock"], 2)
        self.assertEqual(groups[("RTX4090", "24GB", "华东")]["stock"], 5)
        self.assertIn(("RTX4090D", "24GB", "华东"), groups)
        self.assertIn(("A100", "40GB", "华南"), groups)
        self.assertIn(("A100", "80GB", "华南"), groups)


if __name__ == "__main__":
    unittest.main()
