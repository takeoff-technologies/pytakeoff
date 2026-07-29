# Releasing pytakeoff

From a version you trust, to PyPI + Read the Docs.

Maintainer docs — not shipped. The wheel packages only `src/pytakeoff` and the
sdist uses an allowlist in `pyproject.toml`, so this file and `release.py` are in
neither artifact.

---

## The whole release

```powershell
cd C:\Users\nicop\Documents\git\takeoff\pytakeoff
python release.py
```

It asks everything it needs.

**1 — what to release** (Enter takes patch):

```
  pytakeoff - current release  0.1.1   (last tag: v0.1.1)

  What do you want to release?

    1. patch  0.1.1 -> 0.1.2    bug fixes, no API change  <- default
    2. minor  0.1.1 -> 0.2.0    new features, backwards compatible
    3. major  0.1.1 -> 1.0.0    breaking changes

  choose [1/2/3, or patch/minor/major] (Enter = patch):
```

**2 — the description.** It shows the commits since the last tag; type your own
or press Enter to use them as-is:

```
  Commits since the last tag:

    - feat: add polar export
    - fix: reconnect after idle

  Describe this release. Enter on an empty line finishes.
  Leave blank to use the commit list above.
```

**3 — confirm**, with the full plan spelled out:

```
  About to release
    version    0.1.1  ->  0.1.2   (patch)
    tag        v0.1.2
    branch     main  ->  origin/main

    notes:
      Adds project close/delete.

    this will:
      1. build the docs (aborts the release if they do not compile)
      2. set __version__ = "0.1.2"
      3. commit and push to origin/main
      4. create and push tag v0.1.2
      5. publish the GitHub Release  ->  triggers the PyPI upload

    then, with no action from you:
      - PyPI       the publish workflow builds and uploads
      - Read the Docs  rebuilds latest, stable follows the new tag

  Release 0.1.2? [y/N]
```

Nothing happens until you answer `y`.

It refuses to start if you are not on `main`, the tree is dirty, `main` is out of
sync with origin, or the tag already exists — and it aborts before touching
anything if the docs do not compile.

### Skipping the questions

```powershell
python release.py --dry-run                      # show the plan, change nothing
python release.py minor                          # skip question 1
python release.py --set 1.0.0rc1                 # exact version
python release.py patch --notes "Fix reconnect" --yes   # no prompts at all
python release.py --skip-docs                    # do not build the docs first
```

## After it finishes

```powershell
gh run watch                                    # the publish workflow
```

- **PyPI** — <https://pypi.org/project/pytakeoff/> (a minute or two behind the workflow)
- **Docs** — <https://pytakeoff.readthedocs.io>

Nothing to do for the docs. Read the Docs rebuilds `latest` from the push to
`main`, and `stable` follows your newest semver tag on its own. Tags that are
PEP 440 and greater than the current stable are activated and built
automatically.

To make that unconditional rather than relying on the version comparison, set a
one-time rule: **RTD → Admin → Automation Rules → Add rule** → match *Tags*,
version type *Tag*, action **Activate version**. Applies to future tags only.

## Requirements

- **GitHub CLI** — `winget install --id GitHub.cli`, then `gh auth login`.
  Without it the script still pushes and tags, then prints a pre-filled release
  URL and the notes to paste; PyPI does not publish until that Release exists.
- Push rights on `main` and the repo's Releases.

PyPI needs no token — `publish.yml` uses Trusted Publishing (OIDC).

## If it goes wrong

PyPI versions cannot be replaced or deleted, only yanked. Fix forward with a new
patch version — never re-tag a published one.

```powershell
gh release delete v0.1.2 --yes
git push --delete origin v0.1.2
git tag -d v0.1.2
```

Yank on PyPI: **Manage project → Releases → Options → Yank**.

## Gotchas

- The workflow fires on **release published**, not on tag push. A tag alone
  publishes nothing.
- The sdist `include` in `pyproject.toml` is an allowlist — a new top-level
  directory will not ship until it is added there.
- `__version__` in `src/pytakeoff/__init__.py` is the only version in the repo;
  `pyproject.toml` reads it via `[tool.hatch.version]`.
