def canonical_display_name(name: str, program: str | None, batch: int | None) -> str:
    """Build the canonical display string: 'Name (Program Year)'."""
    base = name.strip()
    parts: list[str] = []
    if program:
        parts.append(program.strip())
    if batch:
        parts.append(str(batch))
    if not parts:
        return base
    return f"{base} ({' '.join(parts)})"


def suffix_for_collision(index: int) -> str:
    """0 -> 'A', 1 -> 'B', ..., 25 -> 'Z'. ValueError beyond 25."""
    if not 0 <= index <= 25:
        raise ValueError(f"collision suffix index out of range: {index}")
    return chr(ord("A") + index)


def mask_email(email: str) -> str:
    """Mask an email for safe display: 'suresh@gmail.com' -> 's••••@gmail.com'."""
    if "@" not in email:
        return "••••"
    local, _, domain = email.partition("@")
    if not local:
        return f"••••@{domain}"
    return f"{local[0]}••••@{domain}"
