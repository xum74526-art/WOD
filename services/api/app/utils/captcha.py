"""图形验证码：生成base64图片 + 存储验证码"""
import random
import string
import base64
import io
import time
import hashlib
import os
from threading import Lock

# 简易图形验证码生成（纯Python，不依赖PIL）
# 生成SVG格式的验证码图片，转base64

CAPTCHA_STORE: dict[str, dict] = {}  # key -> {code, expire}
CAPTCHA_EXPIRE = 300  # 5分钟过期
_CAPTCHA_LOCK = Lock()


def _generate_code(length: int = 4) -> str:
    """生成4位验证码（字母+数字，排除易混淆字符）"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=length))


def _make_svg(code: str) -> str:
    """生成SVG验证码图片"""
    w, h = 120, 50
    # 背景色
    bg_r = random.randint(230, 245)
    bg_g = random.randint(230, 245)
    bg_b = random.randint(230, 245)
    # 干扰线
    lines = []
    for _ in range(4):
        x1, y1 = random.randint(0, w), random.randint(0, h)
        x2, y2 = random.randint(0, w), random.randint(0, h)
        r, g, b = random.randint(100, 180), random.randint(100, 180), random.randint(100, 180)
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="rgb({r},{g},{b})" stroke-width="1.5"/>')
    # 干扰点
    dots = []
    for _ in range(20):
        x, y = random.randint(0, w), random.randint(0, h)
        dots.append(f'<circle cx="{x}" cy="{y}" r="1" fill="rgb({random.randint(100,200)},{random.randint(100,200)},{random.randint(100,200)})"/>')
    # 文字（每个字符不同颜色和旋转）
    texts = []
    total_w = 0
    char_w = 26
    start_x = (w - char_w * len(code)) // 2 + 8
    for i, ch in enumerate(code):
        x = start_x + i * char_w
        y = random.randint(28, 38)
        rot = random.randint(-15, 15)
        r = random.randint(20, 80)
        g = random.randint(20, 80)
        b = random.randint(20, 80)
        texts.append(f'<text x="{x}" y="{y}" font-size="28" font-weight="bold" fill="rgb({r},{g},{b})" transform="rotate({rot} {x} {y})" font-family="Arial">{ch}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
<rect width="{w}" height="{h}" fill="rgb({bg_r},{bg_g},{bg_b})"/>
{"".join(lines)}
{"".join(dots)}
{"".join(texts)}
</svg>'''
    return svg


def create_captcha() -> dict:
    """生成验证码，返回 {key, image_base64}"""
    code = _generate_code()
    key = hashlib.md5((code + str(time.time()) + os.urandom(8).hex()).encode()).hexdigest()[:24]
    svg = _make_svg(code)
    svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    now = time.time()
    with _CAPTCHA_LOCK:
        _cleanup_locked(now)
        CAPTCHA_STORE[key] = {"code": code, "expire": now + CAPTCHA_EXPIRE}
    return {"key": key, "image": f"data:image/svg+xml;base64,{svg_b64}"}


def verify_captcha(key: str, code: str) -> bool:
    """验证验证码"""
    normalized_code = code.upper().strip()
    with _CAPTCHA_LOCK:
        _cleanup_locked(time.time())
        item = CAPTCHA_STORE.get(key)
        if not item:
            return False
        # 不区分大小写；正确验证码仅允许被消费一次。
        if item["code"].upper() != normalized_code:
            return False
        del CAPTCHA_STORE[key]
        return True


def _cleanup():
    """清理过期验证码"""
    with _CAPTCHA_LOCK:
        _cleanup_locked(time.time())


def _cleanup_locked(now: float) -> None:
    """在持有验证码锁时清理过期记录。"""
    expired = [k for k, v in CAPTCHA_STORE.items() if now > v["expire"]]
    for k in expired:
        CAPTCHA_STORE.pop(k, None)
