import re


_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def normalize_email(value: str) -> str:
    """Return a conservative, case-insensitive recovery mailbox key."""

    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 320 or candidate.count("@") != 1:
        raise ValueError("请输入有效邮箱")
    local, domain = candidate.rsplit("@", 1)
    if not local or len(local) > 64 or not _LOCAL_RE.fullmatch(local):
        raise ValueError("请输入有效邮箱")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("请输入有效邮箱")
    try:
        ascii_domain = domain.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("请输入有效邮箱") from exc
    labels = ascii_domain.split(".")
    if (
        len(ascii_domain) > 253
        or len(labels) < 2
        or any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels)
        or len(labels[-1]) < 2
    ):
        raise ValueError("请输入有效邮箱")
    return f"{local.casefold()}@{ascii_domain}"
