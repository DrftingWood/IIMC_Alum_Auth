from src.shared.display_name import (
    canonical_display_name,
    mask_email,
    suffix_for_collision,
)


def test_canonical_display_name_basic() -> None:
    assert canonical_display_name("Suresh Iyer", "PGP", 2015) == "Suresh Iyer (PGP 2015)"


def test_canonical_display_name_missing_program_or_batch() -> None:
    assert canonical_display_name("Alone", None, None) == "Alone"
    assert canonical_display_name("Just Program", "LDP", None) == "Just Program (LDP)"
    assert canonical_display_name("Just Batch", None, 2020) == "Just Batch (2020)"


def test_canonical_strips_whitespace() -> None:
    assert canonical_display_name("  Spaced  ", "PGP", 2010) == "Spaced (PGP 2010)"


def test_suffix_for_collision_letters() -> None:
    assert suffix_for_collision(0) == "A"
    assert suffix_for_collision(1) == "B"
    assert suffix_for_collision(25) == "Z"


def test_suffix_for_collision_out_of_range() -> None:
    import pytest

    with pytest.raises(ValueError):
        suffix_for_collision(26)


def test_mask_email_normal() -> None:
    assert mask_email("suresh@gmail.com") == "s••••@gmail.com"


def test_mask_email_single_char_local() -> None:
    assert mask_email("a@x.io") == "a••••@x.io"


def test_mask_email_no_at() -> None:
    assert mask_email("notanemail") == "••••"
