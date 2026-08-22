"""省份/国家 → 国内大区映射。"""


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
    {"code": "south_china", "name": "华南"},
    {"code": "northwest_china", "name": "西北"},
    {"code": "southwest_china", "name": "西南"},
]


def map_region(geolocation: str | None, country_code: str | None = None) -> tuple[str, str]:
    """从 vast geolocation + country_code 推断国内大区。国内城市空时默认华东。"""
    geo = geolocation or ""
    for prov, (code, name) in PROVINCE_TO_REGION.items():
        if prov in geo:
            return (code, name)
    if country_code == "CN" or "CN" in geo:
        return ("east_china", "华东")
    return ("overseas", "海外")
