"""Tests for track matching heuristics.

These cover the cases that actually break playlist transfers: remaster tags,
official-video suffixes, feat. credits moving between title and artist, and
live or extended versions that share a title but aren't the same recording.
"""

import unittest

from playlist_bridge.matching import (
    artist_score,
    duration_score,
    normalize_artist,
    normalize_title,
    pick_best,
    score_candidate,
    title_score,
)
from playlist_bridge.models import Track

THRESHOLD = 0.62


def track(title, artists=(), duration_ms=None, isrc=None, tid="x"):
    return Track(
        id=tid,
        title=title,
        artists=list(artists),
        duration_ms=duration_ms,
        isrc=isrc,
    )


class TestNormalizeTitle(unittest.TestCase):
    def test_strips_remaster_suffix(self):
        self.assertEqual(
            normalize_title("Bohemian Rhapsody - Remastered 2011"),
            "bohemian rhapsody",
        )

    def test_strips_parenthetical_remaster(self):
        self.assertEqual(
            normalize_title("Come Together (2019 Remaster)"), "come together"
        )

    def test_strips_official_video_markers(self):
        for variant in [
            "Blinding Lights (Official Video)",
            "Blinding Lights (Official Music Video)",
            "Blinding Lights [Official Audio]",
            "Blinding Lights - Official Video",
            "Blinding Lights (Lyrics)",
        ]:
            with self.subTest(variant=variant):
                self.assertEqual(normalize_title(variant), "blinding lights")

    def test_strips_feat_credits(self):
        self.assertEqual(
            normalize_title("goosebumps (feat. Kendrick Lamar)"), "goosebumps"
        )
        self.assertEqual(normalize_title("Head & Heart ft. MNEK"), "head and heart")

    def test_keeps_feat_when_asked(self):
        self.assertIn(
            "kendrick",
            normalize_title("goosebumps (feat. Kendrick Lamar)", drop_feat=False),
        )

    def test_normalizes_accents_and_punctuation(self):
        self.assertEqual(normalize_title("Café del Mar"), "cafe del mar")
        self.assertEqual(normalize_title("Don't Stop!"), "don t stop")

    def test_ampersand_becomes_and(self):
        self.assertEqual(normalize_title("Head & Heart"), "head and heart")

    def test_does_not_strip_meaningful_parentheses(self):
        # A remix is a genuinely different recording, so it must survive.
        self.assertIn("imanbek remix", normalize_title("Roses (Imanbek Remix)"))


class TestNormalizeArtist(unittest.TestCase):
    def test_strips_youtube_topic_suffix(self):
        self.assertEqual(normalize_artist("Eagles - Topic"), "eagles")

    def test_strips_trailing_vevo(self):
        self.assertEqual(normalize_artist("Rihanna VEVO"), "rihanna")


class TestDurationScore(unittest.TestCase):
    def test_identical_is_perfect(self):
        self.assertEqual(duration_score(200_000, 200_000), 1.0)

    def test_within_three_seconds_is_perfect(self):
        self.assertEqual(duration_score(200_000, 202_000), 1.0)

    def test_thirty_seconds_apart_is_zero(self):
        self.assertEqual(duration_score(200_000, 230_000), 0.0)

    def test_unknown_duration_is_neutral(self):
        self.assertEqual(duration_score(None, 200_000), 0.5)
        self.assertEqual(duration_score(200_000, None), 0.5)

    def test_tapers_between(self):
        mid = duration_score(200_000, 215_000)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 1.0)


class TestArtistScore(unittest.TestCase):
    def test_exact_primary_artist(self):
        self.assertEqual(artist_score(["Queen"], ["Queen"]), 1.0)

    def test_ignores_topic_suffix(self):
        self.assertEqual(artist_score(["Eagles"], ["Eagles - Topic"]), 1.0)

    def test_collaborator_split_across_services(self):
        # Spotify lists both artists; YouTube puts one in the title.
        self.assertEqual(
            artist_score(["Travis Scott", "Kendrick Lamar"], ["Travis Scott"]), 1.0
        )

    def test_different_artists_score_low(self):
        self.assertLess(artist_score(["The Beatles"], ["Boyz II Men"]), 0.5)

    def test_empty_is_zero(self):
        self.assertEqual(artist_score([], ["Queen"]), 0.0)


class TestScoreCandidate(unittest.TestCase):
    def test_isrc_match_short_circuits(self):
        a = track("Whatever", ["Someone"], 200_000, isrc="USRC12345678")
        b = track("Totally Different", ["Other"], 900_000, isrc="USRC12345678")
        self.assertEqual(score_candidate(a, b), 1.0)

    def test_remaster_variant_matches(self):
        src = track("Bohemian Rhapsody - Remastered 2011", ["Queen"], 354_000)
        cand = track("Bohemian Rhapsody", ["Queen"], 355_000)
        self.assertGreaterEqual(score_candidate(src, cand), THRESHOLD)

    def test_official_video_variant_matches(self):
        src = track("Blinding Lights (Official Video)", ["The Weeknd"], 200_000)
        cand = track("Blinding Lights", ["The Weeknd"], 201_000)
        self.assertGreaterEqual(score_candidate(src, cand), THRESHOLD)

    def test_feat_moved_into_title_matches(self):
        src = track("goosebumps", ["Travis Scott", "Kendrick Lamar"], 244_000)
        cand = track("goosebumps (feat. Kendrick Lamar)", ["Travis Scott"], 243_000)
        self.assertGreaterEqual(score_candidate(src, cand), THRESHOLD)

    def test_accented_title_matches(self):
        src = track("Cafe Del Mar", ["Energy 52"], 420_000)
        cand = track("Café del Mar", ["Energy 52"], 418_000)
        self.assertGreaterEqual(score_candidate(src, cand), THRESHOLD)

    def test_live_version_rejected(self):
        # Same title and artist, but three minutes longer.
        src = track("Hotel California", ["Eagles"], 391_000)
        cand = track("Hotel California (Live 1977)", ["Eagles"], 570_000)
        self.assertLess(score_candidate(src, cand), THRESHOLD)

    def test_same_title_different_artist_rejected(self):
        src = track("Yesterday", ["The Beatles"], 125_000)
        cand = track("Yesterday", ["Boyz II Men"], 240_000)
        self.assertLess(score_candidate(src, cand), THRESHOLD)

    def test_hour_long_loop_rejected(self):
        src = track("Dreams", ["Fleetwood Mac"], 257_000)
        cand = track("Dreams (Slowed + Reverb) 1 HOUR LOOP", ["lofi guy"], 3_600_000)
        self.assertLess(score_candidate(src, cand), THRESHOLD)

    def test_duration_gap_is_capped(self):
        # Even a perfect title and artist can't pass on a huge runtime gap.
        src = track("Some Song", ["Some Artist"], 200_000)
        cand = track("Some Song", ["Some Artist"], 600_000)
        self.assertLessEqual(score_candidate(src, cand), 0.55)

    def test_missing_durations_still_match_on_text(self):
        src = track("Bohemian Rhapsody", ["Queen"], None)
        cand = track("Bohemian Rhapsody", ["Queen"], None)
        self.assertGreaterEqual(score_candidate(src, cand), THRESHOLD)

    def test_scoring_is_symmetric_across_direction(self):
        """A Spotify-style and YouTube-style entry must match either way round.

        Transfer runs in both directions, so scoring can't favor one service's
        title conventions over the other's.
        """
        spotify_style = track("Blinding Lights", ["The Weeknd"], 200_000)
        youtube_style = track(
            "Blinding Lights (Official Video)", ["The Weeknd - Topic"], 201_000
        )
        forward = score_candidate(spotify_style, youtube_style)
        backward = score_candidate(youtube_style, spotify_style)
        self.assertGreaterEqual(forward, THRESHOLD)
        self.assertGreaterEqual(backward, THRESHOLD)
        self.assertAlmostEqual(forward, backward, places=6)


class TestPickBest(unittest.TestCase):
    def test_no_candidates_returns_unmatched(self):
        result = pick_best(track("X", ["Y"]), [])
        self.assertFalse(result.matched)
        self.assertEqual(result.score, 0.0)

    def test_picks_highest_scoring(self):
        src = track("Blinding Lights", ["The Weeknd"], 200_000)
        wrong = track("Blinding Lights", ["Karaoke Band"], 200_000, tid="w")
        right = track("Blinding Lights", ["The Weeknd"], 201_000, tid="r")
        result = pick_best(src, [wrong, right])
        self.assertTrue(result.matched)
        self.assertEqual(result.best.id, "r")

    def test_below_threshold_is_unmatched_but_keeps_candidates(self):
        src = track("Yesterday", ["The Beatles"], 125_000)
        cand = track("Yesterday", ["Boyz II Men"], 240_000)
        result = pick_best(src, [cand])
        self.assertFalse(result.matched)
        self.assertIsNone(result.best)
        # Rejected candidates still get reported so the user can review them.
        self.assertEqual(len(result.candidates), 1)

    def test_threshold_is_respected(self):
        src = track("Yesterday", ["The Beatles"], 125_000)
        cand = track("Yesterday", ["Boyz II Men"], 240_000)
        self.assertTrue(pick_best(src, [cand], threshold=0.1).matched)

    def test_keeps_limited_candidates(self):
        src = track("Song", ["Artist"], 200_000)
        cands = [track("Song", ["Artist"], 200_000, tid=str(i)) for i in range(10)]
        self.assertEqual(len(pick_best(src, cands, keep=3).candidates), 3)


class TestTitleScore(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(title_score("Dreams", "Dreams"), 1.0)

    def test_empty(self):
        self.assertEqual(title_score("", "Dreams"), 0.0)


if __name__ == "__main__":
    unittest.main()
