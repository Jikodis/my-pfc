# AI News

Optional. New posts from the AI blogs you follow land on the reMarkable as EPUBs in the `AI News` folder (named `YYYY-MM-DD - Title`, so they sort by age) and as episodes in a private podcast feed. Claude keeps only the posts that match your criteria in `config/ai_news.yaml`.

The folder is the one exception to the reMarkable pages' "never in a folder" rule ([`remarkable.md`](remarkable.md)): these are reading material you go looking for, not pages that need you to act.

## How it runs

The `pfc-ai-news` timer runs `automations/scripts/ai_news.py` daily at 5:30 AM local time on the server.

| Step | Module | Notes |
|---|---|---|
| List posts | `ai_news_sources.py` | `rss` sources read the feed; `index` sources collect links on the index page matching `link` |
| Fetch the article | `ai_news_extract.py` | trafilatura, as written; a blocked page falls back to the feed's content, else its summary (`partial`, no audio) |
| Keep or skip | `ai_news_filter.py` | one `claude -p` call per run, criteria in `config/ai_news.yaml`; posts older than `first_run_days` (14) are skipped without asking |
| EPUB | `ai_news_epub.py` | uploaded with `rmapi put` into `AI News`, or the source's `folder` |
| Audio | `ai_news_tts.py` | Google Cloud Text-to-Speech (`voice` in the config); none for partial posts, `kind: changelog` sources or a source with `audio: false`; stops at `monthly_char_cap` characters a month (`data/.ai-news/tts-usage.json`). Posts that missed their audio that way are read aloud, newest first, once the next month starts |
| Feed | `ai_news_feed.py` | `data/.ai-news/feed/feed.xml`, MP3s older than `audio_keep_days` deleted |

Every finished post is one line in `data/ai-news.ndjson` (schema in [`data-model.md`](data-model.md)), written the moment it finishes, so a run cut short never redoes a post and reuses the MP3s it already made; the run commits it as `ai-news: log YYYY-MM-DD` and pushes. A post that fails is retried on the next two runs, then logged `failed`. Deleting an EPUB on the tablet never brings it back: a run skips any web address already in the log.

## The feed

`<AI_NEWS_FEED_BASE_URL>/p/pod/<AI_NEWS_FEED_SECRET>/feed.xml`, served by `trmnl_serve.py` (the same process and reverse proxy as the TRMNL endpoint, [`install/trmnl-endpoint.md`](install/trmnl-endpoint.md); `/p/*` is already proxied). The secret in the path is the only guard, because a podcast app cannot send a bearer header: never post the URL anywhere. Add the URL to any podcast app that accepts a private RSS feed.

## Setup

1. The reMarkable sign-in from [`remarkable.md`](remarkable.md) § Setup (`rmapi`), and `CLAUDE_CODE_OAUTH_TOKEN` in `.env`.
2. `pip3 install --user trafilatura feedparser lxml`, and `ffmpeg` for joining audio parts.
3. For audio (optional): a Google Cloud project with the Cloud Text-to-Speech API on and an API key restricted to it, ideally with a small budget alert. Put it in `.env` as `GOOGLE_TTS_API_KEY`. Without it you still get the EPUBs.
4. `.env`: `AI_NEWS_FEED_SECRET` (generate with `python3 -c 'import secrets;print(secrets.token_urlsafe(24))'`) and `AI_NEWS_FEED_BASE_URL` (your TRMNL endpoint host, e.g. `https://trmnl.example.com`).
5. Edit `config/ai_news.yaml`: the blogs and, most of all, `criteria` (who you are as a reader and what to keep).
6. `PFC_AI_NEWS=1` in `.env`, then `automations/systemd/install.sh`, then `systemctl --user restart pfc-trmnl-serve`.

The podcast feed needs the TRMNL endpoint running even without a TRMNL device: `pfc-trmnl-serve` serves the feed, refuses to start without `TRMNL_SERVE_TOKEN`, and `install.sh` skips it while that token is unset. Set it up per [`install/trmnl-endpoint.md`](install/trmnl-endpoint.md). Without it you still get the EPUBs.

## Running it by hand

- `python3 automations/scripts/ai_news.py --dry-run --limit 10`: fetch and decide, change nothing.
- `python3 automations/scripts/ai_news.py`: one real run.
- `journalctl --user -u pfc-ai-news -n 50`: the last run.
- Tests: `pytest automations/scripts/tests/test_ai_news.py` (the fetch and EPUB tests skip without trafilatura, feedparser and lxml).

A source's `weekly_cap` keeps at most that many of its posts a week, Monday to Sunday: Claude ranks the ones it keeps and the rest are logged `over the weekly limit`. `/pfc-usage-audit` lists recent skips so you can tune the criteria.
