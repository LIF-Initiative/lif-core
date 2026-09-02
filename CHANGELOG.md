<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Unique indexes added for ValueSets and ValueSetValues
- Minor adjustments to data to comply with uniqueness indexes
- Pull request template with comprehensive contribution guidelines
- MIGRATION.md for tracking breaking changes and upgrade paths
- CHANGELOG.md for tracking all notable changes

### Changed

- Identity Mapper `save_mappings` is now all-or-nothing: a single transaction with a single commit,
  so a mid-batch failure rolls back the entire batch instead of leaving partial saves; storage DB
  work is offloaded off the FastAPI event loop via `asyncio.to_thread`, and per-request delete/read
  round trips are reduced
- Identity Mapper `save_mappings` stages all inserts and flushes once instead of flushing per row;
  the mapping id is generated in Python rather than by the column default. Measured against MariaDB,
  a 500-mapping batch goes from 12801 ms to 159 ms (~80x) and from 501 SQL statements to 2
- Identity Mapper `save_mappings` returns one entry per persisted row, so duplicate keys in one
  batch no longer produce two response entries for the same row
- `IDENTITY_MAPPER_DB_POOL_PRE_PING` now defaults to `true` and is wired into the ECS task
  definition, replacing the connection validation lost with the startup `SELECT 1`

### Deprecated

### Removed

### Fixed

- Identity Mapper `save_mappings` rejects a `mapping_id` the caller does not own, or one that
  disagrees with the target system fields sent with it, as a 400 instead of failing the unique
  constraint as a 500 and discarding the rest of the batch
- `IDENTITY_MAPPER_DB_CONNECT_ARGS` is parsed from JSON into a dict; the raw string was passed
  straight to SQLAlchemy, which expects a mapping

### Security

---

## Example Format

Below is an example of how to document changes. Remove this section once you
have real entries.

## [1.2.0] - 2025-01-15

### Added

- New `/v2/learner` API endpoint with improved data model
- Support for user roles in the authentication system
- Database migration script for version 1.2.0
- Configuration validation on startup

### Changed

- **BREAKING:** Environment variable naming convention now uses `LIF_DATABASE_*`
  prefix instead of `LIF_DB_*`
- Improved error messages in GraphQL API responses
- Updated Python dependencies to latest compatible versions

### Deprecated

- `/v1.1/learner` endpoint will be removed in version 2.0.0 (use `/v2/learner` instead)

### Removed

- **BREAKING:** Removed deprecated `/v1.0/learner` endpoint (deprecated in 1.0.0)
- Legacy authentication middleware

### Fixed

- Fixed race condition in concurrent database writes
- Resolved memory leak in long-running orchestrator processes
- Corrected timezone handling in audit logs

### Security

- Updated dependency `library-name` to patch CVE-2025-XXXX
- Added rate limiting to public API endpoints

## [1.1.0] - 2024-12-01

### Added

- Feature description

### Fixed

- Bug fix description

---

## Guidelines

### When to Add Entries

- Add entries as you make changes, not just at release time
- Keep entries under `[Unreleased]` until a version is released
- Move unreleased entries to a new version section when releasing

### Categories

- **Added** - New features
- **Changed** - Changes to existing functionality
- **Chore** - Maintenance changes outside of functionality and bug fixes
- **Deprecated** - Features that will be removed in future versions
- **Documentation** - Documentation-focused updates
- **Fixed** - Bug fixes
- **Removed** - Features that have been removed
- **Security** - Vulnerability fixes and security improvements

### Breaking Changes

- Mark breaking changes with **BREAKING:** prefix
- Always add corresponding entry in MIGRATION.md with upgrade instructions
- Include in either "Changed" or "Removed" sections

### Writing Style

- Use present tense ("Add feature" not "Added feature")
- Be specific and concise
- Link to issues/PRs when relevant: `(#123)` or `([#123](link))`
- Focus on user impact, not implementation details

### Version Numbers

- Follow [Semantic Versioning](https://semver.org/):
  - MAJOR: Breaking changes
  - MINOR: New features (backward compatible)
  - PATCH: Bug fixes (backward compatible)

[Unreleased]: https://github.com/lif-initiative/lif-core/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/lif-initiative/lif-core/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/lif-initiative/lif-core/releases/tag/v1.1.0
