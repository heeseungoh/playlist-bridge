# playlist-bridge

As a YouTube Music user with genuinely excellent taste, I couldn't share my
playlists with any of my friends on Spotify. So I built this: a command line
tool that moves a playlist between the two services from a pasted link.

Paste a playlist URL from either service and it rebuilds that playlist on the
other one, matching each track and telling you exactly what it couldn't find.

```bash
python -m playlist_bridge transfer "https://music.youtube.com/playlist?list=PLi8xM09IGQqU"
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

## Trying it without credentials

Spotify requires a registered developer app before you can read anything,
which is a hard stop if you can't create one. There's an offline fixture
provider so you can still exercise the whole pipeline:

```bash
python -m playlist_bridge transfer "offline:spotify_demo" --to ytmusic --dry-run
```

That reads a canned playlist with Spotify-shaped metadata (remaster tags,
multi-artist tracks, accented titles), runs a real search against YouTube
Music, and prints the full match report — without any credentials.

It's a development and testing aid, not a way to move real playlists.

## Notes

- `ytmusicapi` is unofficial and can break if Google changes its internals.
- Playlists you don't own can be read but not modified.
- Auth tokens are cached in `.cache/` and are gitignored.

## Tests

```bash
python -m unittest discover -s tests
```

Stdlib `unittest`, no extra dependencies. The suite covers matching
heuristics, link parsing in both directions, and a full transfer through
the offline provider.
