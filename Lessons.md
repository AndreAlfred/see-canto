# Lessons — Voice Trainer

A running reliquary of wrong turns, mistakes, and hard-won corrections, so we
don't repeat them.

**Rules for this file**
- Add an entry whenever something goes wrong, surprises us, or we course-correct.
- Prune entries once they go stale or stop being relevant.
- When a lesson proves durable and general, **promote** it into
  [CLAUDE.md](CLAUDE.md) as a standing rule and trim it back here.

Format — `### YYYY-MM-DD — Short title`, then: what happened / why it bit us /
the fix.

---

### 2026-07-07 — Deleting a word doesn't remove it from git history
**What happened:** Before the first public push we needed to remove a product
name from a design doc. Editing the current file wasn't enough — the word lived
in every past commit's snapshot and would have stayed world-readable via
`git checkout <old-commit>`.
**Fix:** Rewrote all history with `git filter-repo --replace-text` *before*
pushing, then verified across the working tree, commit messages, and full history.
**Rule:** Scrub sensitive strings BEFORE the first push. Afterward the same fix
needs a force-push and may already be cached upstream.

### 2026-08-05 — Agent-written plan docs smuggle in absolute paths
**What happened:** The intonation-gauge implementation plan hard-coded
`/Users/<name>/voice-trainer/venv/bin/python` in 12 places — the agent wrote the
absolute interpreter path because that's what it needed to run commands, and the
doc got committed and pushed. The same leak is still sitting on `main` in
`docs/superpowers/plans/2026-07-09-spectrogram-resolution.md` (5 occurrences,
including worktree paths).
**Why it bit us:** the privacy rule in [CLAUDE.md](CLAUDE.md) is real but was
only being enforced on code. Markdown under `docs/plans/` skips the attention
`.py` files get in review, so it's the path of least resistance for a leak.
**Fix:** rewrote them as repo-relative `venv/bin/python`. Because this repo
squash-merges every PR, stripping the paths from the branch tip is enough to
keep them out of `main`'s history — but they remain in the *branch's* pushed
commits until that branch is deleted (see the 2026-07-07 history-scrub lesson).
**Rule:** plan and spec docs are tracked files — write commands repo-relative
from the start, and grep `docs/` for `/Users/` before pushing.

### 2026-07-07 — Git invents a leaky author email from your machine
**What happened:** With no `user.email` configured, git authored commits as
`username@hostname.local`, exposing the local username and machine name in
public commit metadata.
**Fix:** Set a repo-local git identity using the GitHub `noreply` email, so new
commits are clean.
**Open item:** Commits made before this fix still carry the old `.local` email;
scrubbing those needs a history rewrite + force-push (optional, low urgency —
it's a non-deliverable address).
