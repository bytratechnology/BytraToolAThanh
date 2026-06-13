import json
import ssl
import urllib.error
import urllib.request

from branding import ADMIN_CONTACT
from firebase_config import FIREBASE_CONFIG, PAYMENT_FLAG_PATH

REQUEST_TIMEOUT = 12


def _denied_message(*lines: str) -> str:
    body = "\n".join(lines)
    return f"{body}\n\n{ADMIN_CONTACT}"


def _ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_is_payment():
    """
    Đọc cờ isPayment từ Firebase Realtime Database.
    Trả về True/False, hoặc None nếu không có giá trị.
    """
    database_url = FIREBASE_CONFIG["databaseURL"].rstrip("/")
    url = f"{database_url}/{PAYMENT_FLAG_PATH}.json"

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT,
        context=_ssl_context(),
    ) as response:
        raw = response.read().decode("utf-8").strip()

    if raw in ("", "null"):
        return None

    value = json.loads(raw)
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False

    return bool(value)


def verify_payment_access():
    """
    Kiểm tra quyền sử dụng theo isPayment.
    Trả về (allowed: bool, message: str).
    """
    try:
        is_payment = fetch_is_payment()
    except urllib.error.URLError as exc:
        return False, _denied_message(
            "Không kết nối được máy chủ xác thực.",
            "Kiểm tra kết nối Internet và thử lại.",
            f"Chi tiết: {exc.reason}",
        )
    except TimeoutError:
        return False, _denied_message(
            "Hết thời gian chờ khi kiểm tra quyền sử dụng.",
            "Vui lòng thử lại sau.",
        )
    except Exception as exc:
        return False, _denied_message(
            "Không thể kiểm tra quyền sử dụng.",
            f"Chi tiết: {exc}",
        )

    if is_payment is True:
        return True, "Đã kích hoạt."

    if is_payment is False:
        return False, _denied_message(
            "Phần mềm chưa được kích hoạt.",
            "Vui lòng liên hệ quản trị viên để được cấp quyền sử dụng.",
        )

    return False, _denied_message(
        "Không tìm thấy trạng thái kích hoạt trên hệ thống.",
        "Vui lòng liên hệ quản trị viên.",
    )
