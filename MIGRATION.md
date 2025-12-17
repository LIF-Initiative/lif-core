<!-- markdownlint-disable MD024 MD036 -->

# Migration Guide

This document provides step-by-step instructions for upgrading between versions
of lif-core when breaking changes are introduced.

## Overview

Breaking changes are modifications that require action from users to maintain
compatibility. This includes:

- Database schema changes that require migrations
- API endpoint changes (removed, renamed, or modified parameters)
- Configuration format changes
- Dependency version requirements
- Changes to expected input/output formats

## How to Use This Guide

1. Identify your current version
2. Read all migration sections between your current version and target version
3. Follow the steps in order
4. Test thoroughly in a non-production environment first

---

## Upcoming Changes (Unreleased)

### Breaking Changes

*No breaking changes currently pending*

### Deprecation Notices

*No deprecations currently pending*

---

## Version History

### Version X.Y.Z (YYYY-MM-DD)

**Breaking Changes:**

- Description of breaking change
- **Action Required:** Step-by-step migration instructions
- **Impact:** Who is affected and how
- **Related:** Link to CHANGELOG.md entry, relevant issue, or documentation

**Example:**

### Version 1.2.0 (2025-01-15)

**Breaking Changes:**

#### Database: Added required `user_role` column to users table

- **Action Required:**
  1. Run migration script: `python scripts/migrate.py --version 1.2.0`
  2. Update any code that inserts users to include `user_role` parameter
- **Impact:** All deployments with existing user data
- **Related:** [CHANGELOG.md](CHANGELOG.md#120---2025-01-15), Issue #123

#### API: Removed deprecated `/v1/learner` endpoint

- **Action Required:**
  1. Update all client code to use `/v2/learner` instead
  2. Note: `/v2/learner` returns data in a different format (see API docs)
- **Impact:** Any external systems calling the v1 endpoint
- **Related:** [API Documentation](docs/api/learner-v2.md)

#### Configuration: Changed environment variable naming convention

- **Action Required:**
  1. Rename `LIF_DB_HOST` → `LIF_DATABASE_HOST`
  2. Rename `LIF_DB_PORT` → `LIF_DATABASE_PORT`
  3. Update all deployment configurations and docker-compose files
- **Impact:** All deployment configurations
- **Related:** [Configuration Guide](docs/configuration.md)

---

## Need Help?

If you encounter issues during migration:

1. Check the [CHANGELOG.md](CHANGELOG.md) for additional context
2. Review relevant documentation in the [/docs](docs/) directory
3. Search existing [GitHub Discussions](https://github.com/lif-initiative/lif-core/discussions)
4. Open a new discussion with the `migration` label if applicable
5. Search existing [GitHub Issues](https://github.com/lif-initiative/lif-core/issues)
6. Open a new issue with the `migration` label if needed
