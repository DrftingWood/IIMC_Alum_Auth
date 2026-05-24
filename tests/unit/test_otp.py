import pytest

from src.shared.otp import generate_code, hash_code, verify_code


def test_generate_code_returns_six_digit_string() -> None:
    for _ in range(50):
        c = generate_code()
        assert len(c) == 6
        assert c.isdigit()


def test_hash_and_verify_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_PEPPER", "p" * 32)
    from src.shared import config

    config._settings = None

    h = hash_code("123456")
    assert h != "123456"
    assert verify_code("123456", h) is True
    assert verify_code("999999", h) is False


def test_verify_rejects_modified_pepper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_PEPPER", "p" * 32)
    from src.shared import config

    config._settings = None
    h = hash_code("424242")

    monkeypatch.setenv("OTP_PEPPER", "q" * 32)
    config._settings = None
    assert verify_code("424242", h) is False
