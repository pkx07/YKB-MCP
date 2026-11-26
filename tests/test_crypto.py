import hashlib

import pytest

from ykb_mcp.crypto import (
    decrypt_data,
    decrypt_json,
    encrypt_data,
    encrypt_password,
    signature,
)


def test_decrypt_pinned_vector_list():
    cipher = "256Ynz8GHnhKArMiqUqRy1H2R+Qs6K+BbSrw/QbV4XUBktheWuGXRBYYU67oEkBdaAQsW8I6rgs="
    assert decrypt_data(cipher) == '{"list":[{"id":"100001","title":"示例题目"}]}'


def test_decrypt_pinned_vector_empty():
    cipher = "fqHfloAWtU208qG1tDaok+y+MgAuE5fo1lizktQdoYRZ7Kj75pwQPw=="
    assert decrypt_data(cipher) == '{"code":"200","data":{"list":[]}}'


def test_decrypt_json():
    cipher = "fqHfloAWtU208qG1tDaok+y+MgAuE5fo1lizktQdoYRZ7Kj75pwQPw=="
    assert decrypt_json(cipher) == {"code": "200", "data": {"list": []}}


def test_encrypt_decrypt_roundtrip():
    plain = '{"list":[{"id":"1","title":"题干"}]}'
    assert decrypt_data(encrypt_data(plain)) == plain


def test_decrypt_bad_padding():
    with pytest.raises(ValueError):
        decrypt_data(encrypt_data("x")[:-2] + "==")


def test_encrypt_password_md5():
    assert encrypt_password("123456") == "e10adc3949ba59abbe56e057f20f883e"


def test_signature_known_vector():
    params = {
        "app_id": "1",
        "mobile": "13800000000",
        "password": "e10adc3949ba59abbe56e057f20f883e",
        "beta_version": "0",
    }
    assert signature("1700000000", params) == "ff06746152258b833baed979833367273a3a29fe"


def test_signature_sorts_keys():
    a = {"b": "2", "a": "1", "app_id": "9"}
    b = {"app_id": "9", "a": "1", "b": "2"}
    assert signature("1700000000", a) == signature("1700000000", b)
    param_str = "a=1app_id=9b=2"
    build = param_str + "9" + "1700000000"
    md5 = hashlib.md5(build.encode()).hexdigest()
    expected = hashlib.sha1((md5 + "bfde83c3208f4bfe97a57765ee824e92").encode()).hexdigest()
    assert signature("1700000000", a) == expected