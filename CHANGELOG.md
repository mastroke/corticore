# Changelog

All notable changes to corticore are documented here. This project adheres to
[Semantic Versioning](https://semver.org/) and the format is loosely based on
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Feature backlog workflow: a local (gitignored) `feature-list.csv` backlog and
  a `corticore-feature-builder` project skill that drives researched,
  vision-checked, test-backed feature work, plus a `ROADMAP.md`.
- Metadata-filtered recall (`F001`): `recall(query, filters={...})` narrows
  candidates to memories whose metadata matches every key/value pair before
  scoring. Omitting `filters` preserves prior behavior exactly.
