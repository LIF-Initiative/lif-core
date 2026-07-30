<!--
Thank you for your pull request. Please review the requirements below.

Bug fixes and new features should be reported on the issue tracker: https://github.com/lif-initiative/lif-core/issues

Contributing guide: https://github.com/lif-initiative/lif-core/blob/main/CONTRIBUTING.md
Code of Conduct: https://github.com/lif-initiative/lif-core/blob/main/CODE_OF_CONDUCT.md
-->

##### Description of Change
<!-- Provide a clear and detailed description of the change below this comment.
Include:
- What problem does this solve?
- What is the solution?
- Are there any side effects or limitations?
- How should reviewers test this?
-->

##### Related Issues
<!-- Link the issue(s) this PR relates to. The number must come directly after `#` — no space, no
     brackets — or GitHub won't parse it (e.g. `Closes #123`, not `Closes # 123`).
       - `Closes #123` — a leaf issue this PR FULLY resolves. Merging auto-closes it AND moves its
                         card to Done on the project board. Use one per issue you actually finished.
       - `Refs #123`   — a related issue this PR does NOT fully resolve, OR an epic / umbrella issue
                         (which must stay open — its sub-issue rollup tracks progress, so never `Closes` it).
     Example for a PR implementing one item of an epic:  `Closes #123`  /  `Refs #120` (the epic).
     Delete these lines if the PR closes nothing. -->

Closes #


##### Type of Change
<!-- Check all that apply -->

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality
      to not work as expected)
- [ ] Documentation update
- [ ] Infrastructure/deployment change
- [ ] Performance improvement
- [ ] Code refactoring

##### Project Area(s) Affected
<!-- Check all project areas affected by this change -->

- [ ] bases/
- [ ] components/
- [ ] projects/
- [ ] orchestrators/
- [ ] frontends/
- [ ] deployments/
- [ ] cloudformation/ or sam/ templates
- [ ] reference_data/
- [ ] scripts/
- [ ] test/ or e2e/
- [ ] Database schema (migrations)
- [ ] API endpoints
- [ ] Documentation (docs/, READMEs, ARCHITECTURE.md, CLAUDE.md)

---

##### Checklist
<!-- REMOVE ITEMS that do not apply. For completed items, change [ ] to [x]. -->

- [ ] commit message follows commit guidelines (see commitlint.config.mjs)
- [ ] tests are included (unit and/or integration tests)
- [ ] documentation is changed or added (in /docs directory)
- [ ] code passes linting checks (`uv run ruff check`)
- [ ] code passes formatting checks (`uv run ruff format`)
- [ ] code passes type checking (`uv run ty check`)
- [ ] pre-commit hooks have been run successfully
- [ ] database schema changes: migration files created and CHANGELOG.md updated
- [ ] API changes: base (Python code) documentation in `docs/`
      and project README updated
- [ ] configuration changes: relevant folder README updated
- [ ] breaking changes: added to MIGRATION.md with upgrade instructions
      and CHANGELOG.md entry

##### Testing
<!-- Describe the testing you've done -->

- [ ] Manual testing performed
- [ ] Automated tests added/updated
- [ ] Integration testing completed

##### Additional Notes
<!-- Any additional information that reviewers should know -->
