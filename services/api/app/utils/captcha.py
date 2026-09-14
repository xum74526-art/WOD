"""图形验证码：生成不可直接读取文本节点的 PNG 图片并存储答案。"""
import base64
import io
import secrets
import time
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

CAPTCHA_STORE: dict[str, dict] = {}  # key -> {code, expire}
CAPTCHA_EXPIRE = 300  # 5分钟过期
_CAPTCHA_LOCK = Lock()
_RNG = secrets.SystemRandom()
_CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_IMAGE_SIZE = (120, 50)
_RENDER_SCALE = 2


def _generate_code(length: int = 4) -> str:
    """生成4位验证码（字母+数字，排除易混淆字符）"""
    return "".join(secrets.choice(_CAPTCHA_CHARS) for _ in range(length))


def _scaled(value: int) -> int:
    return value * _RENDER_SCALE


def _random_color(low: int, high: int) -> tuple[int, int, int]:
    return tuple(_RNG.randint(low, high) for _ in range(3))


def _fit_layer_position(
    x: int,
    y: int,
    layer: Image.Image,
    canvas_size: tuple[int, int],
) -> tuple[int, int]:
    """把图层的不透明像素限制在画布内，透明边距仍可越界。"""
    opaque_bounds = layer.getchannel("A").getbbox()
    if not opaque_bounds:
        return x, y
    left, top, right, bottom = opaque_bounds
    canvas_width, canvas_height = canvas_size
    return (
        min(max(x, -left), canvas_width - right),
        min(max(y, -top), canvas_height - bottom),
    )


def _make_png(code: str) -> bytes:
    """把验证码栅格化为 PNG；返回内容不再含可正则提取的文本节点。"""
    width, height = (_scaled(value) for value in _IMAGE_SIZE)
    image = Image.new("RGB", (width, height), _random_color(235, 248))
    draw = ImageDraw.Draw(image)

    # 先画浅色干扰线，避免遮住主体字符。
    for _ in range(4):
        draw.line(
            (
                _RNG.randint(0, width - 1),
                _RNG.randint(0, height - 1),
                _RNG.randint(0, width - 1),
                _RNG.randint(0, height - 1),
            ),
            fill=_random_color(135, 200),
            width=_scaled(_RNG.randint(1, 2)),
        )

    font = ImageFont.load_default(size=_scaled(28))
    slot_width = width / max(len(code), 1)
    for index, character in enumerate(code):
        glyph = Image.new("RGBA", (_scaled(38), _scaled(44)), (0, 0, 0, 0))
        glyph_draw = ImageDraw.Draw(glyph)
        bounds = glyph_draw.textbbox((0, 0), character, font=font)
        glyph_width = bounds[2] - bounds[0]
        glyph_height = bounds[3] - bounds[1]
        glyph_draw.text(
            (
                (glyph.width - glyph_width) / 2 - bounds[0],
                (glyph.height - glyph_height) / 2 - bounds[1],
            ),
            character,
            font=font,
            fill=(*_random_color(15, 90), 255),
        )
        rotated = glyph.rotate(
            _RNG.randint(-14, 14),
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        center_x = int(slot_width * (index + 0.5))
        x = center_x - rotated.width // 2 + _scaled(_RNG.randint(-2, 2))
        y = (height - rotated.height) // 2 + _scaled(_RNG.randint(-2, 2))
        x, y = _fit_layer_position(x, y, rotated, (width, height))
        image.paste(rotated, (x, y), rotated)

    # 少量点和细线叠在字符上，增加自动识别成本但保持肉眼清晰。
    draw = ImageDraw.Draw(image)
    for _ in range(45):
        x = _RNG.randint(0, width - 1)
        y = _RNG.randint(0, height - 1)
        radius = _RNG.randint(1, _scaled(1))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=_random_color(100, 190))
    for _ in range(2):
        draw.line(
            (
                0,
                _RNG.randint(_scaled(8), height - _scaled(8)),
                width - 1,
                _RNG.randint(_scaled(8), height - _scaled(8)),
            ),
            fill=_random_color(100, 175),
            width=_scaled(1),
        )

    image = image.resize(_IMAGE_SIZE, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def create_captcha() -> dict:
    """生成验证码，返回兼容原客户端的 {key, image}。"""
    code = _generate_code()
    key = secrets.token_hex(12)
    image_b64 = base64.b64encode(_make_png(code)).decode("ascii")
    now = time.time()
    with _CAPTCHA_LOCK:
        _cleanup_locked(now)
        CAPTCHA_STORE[key] = {"code": code, "expire": now + CAPTCHA_EXPIRE}
    return {"key": key, "image": f"data:image/png;base64,{image_b64}"}


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
