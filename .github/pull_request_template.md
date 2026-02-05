<!--
Thank you for your pull request. Please review the requirements below.

Bug fixes and new features should be reported on the issue tracker: https://github.com/lif-initiative/lif-core/issues

Contributing guide: https://github.com/lif-initiative/lif-core/blob/main/docs/CONTRIBUTING.md
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
<!-- Link to related issues using #issue_number -->

Closes # [[add Github issue number]]


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
- [ ] orchestrators/
- [ ] frontends/
- [ ] deployments/
- [ ] CloudFormation/SAM templates
- [ ] Database schema
- [ ] API endpoints
- [ ] Documentation
- [ ] Testing

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
