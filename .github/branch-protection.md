# Branch protection requirements

This repository cannot enforce GitHub branch protection rules from within the codebase alone, but the required protection baseline for `main` is:

- require the `pytest` GitHub Actions workflow to pass before merge
- require branches to be up to date before merge
- block direct pushes to `main`
- require pull requests for all changes

If GitHub repository settings or rulesets are managed externally, mirror these requirements there so the workflow in `.github/workflows/pytest.yml` becomes a mandatory merge gate.
