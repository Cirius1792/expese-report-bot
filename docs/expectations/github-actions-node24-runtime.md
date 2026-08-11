# GitHub Actions: Node 24 runtime for all actions

## Context

GitHub Actions emits deprecation warnings when workflows use actions that
target the Node.js 20 runtime ("Node.js 20 is deprecated... forced to run on
Node.js 24"). All actions in `.github/workflows/` must target Node 24.

## Expectations

### Happy path

- E1. Every `uses:` reference in `ci.yml` and `release.yml` points to a major
  version whose `runs.using` is `node24` (verified against upstream `action.yml`).
- E2. `ci.yml` runs green on `main` after the bump (unit-tests, bdd-tests).
- E3. The CI run log contains no "Node.js 20 is deprecated" warning for any
  action in the workflow.

### Edge cases

- E4. Docker + release actions (`login-action`, `metadata-action`,
  `build-push-action`, `action-gh-release`) only execute on a tag push; their
  Node 24 runtime is verified statically via `action.yml` at the pinned major
  (cannot be executed in-loop without cutting a release).

### Must NOT happen

- E5. No `@v4`/`@v5` (Node 20) action references remain in any workflow.
- E6. The workflows' inputs/behavior are unchanged (no breaking input changes
  in the chosen majors — verified against upstream release notes).
