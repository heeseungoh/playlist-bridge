"""Tests for playlist link parsing."""

import unittest

from playlist_bridge.links import SPOTIFY, YTMUSIC, LinkError, other_provider, parse_link


class TestSpotifyLinks(unittest.TestCase):
    PID = "37i9dQZF1DXcBWIGoYBM5M"

    def test_standard_url(self):
        self.assertEqual(
            parse_link(f"https://open.spotify.com/playlist/{self.PID}"),
            (SPOTIFY, self.PID),
        )

    def test_share_url_with_si_param(self):
        self.assertEqual(
            parse_link(f"https://open.spotify.com/playlist/{self.PID}?si=abc123"),
            (SPOTIFY, self.PID),
        )

    def test_uri_form(self):
        self.assertEqual(
            parse_link(f"spotify:playlist:{self.PID}"), (SPOTIFY, self.PID)
        )

    def test_locale_path(self):
        self.assertEqual(
            parse_link(f"https://open.spotify.com/intl-de/playlist/{self.PID}"),
            (SPOTIFY, self.PID),
        )

    def test_missing_scheme(self):
        self.assertEqual(
            parse_link(f"open.spotify.com/playlist/{self.PID}"), (SPOTIFY, self.PID)
        )

    def test_surrounding_whitespace(self):
        self.assertEqual(
            parse_link(f"  https://open.spotify.com/playlist/{self.PID}  "),
            (SPOTIFY, self.PID),
        )

    def test_album_link_rejected(self):
        with self.assertRaises(LinkError):
            parse_link("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3")


class TestYouTubeLinks(unittest.TestCase):
    PID = "PLi8xM09IGQqUfV7qpngFdIYoZ5yCgxUjY"

    def test_music_youtube_playlist(self):
        self.assertEqual(
            parse_link(f"https://music.youtube.com/playlist?list={self.PID}"),
            (YTMUSIC, self.PID),
        )

    def test_plain_youtube_playlist(self):
        self.assertEqual(
            parse_link(f"https://www.youtube.com/playlist?list={self.PID}"),
            (YTMUSIC, self.PID),
        )

    def test_watch_url_with_list_param(self):
        self.assertEqual(
            parse_link(f"https://www.youtube.com/watch?v=abc&list={self.PID}"),
            (YTMUSIC, self.PID),
        )

    def test_single_video_rejected_with_guidance(self):
        with self.assertRaises(LinkError) as ctx:
            parse_link("https://youtube.com/watch?v=dQw4w9WgXcQ")
        # The message should tell the user what to copy instead.
        self.assertIn("playlist", str(ctx.exception).lower())


class TestInvalidLinks(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(LinkError):
            parse_link("")

    def test_whitespace_only(self):
        with self.assertRaises(LinkError):
            parse_link("   ")

    def test_unrelated_domain(self):
        with self.assertRaises(LinkError):
            parse_link("https://soundcloud.com/some/playlist")

    def test_garbage(self):
        with self.assertRaises(LinkError):
            parse_link("notalink")


class TestBidirectional(unittest.TestCase):
    """Transfer must work in both directions, inferred from the link."""

    SPOTIFY_LINK = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
    YTMUSIC_LINK = "https://music.youtube.com/playlist?list=PLi8xM09IGQqU"

    def test_other_provider_flips_both_ways(self):
        self.assertEqual(other_provider(SPOTIFY), YTMUSIC)
        self.assertEqual(other_provider(YTMUSIC), SPOTIFY)

    def test_spotify_link_routes_to_ytmusic(self):
        source, _ = parse_link(self.SPOTIFY_LINK)
        self.assertEqual(source, SPOTIFY)
        self.assertEqual(other_provider(source), YTMUSIC)

    def test_ytmusic_link_routes_to_spotify(self):
        source, _ = parse_link(self.YTMUSIC_LINK)
        self.assertEqual(source, YTMUSIC)
        self.assertEqual(other_provider(source), SPOTIFY)

    def test_direction_is_symmetric(self):
        for link in (self.SPOTIFY_LINK, self.YTMUSIC_LINK):
            with self.subTest(link=link):
                source, _ = parse_link(link)
                dest = other_provider(source)
                self.assertNotEqual(source, dest)
                # Flipping twice returns to the original service.
                self.assertEqual(other_provider(dest), source)


if __name__ == "__main__":
    unittest.main()
