# Releasing Litmus

This is the maintainer runbook for cutting a new release of the
`litmus-data` package on PyPI. Publication is automated via the
`.github/workflows/release.yml` workflow and PyPI's **Trusted Publishing**
(OIDC) — there are no long-lived API tokens anywhere.

## One-time PyPI setup

Before the very first release, the `litmus-data` project needs to be
registered on PyPI as a trusted publisher pointing at this repository.

1. Sign in to <https://pypi.org/> with the maintainer account that owns
   (or will own) the `litmus-data` project name.
2. Follow the official guide: <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>.
3. When prompted, use exactly these values:
   - **PyPI Project Name:** `litmus-data`
   - **Owner:** `zinnoberHaus`
   - **Repository name:** `litmus`
   - **Workflow filename:** `release.yml`
   - **Environment name:** `pypi`
4. In GitHub, create a repository environment named `pypi`
   (Settings -> Environments -> New environment). Optionally protect it
   with required reviewers — the release job is gated on this environment,
   so a protection rule gives you a manual approval step before upload.

No API token or `PYPI_API_TOKEN` secret is needed — the workflow mints a
short-lived OIDC token at run time and PyPI trusts it because of the
registration above.

## Cutting a release

1. **Bump the version.** Update both files to the new version (e.g. `0.2.0`):
   - `pyproject.toml` — the `version` field under `[project]`.
   - `litmus/__init__.py` — the `__version__` string.
2. **Update `CHANGELOG.md`.**
   - Rename the top `[Unreleased]` section to `[<version>] - YYYY-MM-DD`.
   - Add a fresh empty `[Unreleased]` section above it.
   - Update the compare/tag links at the bottom of the file.
3. **Commit** the version bump and changelog together:
   ```bash
   git add pyproject.toml litmus/__init__.py CHANGELOG.md
   git commit -m "Release v<version>"
   git push origin main
   ```
4. **Tag and push.** The workflow triggers on tags matching `v*`.
   ```bash
   git tag v<version>
   git push origin v<version>
   ```
5. **Watch the release.** Open the Actions tab on GitHub and find the
   `Release` workflow run for the tag. The `build` job produces the
   sdist and wheel, and `publish-pypi` uploads them to PyPI via OIDC.
   If you added reviewers to the `pypi` environment, approve the
   deployment when prompted.
6. **Verify.** Once the run is green:
   ```bash
   pip install --upgrade litmus-data==<version>
   litmus --version
   ```

## Rollback

PyPI **does not** allow re-uploading the same version number, even after
a delete. If a release is broken:

1. **Yank** the broken version on PyPI (Manage project -> Releases ->
   Options -> Yank). Yanking hides the release from `pip install
   litmus-data` but preserves it for anyone who pinned it.
2. **Fix forward.** Bump the patch version, repeat the release steps
   above. Never try to reuse the broken version number.

## Notes

- `release.yml` deliberately does not run the test suite — that is the
  job of `ci.yml` on `main`. A tag should only ever be cut from a commit
  that has already passed CI.
- Action versions in `release.yml` are pinned (`actions/checkout@v4`,
  `actions/setup-python@v4`, `actions/upload-artifact@v4`,
  `actions/download-artifact@v4`, and
  `pypa/gh-action-pypi-publish@release/v1`, which is the official
  pinning convention recommended by PyPA).
