class ProviderError(RuntimeError):
    """A sanitized, user-safe provider failure."""


def safe_error(provider: str, error: Exception) -> ProviderError:
    status = getattr(error, "status_code", None)
    labels = {
        401: "The configured key was not accepted.",
        403: "This account lacks access.",
        429: "The provider is rate limited or its quota is exhausted.",
    }
    return ProviderError(
        f"{provider}: "
        + labels.get(status, f"{type(error).__name__}. Retry explicitly or use completed local evidence.")
    )
