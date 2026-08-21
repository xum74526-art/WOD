from typing import Any


class BizError(Exception):
    """业务异常，全局处理器统一转为 {code,msg,data}。"""

    def __init__(self, msg: str, code: int = 1, status_code: int = 400):
        self.msg = msg
        self.code = code
        self.status_code = status_code


def success(data: Any = None, msg: str = "ok"):
    return {"code": 0, "msg": msg, "data": data}


def error(msg: str = "error", code: int = 1):
    return {"code": code, "msg": msg, "data": None}
