# Help Center Mirror

A read-only mirror of **help.sidelineswap.com** kept in Git. A scheduled GitHub
Action pulls every published article from the Zendesk Guide API once a day and
commits it here as Markdown. Claude skills read from this repo instead of
scraping Zendesk live, so they always have a fresh, complete copy without paying
the cost of a full pull each time.

**Zendesk stays the source of truth.** This repo is only ever written *to* by the
sync job, and never written *back* to Zendesk. Edit articles in Zendesk, not here.

## What the sync produces

- `articles/<id>-<slug>.md` — one file per published article. YAML frontmatter
  (id, title, section, category, labels, updated_at, url) plus the body as Markdown.
- `index.md` — human-readable table of contents, grouped by category and section.
- `index.json` — machine-readable index for skills: `{ id, title, section, category,
  labels, updated_at, url, file }` per article. A skill reads this to find the right
  article, then reads just that one `.md` file.

## One-time setup

You'll do steps 1–2 and 4; step 3 is just dropping these files in.

1. **Create a new repo.** On GitHub: **New repository** → name it something like
   `help-center-mirror` → Private → **Create**. (Private is fine — the Action still runs.)

2. **Add these files.** Either drag this whole folder into the repo via GitHub's web
   uploader, or `git clone` the empty repo, copy these files in, and push. The layout
   must stay as-is:
   ```
   .github/workflows/sync-help-center.yml
   scripts/sync.py
   requirements.txt
   .gitignore
   README.md
   ```
   (`articles/`, `index.md`, and `index.json` don't exist yet — the first run creates them.)

3. **Confirm Actions can write.** The workflow already requests write permission
   (`permissions: contents: write`), which is enough on a normal repo. If your org
   locks this down, go to **Settings → Actions → General → Workflow permissions** and
   set **Read and write permissions**.

4. **Run it once by hand.** Go to the **Actions** tab → **Sync Help Center** →
   **Run workflow**. Watch it run. On success it commits `articles/`, `index.md`, and
   `index.json`. After that it runs itself daily.

## Verify the first run (step 5 of the plan)

Open a few files in `articles/` and check:

- The body converted cleanly — lists, links, and headings look right, no leftover HTML tags.
- `section`, `category`, and `labels` in the frontmatter match what's in Zendesk.
- `index.md` article count matches roughly what you expect to be published.

If a conversion looks off, note which article and we'll adjust the script.

## Changing the schedule

Edit the `cron` line in `.github/workflows/sync-help-center.yml`. Cron is **UTC**.
`0 8 * * *` is 08:00 UTC (~2am Mountain). Daily is plenty for docs, but you can run
it more often if you want.

## Configuration

Set at the top of the workflow (the `env:` block on the "Run sync" step):

- `ZENDESK_SUBDOMAIN` — `sidelineswap`
- `HELP_CENTER_LOCALE` — `en-us`

No credentials are needed: the sync only reads **published** articles, which are public.
(If we ever need unpublished/internal content, that would require a Zendesk API token —
not the case today.)

## How skills consume this (next phase)

Skills that need help content read `index.json` from this repo — either off disk (if
the skill runs with this repo checked out) or over HTTPS from `raw.githubusercontent.com`
— find the relevant article(s) by title/label/section, then read the specific
`articles/*.md` file. The flagging behavior ("when planning a ticket, check the docs and
say which articles need updating") is built on top of this and comes next.
