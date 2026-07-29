#!/usr/bin/env python3
"""Cut a pytakeoff release: bump the version, push, tag, publish the GitHub Release.

Publishing the GitHub Release is what triggers the PyPI workflow; Read the Docs
picks the tag up on its own.

    python release.py                # interactive: asks what to bump and why
    python release.py minor          # skip the bump question
    python release.py --set 1.0.0rc1 # exact version
    python release.py --dry-run      # print every command, change nothing
    python release.py patch --notes "Fix reconnect" --yes    # non-interactive

Maintainer tool - not shipped (the sdist allowlist and wheel packages exclude it).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "src" / "pytakeoff" / "__init__.py"
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.M)
BRANCH = "main"
RULE = "-" * 66

DRY_RUN = False


class Abort(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(f"\n  {message}\n")


def run(*args: str, capture: bool = True, check: bool = True) -> str:
    """Run a command. Honours --dry-run for anything that mutates state."""
    reads_only = "--list" in args  # `git tag --list` must still run under --dry-run
    mutating = not reads_only and (
        args[:2] in {
            ("git", "commit"), ("git", "push"), ("git", "tag"), ("git", "add"),
        }
        or args[0] == "gh"
    )
    if DRY_RUN and mutating:
        print(f"    [dry-run] {' '.join(args)}")
        return ""
    result = subprocess.run(
        args, cwd=ROOT, capture_output=capture, text=True, check=False
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise Abort(f"command failed: {' '.join(args)}\n  {detail}")
    return (result.stdout or "").strip()


def read_version() -> str:
    match = VERSION_RE.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        raise Abort(f"no __version__ found in {VERSION_FILE}")
    return match.group(1)


def write_version(new: str) -> None:
    if DRY_RUN:
        print(f"    [dry-run] set __version__ = {new!r} in {VERSION_FILE.name}")
        return
    text = VERSION_FILE.read_text(encoding="utf-8")
    VERSION_FILE.write_text(
        VERSION_RE.sub(f'__version__ = "{new}"', text, count=1), encoding="utf-8"
    )


def bump(version: str, part: str) -> str:
    core = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not core:
        raise Abort(f"cannot bump non-semver version {version!r} - use --set")
    major, minor, patch = (int(g) for g in core.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def have_gh() -> bool:
    try:
        return subprocess.run(
            ["gh", "--version"], capture_output=True,
            shell=(sys.platform == "win32"),
        ).returncode == 0
    except OSError:
        return False


def repo_slug() -> str:
    """owner/name, parsed from the origin remote."""
    url = run("git", "remote", "get-url", "origin", check=False)
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return match.group(1) if match else "takeoff-technologies/pytakeoff"


def preflight() -> None:
    if run("git", "rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        raise Abort(f"not on {BRANCH}")
    if run("git", "status", "--porcelain"):
        raise Abort("working tree is dirty - commit or stash first")
    run("git", "fetch", "--quiet", "origin")
    local, remote = run("git", "rev-parse", "@"), run("git", "rev-parse", "@{u}")
    if local != remote:
        raise Abort(f"{BRANCH} is out of sync with origin - pull/push first")


def build_docs() -> None:
    """Build the Sphinx docs, failing the release if they do not compile.

    Read the Docs runs with fail_on_warning: false, so a broken reference would
    ship silently. Catch it here instead, before anything is pushed.
    """
    out = ROOT / "docs" / "_build" / "release-check"
    print("  building docs")
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "html", "-q", "-W", "--keep-going",
         str(ROOT / "docs"), str(out)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise Abort(
            "docs failed to build - fix before releasing:\n\n"
            + "\n".join(f"  {line}" for line in detail.splitlines()[-25:])
            + "\n\n  (skip with --skip-docs if this is a Sphinx setup problem)"
        )
    print(f"    ok - {out.relative_to(ROOT)}")


def changes_since_last_tag() -> tuple[str, str]:
    last = run("git", "describe", "--tags", "--abbrev=0", check=False)
    span = f"{last}..HEAD" if last else "HEAD"
    log = run("git", "log", span, "--no-merges", "--pretty=format:- %s")
    return last, log


# --------------------------------------------------------------------------- #
# interaction
# --------------------------------------------------------------------------- #

def ask_part(current: str) -> str:
    """Which part to bump. Enter accepts patch."""
    options = [
        ("patch", bump(current, "patch"), "bug fixes, no API change"),
        ("minor", bump(current, "minor"), "new features, backwards compatible"),
        ("major", bump(current, "major"), "breaking changes"),
    ]
    print("\n  What do you want to release?\n")
    for i, (name, version, blurb) in enumerate(options, 1):
        default = "  <- default" if name == "patch" else ""
        print(f"    {i}. {name:<6} {current} -> {version:<10} {blurb}{default}")

    while True:
        choice = input("\n  choose [1/2/3, or patch/minor/major] (Enter = patch): ")
        choice = choice.strip().lower()
        if not choice:
            return "patch"
        if choice in {"1", "2", "3"}:
            return options[int(choice) - 1][0]
        if choice in {"patch", "minor", "major"}:
            return choice
        print("    not a valid choice")


def ask_notes(log: str) -> str:
    """Free-text release description; blank keeps the commit list."""
    print("\n  Commits since the last tag:\n")
    print("\n".join(f"    {line}" for line in (log or "    (none)").splitlines()))
    print(
        "\n  Describe this release. Enter on an empty line finishes."
        "\n  Leave blank to use the commit list above.\n"
    )
    lines: list[str] = []
    while True:
        try:
            line = input("    ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip() or log or ""


def show_plan(current: str, new: str, tag: str, part: str, notes: str,
              gh_ready: bool) -> None:
    print(f"\n{RULE}\n  About to release\n{RULE}")
    print(f"    version    {current}  ->  {new}   ({part})")
    print(f"    tag        {tag}")
    print(f"    branch     {BRANCH}  ->  origin/{BRANCH}")
    print("\n    notes:")
    print("\n".join(f"      {line}" for line in (notes or "(none)").splitlines()))
    print("\n    this will:")
    print("      1. build the docs (aborts the release if they do not compile)")
    print(f"      2. set __version__ = \"{new}\"")
    print(f"      3. commit and push to origin/{BRANCH}")
    print(f"      4. create and push tag {tag}")
    if gh_ready:
        print("      5. publish the GitHub Release  ->  triggers the PyPI upload")
    else:
        print("      5. SKIP the GitHub Release (gh not installed)")
        print("         nothing reaches PyPI until you publish it in the browser")
    print("\n    then, with no action from you:")
    print("      - PyPI       the publish workflow builds and uploads")
    print("      - Read the Docs  rebuilds latest, stable follows the new tag")
    print(RULE)


def confirm(prompt: str) -> bool:
    return input(f"\n  {prompt} [y/N] ").strip().lower() in {"y", "yes"}


# --------------------------------------------------------------------------- #

def main() -> int:
    global DRY_RUN

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "part", nargs="?", default=None, choices=["patch", "minor", "major"],
        help="which part to bump; omit to be asked (default: patch)",
    )
    parser.add_argument("--set", dest="exact", help="use this exact version instead")
    parser.add_argument("--notes", help="release description; skips the prompt")
    parser.add_argument("--dry-run", action="store_true", help="change nothing")
    parser.add_argument("--yes", action="store_true", help="skip all prompts")
    parser.add_argument(
        "--skip-docs", action="store_true", help="do not build the docs first"
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    preflight()

    current = read_version()
    last_tag, log = changes_since_last_tag()

    print(f"\n{RULE}")
    print(f"  pytakeoff - current release  {current}"
          f"   (last tag: {last_tag or 'none'})")
    print(RULE)

    if args.exact:
        part, new = "--set", args.exact
    else:
        part = args.part or ("patch" if args.yes else ask_part(current))
        new = bump(current, part)

    if new == current:
        raise Abort(f"version is already {new}")
    tag = f"v{new}"
    if run("git", "tag", "--list", tag):
        raise Abort(f"tag {tag} already exists")

    if args.notes is not None:
        notes = args.notes
    elif args.yes:
        notes = log
    else:
        notes = ask_notes(log)
    notes = notes or f"pytakeoff {new}"

    gh_ready = have_gh()
    show_plan(current, new, tag, part, notes, gh_ready)

    if DRY_RUN:
        print("\n  -- dry run: nothing below actually happens --")
    elif not args.yes and not confirm(f"Release {new}?"):
        print("  aborted - nothing changed\n")
        return 1

    # Before touching anything: the docs must compile.
    if not args.skip_docs:
        build_docs()

    print("\n  bumping version")
    write_version(new)

    print("  pushing to GitHub")
    run("git", "add", str(VERSION_FILE.relative_to(ROOT)))
    run("git", "commit", "-m", f"Release {new}")
    run("git", "push", "origin", BRANCH)

    print("  tagging")
    run("git", "tag", "-a", tag, "-m", f"pytakeoff {new}")
    run("git", "push", "origin", tag)

    if gh_ready:
        print("  publishing the GitHub Release (this triggers PyPI)")
        run("gh", "release", "create", tag,
            "--title", f"pytakeoff {new}", "--notes", notes)

    if DRY_RUN:
        print("\n  dry run complete - nothing was changed\n")
        return 0

    if gh_ready:
        print(
            f"\n  Released {new}.\n"
            f"    workflow   gh run watch\n"
            f"    pypi       https://pypi.org/project/pytakeoff/{new}/\n"
            f"    docs       https://pytakeoff.readthedocs.io  (stable follows {tag})\n"
        )
        return 0

    from urllib.parse import quote

    print(
        f"\n  Pushed and tagged {tag}, but NOT released:\n"
        f"  the GitHub CLI (gh) is not installed, and publishing the Release is\n"
        f"  what triggers the PyPI upload.\n\n"
        f"  Finish it in the browser:\n"
        f"    https://github.com/{repo_slug()}/releases/new"
        f"?tag={quote(tag)}&title={quote(f'pytakeoff {new}')}\n\n"
        f"  Paste these notes:\n\n{notes}\n\n"
        f"  Or install gh once (https://cli.github.com) and future releases are\n"
        f"  fully automatic:  winget install --id GitHub.cli\n"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\n  interrupted - nothing changed\n")
