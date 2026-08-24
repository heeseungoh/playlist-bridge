"""Tests for the offline fixture provider and the transfer engine.

These exercise the full pipeline - fetch, match, create, add - without
touching any real service, which is what makes the engine verifiable
when developer credentials aren't available.
"""

import contextlib
import io
import unittest

from playlist_bridge.links import OFFLINE, YTMUSIC, parse_link
from playlist_bridge.models import Track
from playlist_bridge.providers.offline import OfflineProvider
from playlist_bridge.transfer import match_all, transfer


@contextlib.contextmanager
def quiet():
    """Suppress transfer progress output so test runs stay readable."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


class TestOfflineFixture(unittest.TestCase):
    def setUp(self):
        self.provider = OfflineProvider()

    def test_loads_demo_fixture(self):
        playlist = self.provider.fetch_playlist("spotify_demo")
        self.assertEqual(playlist.name, "Spotify Demo Playlist")
        self.assertEqual(len(playlist), 10)

    def test_tracks_have_spotify_shaped_metadata(self):
        track = self.provider.fetch_playlist("spotify_demo").tracks[0]
        self.assertEqual(track.title, "Blinding Lights")
        self.assertEqual(track.artists, ["The Weeknd"])
        self.assertEqual(track.duration_ms, 200040)

    def test_multi_artist_track_preserved(self):
        tracks = self.provider.fetch_playlist("spotify_demo").tracks
        goosebumps = next(t for t in tracks if t.title == "goosebumps")
        self.assertEqual(goosebumps.artists, ["Travis Scott", "Kendrick Lamar"])

    def test_missing_fixture_lists_alternatives(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            self.provider.fetch_playlist("does_not_exist")
        self.assertIn("spotify_demo", str(ctx.exception))


class TestOfflineAsDestination(unittest.TestCase):
    def setUp(self):
        self.provider = OfflineProvider()

    def test_search_finds_exact_track(self):
        target = Track("x", "Blinding Lights", ["The Weeknd"], None, 200040)
        results = self.provider.search_track(target)
        self.assertEqual(results[0].title, "Blinding Lights")

    def test_writes_are_captured_not_sent(self):
        with quiet():
            pid = self.provider.create_playlist("Test", "desc")
            self.provider.add_tracks(pid, ["a", "b", "c"])
        self.assertEqual(self.provider.written[pid], ["a", "b", "c"])


class TestTransferEngine(unittest.TestCase):
    """Offline -> offline, so the whole pipeline runs deterministically."""

    def test_dry_run_writes_nothing(self):
        provider = OfflineProvider()
        with quiet():
            _, results, dest_id = transfer(
                link="offline:spotify_demo",
                source=provider,
                dest=provider,
                source_id="spotify_demo",
                dry_run=True,
            )
        self.assertIsNone(dest_id)
        self.assertEqual(provider.written, {})
        self.assertEqual(len(results), 10)

    def test_full_transfer_creates_and_adds(self):
        source = OfflineProvider()
        dest = OfflineProvider()
        with quiet():
            _, results, dest_id = transfer(
                link="offline:spotify_demo",
                source=source,
                dest=dest,
                source_id="spotify_demo",
                dry_run=False,
            )
        self.assertIsNotNone(dest_id)
        matched = [r for r in results if r.matched]
        self.assertEqual(len(dest.written[dest_id]), len(matched))

    def test_every_track_is_accounted_for(self):
        """No track may be silently dropped - matched or not, it's reported."""
        provider = OfflineProvider()
        playlist = provider.fetch_playlist("spotify_demo")
        results = match_all(playlist, provider, threshold=0.62, progress=False)
        self.assertEqual(len(results), len(playlist))

    def test_impossible_threshold_matches_nothing(self):
        provider = OfflineProvider()
        playlist = provider.fetch_playlist("spotify_demo")
        results = match_all(playlist, provider, threshold=1.01, progress=False)
        self.assertTrue(all(not r.matched for r in results))

    def test_custom_name_used_for_destination(self):
        source = OfflineProvider()
        dest = OfflineProvider()
        with quiet():
            _, _, dest_id = transfer(
                link="offline:spotify_demo",
                source=source,
                dest=dest,
                source_id="spotify_demo",
                name="My Custom Name",
                dry_run=False,
            )
        self.assertIsNotNone(dest_id)


class TestOfflineLinkParsing(unittest.TestCase):
    def test_offline_scheme(self):
        self.assertEqual(parse_link("offline:spotify_demo"), (OFFLINE, "spotify_demo"))

    def test_bare_offline_defaults_to_demo(self):
        self.assertEqual(parse_link("offline:"), (OFFLINE, "spotify_demo"))

    def test_offline_defaults_to_ytmusic_destination(self):
        from playlist_bridge.links import other_provider

        source, _ = parse_link("offline:spotify_demo")
        self.assertEqual(other_provider(source), YTMUSIC)


if __name__ == "__main__":
    unittest.main()
