<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Pull request template with comprehensive contribution guidelines
- MIGRATION.md for tracking breaking changes and upgrade paths
- CHANGELOG.md for tracking all notable changes

### Changed

### Deprecated

### Removed

### Fixed

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
