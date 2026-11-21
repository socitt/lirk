# Releasing lirk

Releases publish to [PyPI](https://pypi.org/project/lirk/) automatically
when a GitHub release is published, via `.github/workflows/release.yml`.
There is no API token: PyPI's *trusted publishing* is configured to
accept uploads from that one workflow in `socitt/lirk` and nothing else.

## One-time setup (done once, ever)

On PyPI, signed in: **Account settings → Publishing → Add a new pending
publisher → GitHub**, with:

| Field | Value |
|---|---|
| PyPI Project Name | `lirk` |
| Owner | `socitt` |
| Repository name | `lirk` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

"Pending" because the project doesn't exist on PyPI until the first
upload creates it; after that it is an ordinary trusted publisher.

## Each release

1. Bump `version` in `pyproject.toml` in a PR, and merge it once CI is
   green. PyPI never accepts the same version twice, so every release
   needs a new number.
2. On GitHub: **Releases → Draft a new release → Choose a tag →** type
   `v<version>` (e.g. `v1.0.2`) **→ Create new tag on publish**, target
   `main`. Publish.
3. The **Release** workflow then checks the tag matches the version,
   runs both test paths, builds, and uploads. Watch it under **Actions**.

If the tag and the version disagree, the workflow stops before
building, so a wrong number can never reach PyPI.
