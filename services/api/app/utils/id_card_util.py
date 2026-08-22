"""身份证号校验工具：18位格式校验 + 校验位 + 年龄提取"""

import re
from datetime import date

# 校验位权重
WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
CHECK_CODES = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']


def validate_id_card(id_card: str) -> tuple[bool, str]:
    """校验身份证号，返回 (是否有效, 错误信息)"""
    id_card = id_card.strip().upper()

    # 1. 格式校验：18位，前17位数字，最后一位数字或X
    if not re.match(r'^\d{17}[\dX]$', id_card):
        return False, "身份证号须为18位（前17位数字+校验位）"

    # 2. 校验位验证
    total = sum(int(id_card[i]) * WEIGHTS[i] for i in range(17))
    check_code = CHECK_CODES[total % 11]
    if id_card[17] != check_code:
        return False, "身份证号校验位错误，请检查"

    # 3. 生日校验
    try:
        year = int(id_card[6:10])
        month = int(id_card[10:12])
        day = int(id_card[12:14])
        birth = date(year, month, day)
    except ValueError:
        return False, "身份证号中的出生日期无效"

    # 不能是未来日期
    if birth > date.today():
        return False, "出生日期不能在未来"

    # 4. 年龄校验（必须18岁以上）
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    if age < 18:
        return False, f"未满18岁（{age}岁），无法进行实名认证"

    return True, ""


def extract_gender(id_card: str) -> str:
    """从身份证号提取性别：奇数=男，偶数=女"""
    if len(id_card) >= 17:
        return "男" if int(id_card[16]) % 2 == 1 else "女"
    return ""


def extract_birthday(id_card: str) -> str:
    """从身份证号提取生日 YYYY-MM-DD"""
    if len(id_card) >= 14:
        return f"{id_card[6:10]}-{id_card[10:12]}-{id_card[12:14]}"
    return ""
