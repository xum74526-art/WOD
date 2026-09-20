"""Normalize KAI's published region labels for catalogue/filter display."""


PROVINCE_TO_REGION = {
    "北京": ("north_china", "华北"), "天津": ("north_china", "华北"),
    "河北": ("north_china", "华北"), "山西": ("north_china", "华北"),
    "内蒙古": ("north_china", "华北"),
    "上海": ("east_china", "华东"), "江苏": ("east_china", "华东"),
    "浙江": ("east_china", "华东"), "安徽": ("east_china", "华东"),
    "福建": ("east_china", "华东"), "江西": ("east_china", "华东"),
    "山东": ("east_china", "华东"),
    "广东": ("south_china", "华南"), "广西": ("south_china", "华南"),
    "海南": ("south_china", "华南"),
    "陕西": ("northwest_china", "西北"), "甘肃": ("northwest_china", "西北"),
    "青海": ("northwest_china", "西北"), "宁夏": ("northwest_china", "西北"),
    "新疆": ("northwest_china", "西北"),
    "四川": ("southwest_china", "西南"), "贵州": ("southwest_china", "西南"),
    "云南": ("southwest_china", "西南"), "西藏": ("southwest_china", "西南"),
    "重庆": ("southwest_china", "西南"),
}

REGIONS = [
    {"code": "north_china", "name": "华北"},
    {"code": "east_china", "name": "华东"},
    {"code": "central_china", "name": "华中"},
    {"code": "south_china", "name": "华南"},
    {"code": "northeast_china", "name": "东北"},
    {"code": "northwest_china", "name": "西北"},
    {"code": "southwest_china", "name": "西南"},
    {"code": "china_unspecified", "name": "中国大陆"},
    {"code": "asia_pacific", "name": "亚太"},
    {"code": "north_america", "name": "北美"},
    {"code": "europe", "name": "欧洲"},
    {"code": "middle_east", "name": "中东"},
    {"code": "south_america", "name": "南美"},
    {"code": "africa", "name": "非洲"},
    {"code": "global_unspecified", "name": "全球/未披露"},
]


KAI_REGION_TOKENS = (
    ("中国大陆-华北", "north_china", "华北"),
    ("中国大陆-华东", "east_china", "华东"),
    ("中国大陆-华中", "central_china", "华中"),
    ("中国大陆-华南", "south_china", "华南"),
    ("中国大陆-东北", "northeast_china", "东北"),
    ("中国大陆-西北", "northwest_china", "西北"),
    ("中国大陆-西南", "southwest_china", "西南"),
    ("中国大陆", "china_unspecified", "中国大陆"),
    ("亚太", "asia_pacific", "亚太"),
    ("北美", "north_america", "北美"),
    ("欧洲", "europe", "欧洲"),
    ("中东", "middle_east", "中东"),
    ("南美", "south_america", "南美"),
    ("非洲", "africa", "非洲"),
    ("全球", "global_unspecified", "全球/未披露"),
)

# KAI's public examples use compact codes such as ``CN-East``.  Keep the
# longest prefixes first so CN-Northeast is not swallowed by CN-North.
KAI_REGION_PREFIXES = (
    ("cn-northeast", "northeast_china", "东北"),
    ("cn-northwest", "northwest_china", "西北"),
    ("cn-southwest", "southwest_china", "西南"),
    ("cn-central", "central_china", "华中"),
    ("cn-north", "north_china", "华北"),
    ("cn-east", "east_china", "华东"),
    ("cn-south", "south_china", "华南"),
    ("china-northeast", "northeast_china", "东北"),
    ("china-northwest", "northwest_china", "西北"),
    ("china-southwest", "southwest_china", "西南"),
    ("china-central", "central_china", "华中"),
    ("china-north", "north_china", "华北"),
    ("china-east", "east_china", "华东"),
    ("china-south", "south_china", "华南"),
    ("north-america", "north_america", "北美"),
    ("us-", "north_america", "北美"),
    ("usa-", "north_america", "北美"),
    ("ca-", "north_america", "北美"),
    ("eu-", "europe", "欧洲"),
    ("europe-", "europe", "欧洲"),
    ("apac-", "asia_pacific", "亚太"),
    ("asia-", "asia_pacific", "亚太"),
    ("middle-east", "middle_east", "中东"),
    ("south-america", "south_america", "南美"),
    ("africa-", "africa", "非洲"),
)


def map_region(geolocation: str | None, country_code: str | None = None) -> tuple[str, str]:
    """Map an upstream label without pretending an undisclosed place is local."""
    geo = str(geolocation or "").strip()
    normalized = "-".join(geo.casefold().replace("_", "-").split())
    for prefix, code, name in KAI_REGION_PREFIXES:
        if normalized == prefix.rstrip("-") or normalized.startswith(prefix):
            return (code, name)
    for token, code, name in KAI_REGION_TOKENS:
        if token in geo:
            return (code, name)
    for prov, (code, name) in PROVINCE_TO_REGION.items():
        if prov in geo:
            return (code, name)
    if str(country_code or "").upper() == "CN" or "CN" in geo.upper():
        return ("china_unspecified", "中国大陆")
    return ("global_unspecified", "全球/未披露")
