# Decisions

Choices made without a team decision, newest last. Each says what, why, and how to undo it.

## D1. This branch includes chay_branch's unmerged backend work
- **What:** `integration/full-stack` was created from `origin/main` and then had `origin/chay_branch` merged in (merge commit, no rebase).
- **Why:** `main` only has the DB skeleton (`db.py`, `models.py`, Alembic). The routes, schemas, matching logic and `testcases.md` exist only on `chay_branch`, which is not merged into `main`. Integration needs the real backend.
- **Consequence:** merging this PR also merges chay_branch's work. The PR description must say so.
- **Undo:** if chay_branch changes, merge its new commits into this branch the same way (no force-push).

## D2. Merge conflict resolutions
- `requirements.txt`: both sides listed the same packages and differed only by a trailing newline; main's version (with newline) was kept.
- `.gitignore`: chay_branch moved it to `backend/.gitignore`; the root file was kept (it now covers the whole repo, including `scraper/`) and `backend/.gitignore` is unchanged.

## D3. Firecrawl is not part of this repository
- A local `firecrawl/` clone is git-ignored. Firecrawl is an external dependency configured by `FIRECRAWL_API_URL` / `FIRECRAWL_API_KEY`.
