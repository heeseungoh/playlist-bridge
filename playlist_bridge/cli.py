"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from .links import LinkError, other_provider, parse_link
from .providers import get_provider
from .providers.base import AuthError
from .report import print_summary, write_unmatched_csv
from .transfer import transfer


def cmd_transfer(args: argparse.Namespace) -> int:
    try:
        source_name, playlist_id = parse_link(args.link)
    except LinkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    dest_name = args.to or other_provider(source_name)
    if dest_name == source_name:
        print("Error: source and destination are the same service.", file=sys.stderr)
        return 2

    try:
        source = get_provider(source_name)
        dest = get_provider(dest_name)
    except AuthError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 3

    try:
        playlist, results, dest_id = transfer(
            link=args.link,
            source=source,
            dest=dest,
            source_id=playlist_id,
            name=args.name,
            threshold=args.threshold,
            dry_run=args.dry_run,
        )
    except AuthError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"\nTransfer failed: {exc}", file=sys.stderr)
        return 1

    if not results:
        return 0

    csv_path = write_unmatched_csv(results, playlist.name)
    print_summary(
        results,
        source.label,
        dest.label,
        playlist.name,
        csv_path,
        dest.playlist_url(dest_id) if dest_id else None,
    )
    return 0


def cmd_auth_ytmusic(args: argparse.Namespace) -> int:
    from .providers.ytmusic import SETUP_HELP, YTMusicProvider

    print(SETUP_HELP)
    print("Paste the copied request headers below.")
    print("Finish with a blank line, then Ctrl+Z + Enter (Windows).\n")

    raw = sys.stdin.read().strip()
    if not raw:
        print("Nothing pasted, aborting.", file=sys.stderr)
        return 2

    try:
        path = YTMusicProvider.setup_auth(raw)
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nSaved to {path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Verify each provider is reachable and authenticated."""
    ok = True

    print("Spotify:")
    try:
        sp = get_provider("spotify")
        me = sp._request("GET", "/me")
        print(f"  connected as {me.get('display_name') or me.get('id')}")
    except AuthError as exc:
        print(f"  not configured\n    {str(exc).splitlines()[0]}")
        ok = False
    except Exception as exc:
        print(f"  error: {exc}")
        ok = False

    print("YouTube Music:")
    try:
        yt = get_provider("ytmusic")
        yt.client.search("test", filter="songs", limit=1)
        print("  search reachable (unauthenticated)")
        try:
            yt.authed.get_library_playlists(limit=1)
            print("  authenticated - can create playlists")
        except AuthError:
            print("  not authenticated - run: python -m playlist_bridge auth-ytmusic")
            ok = False
    except Exception as exc:
        print(f"  error: {exc}")
        ok = False

    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playlist-bridge",
        description="Transfer playlists between YouTube Music and Spotify.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("transfer", help="Transfer a playlist from a pasted link.")
    t.add_argument("link", help="Spotify or YouTube Music playlist URL")
    t.add_argument("--to", choices=["spotify", "ytmusic"],
                   help="Destination service (default: the other one)")
    t.add_argument("--name", help="Name for the new playlist (default: source name)")
    t.add_argument("--threshold", type=float, default=0.62,
                   help="Match confidence 0-1 required to accept (default: 0.62)")
    t.add_argument("--dry-run", action="store_true",
                   help="Match and report without writing anything")
    t.set_defaults(func=cmd_transfer)

    a = sub.add_parser("auth-ytmusic", help="Set up YouTube Music browser auth.")
    a.set_defaults(func=cmd_auth_ytmusic)

    c = sub.add_parser("check", help="Verify both services are connected.")
    c.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which blows up on emoji and CJK
    # track titles. Force UTF-8 and degrade gracefully rather than crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
