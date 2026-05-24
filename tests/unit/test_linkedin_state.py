from src.shared.linkedin import build_authorization_url, generate_state


def test_generate_state_returns_url_safe_token() -> None:
    seen = set()
    for _ in range(20):
        s = generate_state()
        assert len(s) >= 32
        # URL-safe characters only
        assert all(c.isalnum() or c in "-_" for c in s)
        seen.add(s)
    # Tokens are unique
    assert len(seen) == 20


def test_build_authorization_url_includes_required_params() -> None:
    url = build_authorization_url(
        client_id="cid",
        redirect_uri="https://example.com/oauth/linkedin/callback",
        state="state-xyz",
    )
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert "client_id=cid" in url
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Foauth%2Flinkedin%2Fcallback" in url
    assert "state=state-xyz" in url
    assert "scope=openid+profile+email" in url or "scope=openid%20profile%20email" in url
    assert "response_type=code" in url
