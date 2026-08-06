#!/usr/bin/env python3
"""Cut a pytakeoff release: bump the version, push, tag, publish the GitHub Release.

Publishing the GitHub Release is what triggers the PyPI workflow; Read the Docs
picks the tag up on its own.

    python release.py                # interactive: asks what to bump and why
    python release.py minor          # skip the bump question
    python release.py --set 1.0.0rc1 # exact version
    python release.py --republish    # current version is tagged but never reached PyPI
    python release.py --dry-run      # print every command, change nothing
    python release.py patch --notes "Fix reconnect" --yes    # non-interactive

Publishing the Release is only the trigger - the release is not done until the
workflow has run and PyPI has the version. Both are waited for and reported, and
a release event GitHub accepted but never dispatched (it happens) is re-fired
automatically. --republish recovers such a release without burning a version.

Maintainer tool - not shipped (the sdist allowlist and wheel packages exclude it).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "src" / "pytakeoff" / "__init__.py"
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.M)
BRANCH = "main"
RULE = "-" * 66

PACKAGE = "pytakeoff"
WORKFLOW = "publish.yml"
#: How long to wait for GitHub to turn the release event into a workflow run.
#: Generous on purpose: v0.2.0's dispatch took half an hour, and a release that
#: is merely queued must never be mistaken for one that was dropped.
RUN_WAIT_SECONDS = 1800
#: How long to wait for the published version to appear on PyPI afterwards.
PYPI_WAIT_SECONDS = 300

DRY_RUN = False


class Abort(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(f"\n  {message}\n")


def run(*args: str, capture: bool = True, check: bool = True,
        read_only: bool = False) -> str:
    """Run a command. Honours --dry-run for anything that mutates state.

    ``read_only=True`` marks a command as safe to run under --dry-run — needed
    for the gh queries (``gh run list``, ``gh release view``) that only look.
    """
    reads_only = read_only or "--list" in args  # `git tag --list` must still run
    is_gh = Path(args[0]).stem.lower() == "gh"  # args[0] may be a full path to gh.exe
    mutating = not reads_only and (
        args[:2] in {
            ("git", "commit"), ("git", "push"), ("git", "tag"), ("git", "add"),
        }
        or is_gh
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


def gh_path() -> str | None:
    """Locate the GitHub CLI.

    shutil.which, not `subprocess.run(["gh", ...], shell=True)` - on Windows that
    combination is unreliable and reported gh missing on machines that had it.
    Falls back to the default install locations for a shell whose PATH predates
    the install.
    """
    found = shutil.which("gh")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
    ):
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def repo_slug() -> str:
    """owner/name, parsed from the origin remote."""
    url = run("git", "remote", "get-url", "origin", check=False)
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return match.group(1) if match else "takeoff-technologies/pytakeoff"


def preflight() -> None:
    if run("git", "rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        raise Abort(f"not on {BRANCH}")
    # Tracked changes only: the release commits nothing but the version file, so
    # untracked local files (CLAUDE.md, scratch scripts) must not block a release.
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        raise Abort("you have uncommitted changes - commit or stash first")
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


# --------------------------------------------------------------------------- #
# publishing: the Release is only the trigger, so verify it actually fired
# --------------------------------------------------------------------------- #

def on_pypi(version: str) -> bool:
    """Is this version live on PyPI?"""
    try:
        with urlopen(f"https://pypi.org/pypi/{PACKAGE}/json", timeout=15) as response:
            data = json.load(response)
    except (URLError, OSError, ValueError):
        return False
    return version in (data.get("releases") or {})


def publish_runs(gh: str, tag: str) -> list[dict]:
    """Runs of the publish workflow for this tag, newest first."""
    out = run(gh, "run", "list", "--workflow", WORKFLOW, "--limit", "20",
              "--json", "databaseId,status,conclusion,headBranch,createdAt",
              read_only=True, check=False)
    try:
        runs = json.loads(out) if out else []
    except ValueError:
        return []
    return [r for r in runs if r.get("headBranch") == tag]


def wait_for_publish_run(gh: str, tag: str,
                         seconds: int = RUN_WAIT_SECONDS) -> dict | None:
    """Poll until GitHub starts a publish run for ``tag``.

    Dispatch is not immediate and the lag is not bounded — v0.2.0 sat for half
    an hour between the Release and the run. Waiting minutes, not seconds, is
    what keeps a slow release from looking like a failed one.
    """
    if DRY_RUN:
        print("    [dry-run] would wait for the publish workflow to start")
        return {"databaseId": 0}
    minutes = seconds // 60
    print(f"  waiting for the publish workflow (up to {minutes} min; GitHub can "
          f"take a while)\n    ", end="", flush=True)
    deadline = time.monotonic() + seconds
    while True:
        runs = publish_runs(gh, tag)
        if runs:
            print(f"\n    started: run {runs[0]['databaseId']}")
            return runs[0]
        if time.monotonic() >= deadline:
            print()
            return None
        print(".", end="", flush=True)
        time.sleep(10)


def refire_release(gh: str, tag: str) -> None:
    """Re-publish the Release so GitHub emits ``release: published`` again.

    Only for a release that never produced a run at all — re-firing one that is
    merely queued would run the workflow twice and the second upload would be
    rejected by PyPI as a duplicate.
    """
    print(f"  re-firing the release event for {tag}")
    run(gh, "release", "edit", tag, "--draft")
    time.sleep(3)
    run(gh, "release", "edit", tag, "--draft=false")


def wait_for_pypi(version: str, seconds: int = PYPI_WAIT_SECONDS) -> bool:
    if DRY_RUN:
        print(f"    [dry-run] would wait for {PACKAGE} {version} on PyPI")
        return True
    print(f"  waiting for {PACKAGE} {version} on PyPI (up to {seconds}s)",
          end="", flush=True)
    deadline = time.monotonic() + seconds
    while True:
        if on_pypi(version):
            print("\n    live")
            return True
        if time.monotonic() >= deadline:
            print()
            return False
        print(".", end="", flush=True)
        time.sleep(10)


def verify_published(gh: str, version: str, tag: str, *, wait: bool = True) -> int:
    """Follow the Release through to PyPI. Returns an exit code.

    Called with the Release already published. The Release is only the trigger:
    without this, a version that never gets built looks exactly like one that
    did, because everything the script itself does has already succeeded.
    """
    if not wait:
        print(f"\n  Published the Release for {tag}; not waiting for the workflow.\n"
              f"    check later:  gh run list --workflow {WORKFLOW}\n")
        return 0

    try:
        started = wait_for_publish_run(gh, tag)
    except KeyboardInterrupt:
        # Everything up to here already happened — only the watching stops.
        print(f"\n\n  Stopped watching. {tag} is released; the upload continues\n"
              f"  without you.  gh run list --workflow {WORKFLOW}\n")
        return 0

    if started is None:
        print(
            f"\n  GitHub has not started the workflow for {tag} yet. That is usually\n"
            f"  latency rather than failure — dispatch has taken half an hour before —\n"
            f"  so the upload will most likely still happen on its own.\n\n"
            f"    watch it:   gh run list --workflow {WORKFLOW}\n"
            f"    check pypi: https://pypi.org/project/{PACKAGE}/{version}/\n\n"
            f"  If no run has appeared much later, the event really was dropped:\n"
            f"      python release.py --republish\n"
        )
        return 0  # tagged, pushed and released — not a failed release

    print("  workflow running:")
    run(gh, "run", "watch", str(started["databaseId"]), "--exit-status",
        capture=False, check=False)

    if not wait_for_pypi(version):
        print(
            f"\n  The workflow ran but {PACKAGE} {version} is not on PyPI yet.\n"
            f"    gh run view {started['databaseId']} --log-failed\n"
        )
        return 1
    return 0


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
              gh: str | None) -> None:
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
    if gh:
        print("      5. publish the GitHub Release  ->  triggers the PyPI upload")
        print("      6. follow the workflow, then confirm the version on PyPI")
        print("         (dispatch can lag; it waits up to "
              f"{RUN_WAIT_SECONDS // 60} min. Ctrl-C is safe -")
        print("         the release is already out, only the watching stops)")
    else:
        print("      5. SKIP the GitHub Release - the GitHub CLI was not found")
        print("         nothing reaches PyPI until you publish it in the browser")
        print("         (install: winget install --id GitHub.cli, then reopen the shell)")
    print("\n    then, with no action from you:")
    print("      - Read the Docs  rebuilds latest, stable follows the new tag")
    print(RULE)


def confirm(prompt: str) -> bool:
    return input(f"\n  {prompt} [y/N] ").strip().lower() in {"y", "yes"}


def republish(gh: str | None, notes: str, *, yes: bool, wait: bool) -> int:
    """Finish a release that was tagged and published but never reached PyPI.

    Bumps nothing and tags nothing: the current version is already committed and
    tagged, so this only re-sends the trigger the workflow listens for.
    """
    version = read_version()
    tag = f"v{version}"

    if not gh:
        raise Abort("republishing needs the GitHub CLI (gh) — see https://cli.github.com")
    if not run("git", "tag", "--list", tag):
        raise Abort(f"no tag {tag} — nothing to republish; cut a release instead")
    if on_pypi(version):
        raise Abort(f"{PACKAGE} {version} is already on PyPI — nothing to do")

    released = run(gh, "release", "view", tag, "--json", "tagName",
                   read_only=True, check=False)

    # A run that already exists means the event was delivered. Re-firing then
    # would only duplicate the upload, so watch what is there instead.
    existing = publish_runs(gh, tag)
    pending = [r for r in existing if r.get("status") != "completed"]
    if pending:
        print(f"\n  A publish run for {tag} is already {pending[0]['status']} "
              f"(run {pending[0]['databaseId']}) — watching it instead.")
        run(gh, "run", "watch", str(pending[0]["databaseId"]), "--exit-status",
            capture=False, check=False)
        return 0 if wait_for_pypi(version) else 1
    if existing:
        raise Abort(
            f"a publish run for {tag} already completed "
            f"({existing[0]['conclusion']}) but {version} is not on PyPI.\n"
            f"  Re-firing would not help — read the log first:\n"
            f"      gh run view {existing[0]['databaseId']} --log-failed"
        )

    print(f"\n{RULE}\n  Republish {PACKAGE} {version}\n{RULE}")
    print(f"    tag        {tag}  (already committed and pushed)")
    print(f"    release    {'exists — will be re-fired' if released else 'missing — will be created'}")
    print("    version    unchanged — nothing is bumped, committed or tagged")
    print(f"    runs       none for {tag} — the event was never delivered")
    print(f"    then       wait for the workflow, then for {version} on PyPI")
    print(RULE)

    if DRY_RUN:
        print("\n  -- dry run: nothing below actually happens --")
    elif not yes and not confirm(f"Republish {version}?"):
        print("  aborted - nothing changed\n")
        return 1

    # The tag may exist only locally if an earlier run died between the two.
    run("git", "push", "origin", tag, check=False)

    if released:
        refire_release(gh, tag)
    else:
        run(gh, "release", "create", tag,
            "--title", f"{PACKAGE} {version}", "--notes", notes or f"{PACKAGE} {version}")

    code = verify_published(gh, version, tag, wait=wait)
    if code:
        return code
    if not (DRY_RUN or on_pypi(version)):
        return 0  # verify_published already explained where it stands

    print(f"\n  Republished {version}.\n"
          f"    pypi       https://pypi.org/project/{PACKAGE}/{version}/\n")
    return 0


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
    parser.add_argument(
        "--republish", action="store_true",
        help="re-trigger the PyPI publish for the current version (no bump, no new tag)",
    )
    parser.add_argument(
        "--no-wait", action="store_true",
        help="do not wait for the workflow and PyPI after publishing",
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    preflight()

    if args.republish:
        return republish(gh_path(), args.notes or "",
                         yes=args.yes, wait=not args.no_wait)

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

    gh = gh_path()
    show_plan(current, new, tag, part, notes, gh)

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

    if gh:
        print("  publishing the GitHub Release (this triggers PyPI)")
        run(gh, "release", "create", tag,
            "--title", f"pytakeoff {new}", "--notes", notes)

    if DRY_RUN:
        print("\n  dry run complete - nothing was changed\n")
        return 0

    if gh:
        # The Release is only the trigger — a release GitHub accepts but never
        # dispatches leaves the version tagged and absent from PyPI, silently.
        code = verify_published(gh, new, tag, wait=not args.no_wait)
        if code:
            return code
        print(
            f"\n  Released {new}.\n"
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
