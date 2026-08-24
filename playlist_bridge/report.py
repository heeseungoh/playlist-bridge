"""Transfer report: console summary plus a CSV of anything that didn't match."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from .models import MatchResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"


def _slug(text: str) -> str:
    return re.sub(r"[^\w\-]+", "-", text).strip("-").lower()[:40] or "playlist"


def write_unmatched_csv(results: list[MatchResult], playlist_name: str) -> Path | None:
    """Write unmatched tracks with the candidates we rejected and why."""
    unmatched = [r for r in results if not r.matched]
    if not unmatched:
        return None

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"unmatched-{_slug(playlist_name)}-{stamp}.csv"

    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "source_title", "source_artists", "source_album", "source_duration",
            "best_score", "candidate_1", "score_1",
            "candidate_2", "score_2", "candidate_3", "score_3",
        ])
        for r in unmatched:
            row = [
                r.source.title,
                r.source.artist_str,
                r.source.album or "",
                _fmt_duration(r.source.duration_ms),
                f"{r.score:.3f}" if r.candidates else "no results",
            ]
            for cand, score in r.candidates[:3]:
                row += [str(cand), f"{score:.3f}"]
            row += [""] * (11 - len(row))
            writer.writerow(row)

    return path


def _fmt_duration(ms: int | None) -> str:
    if not ms:
        return ""
    total = ms // 1000
    return f"{total // 60}:{total % 60:02d}"


def print_summary(
    results: list[MatchResult],
    source_label: str,
    dest_label: str,
    playlist_name: str,
    csv_path: Path | None,
    dest_url: str | None,
) -> None:
    matched = [r for r in results if r.matched]
    unmatched = [r for r in results if not r.matched]
    total = len(results)
    rate = (len(matched) / total * 100) if total else 0.0

    print()
    print("=" * 62)
    print(f"  {playlist_name}   [{source_label} -> {dest_label}]")
    print("=" * 62)
    print(f"  matched    {len(matched):>4} / {total}   ({rate:.0f}%)")
    print(f"  unmatched  {len(unmatched):>4}")

    # Flag weak matches so the user knows what to spot-check.
    weak = sorted(
        (r for r in matched if r.score < 0.78), key=lambda r: r.score
    )
    if weak:
        print(f"\n  {len(weak)} low-confidence match(es) worth a look:")
        for r in weak[:10]:
            print(f"    {r.score:.2f}  {r.source}")
            print(f"          -> {r.best}")
        if len(weak) > 10:
            print(f"    ... and {len(weak) - 10} more")

    if unmatched:
        print(f"\n  Not found on {dest_label}:")
        for r in unmatched[:10]:
            print(f"    - {r.source}")
        if len(unmatched) > 10:
            print(f"    ... and {len(unmatched) - 10} more")

    if csv_path:
        print(f"\n  Unmatched detail: {csv_path}")
    if dest_url:
        print(f"  Playlist: {dest_url}")
    print()
