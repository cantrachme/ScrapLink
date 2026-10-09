# Local browser demonstration catalog

All jobs here are fictional ScrapLink demonstration data. Source domains in
listing anchors exercise existing platform-specific URL parsing; they must only
be navigated through the explicit fixture resolver. No genuine platform jobs,
credentials, cookies, scripts or remote resources are supplied.

For each source, listing 1 contains jobs 1 and 2 plus a duplicate. Listing 2
repeats job 1 and adds job 3 and inaccessible job 4. Listing 3 is empty. The server
intentionally returns HTTP 403 for detail 4. Details 1–3 contain complete structured
JobPosting descriptions; detail 2 has an older posting date. Select `any` in manual
demonstrations. Tests freeze time when checking relative date filters.

`__JOB_N__` tokens are replaced with catalog-only numeric IDs by FixtureSite.
Normal fixture workers use fixed IDs so repeated demonstrations preserve job
UUIDs. Automated tests supply random IDs to avoid altering development records.
The server binds only to 127.0.0.1 and serves an explicit file catalog.

Start with `python -m backend.app.workers.run_worker --mode fixture` from the
repository root. See the root README for architecture and verification commands.
