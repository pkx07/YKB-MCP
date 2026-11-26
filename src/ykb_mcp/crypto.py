import base64
import hashlib
import json

from Crypto.Cipher import DES

_DES_KEY = b"de158b87"
_DES_IV = bytes.fromhex("1234567890abcdef")
_SIGN_SALT = "bfde83c3208f4bfe97a57765ee824e92"


def encrypt_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def signature(timestamp: str, params: dict[str, str]) -> str:
    app_id = str(params.get("app_id", ""))
    param_str = "".join(f"{k}={params[k]}" for k in sorted(params))
    build = param_str + app_id + timestamp
    md5_str = hashlib.md5(build.encode("utf-8")).hexdigest()
    return hashlib.sha1((md5_str + _SIGN_SALT).encode("utf-8")).hexdigest()


def decrypt_data(cipher_b64: str) -> str:
    cipher = DES.new(_DES_KEY, DES.MODE_CBC, _DES_IV)
    raw = base64.b64decode(cipher_b64)
    if not raw or len(raw) % 8 != 0:
        raise ValueError("密文长度非法")
    padded = cipher.decrypt(raw)
    pad_len = padded[-1]
    if not 1 <= pad_len <= 8 or padded[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("PKCS5 填充非法")
    return padded[:-pad_len].decode("utf-8")


def decrypt_json(cipher_b64: str):
    return json.loads(decrypt_data(cipher_b64))


def encrypt_data(plain: str) -> str:
    data = plain.encode("utf-8")
    pad_len = 8 - len(data) % 8
    data += bytes([pad_len]) * pad_len
    cipher = DES.new(_DES_KEY, DES.MODE_CBC, _DES_IV)
    return base64.b64encode(cipher.encrypt(data)).decode("ascii")