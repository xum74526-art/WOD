from decimal import Decimal

from scripts.seed_market_catalog import derive_price, derive_spec


def test_demo_prices_are_deterministic_variations_of_market_median():
    assert derive_price(Decimal("3.38"), 0) == Decimal("2.974")
    assert derive_price(Decimal("3.38"), 3) == Decimal("3.380")
    assert derive_price(Decimal("3.38"), 6) == Decimal("3.887")


def test_demo_specs_cover_high_end_and_consumer_hosts():
    h200 = derive_spec("nvidia-h200", Decimal("4.48"), 2)
    rtx_3070 = derive_spec("nvidia-rtx-3070", Decimal("0.09"), 1)

    assert h200["gpu_memory_gb"] == 141
    assert h200["cpu_cores"] == 96
    assert h200["ram_gb"] >= 512
    assert rtx_3070["gpu_memory_gb"] == 8
    assert rtx_3070["cpu_cores"] == 24
    assert rtx_3070["ram_gb"] == 96
