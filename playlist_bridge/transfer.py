"""Transfer orchestration: fetch, match, then write."""

from __future__ import annotations

import sys

from .matching import pick_best
from .models import MatchResult, Playlist
from .providers.base import Provider


def match_all(
    playlist: Playlist,
    dest: Provider,
    threshold: float,
    progress: bool = True,
) -> list[MatchResult]:
    """Search the destination for every source track and score the candidates."""
    results: list[MatchResult] = []
    total = len(playlist.tracks)

    for i, track in enumerate(playlist.tracks, 1):
        if progress:
            label = str(track)
            if len(label) > 48:
                label = label[:45] + "..."
            print(f"  [{i:>3}/{total}] {label:<52}", end="", flush=True)

        try:
            candidates = dest.search_track(track)
        except Exception as exc:
            print(f"  search error: {exc}")
            results.append(MatchResult(source=track, best=None, score=0.0))
            continue

        result = pick_best(track, candidates, threshold=threshold)
        results.append(result)

        if progress:
            print(f" {result.score:.2f} {'ok' if result.matched else 'MISS'}")

    return results


def transfer(
    link: str,
    source: Provider,
    dest: Provider,
    source_id: str,
    name: str | None = None,
    threshold: float = 0.62,
    dry_run: bool = False,
) -> tuple[Playlist, list[MatchResult], str | None]:
    """Run a full transfer. Returns (source_playlist, results, dest_playlist_id)."""
    print(f"\nReading playlist from {source.label}...")
    playlist = source.fetch_playlist(source_id)
    print(f"  \"{playlist.name}\" - {len(playlist)} track(s)")

    if not playlist.tracks:
        print("  Playlist is empty, nothing to do.")
        return playlist, [], None

    print(f"\nMatching against {dest.label}...")
    results = match_all(playlist, dest, threshold)

    matched = [r for r in results if r.matched]
    if dry_run:
        print(f"\nDry run - would add {len(matched)} track(s). Nothing was written.")
        return playlist, results, None

    if not matched:
        print("\nNo tracks matched, so no playlist was created.")
        return playlist, results, None

    target_name = name or playlist.name
    print(f"\nCreating \"{target_name}\" on {dest.label}...")
    dest_id = dest.create_playlist(
        target_name,
        f"Transferred from {source.label} by playlist-bridge.",
    )

    print(f"Adding {len(matched)} track(s)...")
    dest.add_tracks(dest_id, [r.best.id for r in matched])

    return playlist, results, dest_id
