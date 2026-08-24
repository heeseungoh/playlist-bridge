# playlist-bridge

Transfer playlists between **YouTube Music** and **Spotify** by pasting a link.

Paste a playlist URL from either service and it recreates that playlist on the
other one, matching each track and telling you exactly what it couldn't find.

```bash
python -m playlist_bridge transfer "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
```

Direction is inferred from the link, so the same command works both ways.

## Why the matching matters

The APIs are the easy part. The hard part is that the same song is titled
differently on each service:

| Spotify | YouTube Music |
|---|---|
| `Bohemian Rhapsody - Remastered 2011` | `Bohemian Rhapsody` |
| `Blinding Lights` | `Blinding Lights (Official Video)` |
| `goosebumps` by Travis Scott, Kendrick Lamar | `goosebumps (feat. Kendrick Lamar)` by Travis Scott |

So each track is normalized (remaster tags, `(Official Video)`, `feat.`
credits, accents, `-  Topic` artist suffixes) and then scored on **title**,
**artist**, and **duration**. A large runtime gap is capped hard, which is what
keeps live cuts, extended mixes, and hour-long loops out of your playlist.

Nothing is silently dropped: anything below the confidence threshold goes into a
CSV with the candidates that were rejected and their scores, so you can fix them
in one pass.

## Setup

Requires Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Spotify

Uses OAuth with PKCE, so there's no client secret to store.

1. Create a free app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Add this redirect URI exactly: `http://127.0.0.1:8888/callback`
3. Copy `.env.example` to `.env` and paste in your Client ID

The browser opens once to authorize; the token is cached and refreshed after that.

### YouTube Music

Reading and searching need no auth. *Creating* playlists does, and since there's
no official API it uses browser headers:

```bash
python -m playlist_bridge auth-ytmusic
```

Follow the printed steps (DevTools → Network → copy request headers from any
`/youtubei/v1/` request).

Verify both sides are connected:

```bash
python -m playlist_bridge check
```

## Usage

```bash
# Preview without writing anything
python -m playlist_bridge transfer "<link>" --dry-run

# Name the new playlist
python -m playlist_bridge transfer "<link>" --name "Road Trip 2026"

# Be stricter (fewer wrong matches) or looser (fewer misses)
python -m playlist_bridge transfer "<link>" --threshold 0.75
```

`--dry-run` is worth using first on a big playlist — it does the full match pass
and prints the report without touching your account.

### Output

```
==============================================================
  Discover Weekly   [Spotify -> YouTube Music]
==============================================================
  matched      28 / 30   (93%)
  unmatched     2

  2 low-confidence match(es) worth a look:
    0.71  Frank Ocean - White Ferrari
          -> Frank Ocean - White Ferrari (Blonde)

  Not found on YouTube Music:
    - Some Very Obscure B-Side

  Unmatched detail: reports\unmatched-discover-weekly-20260824-161200.csv
```

New playlists are created **private** on both services.

## Notes

- `ytmusicapi` is unofficial and can break if Google changes its internals.
- Playlists you don't own can be read but not modified.
- Auth tokens are cached in `.cache/` and are gitignored.
