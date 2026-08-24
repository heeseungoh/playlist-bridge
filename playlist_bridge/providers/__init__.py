from .base import AuthError, Provider

__all__ = ["AuthError", "Provider", "get_provider"]


def get_provider(name: str):
    """Lazily construct a provider so we only auth what we actually use."""
    if name == "spotify":
        from .spotify import SpotifyProvider

        return SpotifyProvider()
    if name == "ytmusic":
        from .ytmusic import YTMusicProvider

        return YTMusicProvider()
    raise ValueError(f"Unknown provider: {name}")
