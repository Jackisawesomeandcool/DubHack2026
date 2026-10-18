"""Which AI provider does search + vision: Gemini (default) or xAI Grok.
Picked from the keys present in backend/.env."""

import config


class LLMError(Exception):
    pass


def provider() -> str:
    if config.GEMINI_API_KEY:
        return "gemini"
    if config.XAI_API_KEY:
        return "xai"
    return ""


def configured() -> bool:
    return bool(provider())


def search_products(prompt: str, category: str | None, exclude: list[str], count: int) -> list[dict]:
    p = provider()
    try:
        if p == "gemini":
            import gemini
            return gemini.search_products(prompt, category, exclude, count)
        if p == "xai":
            import grok
            return grok.search_products(prompt, category, exclude, count)
    except Exception as err:  # noqa: BLE001 — unify provider errors
        raise LLMError(str(err)) from err
    raise LLMError("No AI provider configured (set GEMINI_API_KEY in backend/.env)")


def pick_products(prompt: str, lines: list[str], count: int) -> list[dict]:
    """Catalog ranking: which of these numbered products answer the request. [{"n", "why"}], best first."""
    p = provider()
    try:
        if p == "gemini":
            import gemini
            return gemini.pick_products(prompt, lines, count)
        if p == "xai":
            import grok
            return grok.pick_products(prompt, lines, count)
    except Exception as err:  # noqa: BLE001
        raise LLMError(str(err)) from err
    raise LLMError("No AI provider configured (set GEMINI_API_KEY in backend/.env)")


def pick_index(question: str, jpeg_blobs: list[bytes]) -> int:
    p = provider()
    if p == "gemini":
        import gemini
        return gemini.pick_index(question, jpeg_blobs)
    if p == "xai":
        import grok
        return grok.pick_index(question, jpeg_blobs)
    return 0
