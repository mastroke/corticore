# Changelog

All notable changes to corticore are documented here. This project adheres to
[Semantic Versioning](https://semver.org/) and the format is loosely based on
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- JSONL import/export (`F006`): `export_jsonl(path)` and `import_jsonl(path)`
  serialize a store's memories to/from JSON Lines for backup, migration, and
  debugging. Import is idempotent (upsert by id).
- Namespaced memories (`F002`): `remember(..., namespace=...)` and
  `recall(..., namespace=...)` isolate memories per user/session/agent in a
  single store. Namespaces never leak across `recall()` and are never
  consolidated together by `reflect()`. Defaults to `"default"`, preserving
  single-tenant behavior.
- SQLite schema migrations (`F003`): the default store tracks its schema
  version via `PRAGMA user_version` and applies ordered, idempotent
  migrations on connect, upgrading older databases in place without data loss.
- Feature backlog workflow: a local (gitignored) `feature-list.csv` backlog and
  a `corticore-feature-builder` project skill that drives researched,
  vision-checked, test-backed feature work, plus a `ROADMAP.md`.
- Metadata-filtered recall (`F001`): `recall(query, filters={...})` narrows
  candidates to memories whose metadata matches every key/value pair before
  scoring. Omitting `filters` preserves prior behavior exactly.
