#!/usr/bin/env python3
"""Guards against documentation drifting away from the code it describes.

Every check here corresponds to a real drift found in the suite: a SKILL.md table that had
diverged from the Python it documented, and scripts that crashed instead of explaining themselves.
These are cheap to keep passing and expensive to notice by hand.

    python3 tests/test_docs_match_code.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"
os.environ.setdefault("ARGO_SETUP_NO_OPEN", "1")  # suites must not pop text editors
PORTFOLIO_DIR = PLUGINS / "argo-project-manager/skills/monitor-studies"


def load_portfolio():
    os.environ.setdefault("ARGO_PM_ROOT", str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm"))
    spec = importlib.util.spec_from_file_location("portfolio_doc", PORTFOLIO_DIR / "portfolio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPortfolioDocMatchesCode(unittest.TestCase):
    """The three drifts in finding #5, plus the build-step count drift found alongside them."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_portfolio()
        cls.doc = (PORTFOLIO_DIR / "SKILL.md").read_text()

    def test_every_tracker_in_the_code_is_documented(self):
        for env_var, *_ in self.mod.ADMIN_REDCAPS:
            self.assertIn(env_var, self.doc,
                          f"{env_var} is in ADMIN_REDCAPS but missing from SKILL.md")

    def test_the_doc_does_not_invent_trackers(self):
        known = {e for e, *_ in self.mod.ADMIN_REDCAPS}
        documented = set(re.findall(r"`([A-Z][A-Z_]{6,})`", self.doc))
        # Env vars that aren't tracker names are fine; only flag *_REQUEST/-ish tracker lookalikes.
        suspicious = {d for d in documented
                      if d.endswith(("_REQUEST", "_INITIATION")) and d not in known}
        self.assertFalse(suspicious, f"SKILL.md documents trackers the code doesn't have: {suspicious}")

    def test_done_marker_fields_match(self):
        for env_var, _label, _form, status_field, _done in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertTrue(row, f"no table row for {env_var}")
            self.assertIn(status_field, row[0],
                          f"SKILL.md's row for {env_var} doesn't name its real done-marker "
                          f"field {status_field!r}")

    def test_project_titles_match(self):
        for env_var, label, *_ in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertIn(label, row[0],
                          f"SKILL.md's row for {env_var} doesn't use the project title the code "
                          f"confirms against ({label!r})")

    def test_build_step_count_matches(self):
        n = len(self.mod.SIR_BUILD_STEPS)
        self.assertIn(f"/{n}", self.doc,
                      f"code counts {n} build steps; SKILL.md doesn't mention N/{n}")
        # The old, wrong count must not still be presented as current.
        self.assertNotIn("9 canonical build flags", self.doc)

    def test_snapshot_path_is_described_as_a_directory(self):
        # The code writes snapshot-<stamp>/summary.json, not a flat snapshot-<stamp>.json.
        self.assertIn("summary.json", self.doc,
                      "SKILL.md must document that a snapshot is a directory containing "
                      "summary.json, not a single flat file")


class TestNoBracketEnvAccess(unittest.TestCase):
    """Finding #1: os.environ['X'] raises a bare KeyError instead of explaining itself."""

    # os.environ["X"] = value is an assignment and can't raise KeyError — only reads are a problem.
    READ = re.compile(r"os\.environ\[[^\]]+\]\s*(?!=[^=])")
    ASSIGNMENT = re.compile(r"os\.environ\[[^\]]+\]\s*=[^=]")

    def test_no_script_uses_bracket_env_access(self):
        offenders = []
        for py in PLUGINS.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if self.READ.search(line) and not self.ASSIGNMENT.search(line):
                    offenders.append(f"{py.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "These read environment variables with [], which crashes with a bare KeyError "
            "instead of a message the user can act on. Use os.environ.get() or "
            f"RedcapClient.from_env(): {offenders}",
        )


class TestHeadlessSafe(unittest.TestCase):
    """Nothing may block on typed input where there's no keyboard.

    These scripts run in agent sessions, scheduled jobs and cloud runners as well as terminals.
    A bare input() there waits forever, which looks like a hang with no explanation.
    """

    def test_every_input_call_is_guarded_by_a_tty_check(self):
        unguarded = []
        for py in PLUGINS.rglob("*.py"):
            text = py.read_text()
            if not re.search(r"(?<![\w.])input\s*\(", text):
                continue
            if "isatty" not in text:
                unguarded.append(str(py.relative_to(REPO)))
        self.assertFalse(
            unguarded,
            "These prompt for typed input without checking a keyboard is attached, so they hang "
            f"forever in a headless run: {unguarded}",
        )

    def test_no_script_globs_plugin_roots_anymore(self):
        """Cross-plugin discovery is retired: every skill vendors its own scripts/ copy.

        Four separate locator bugs (directory-name globbing, lexical version sort, the
        /mnt/skills layout, the ~/mnt layout) came from scripts hunting for argo-core across
        environments. Imports are now same-folder. The shared client's find_argo_core keeps a
        roots list for standalone --check use; no other script may grow one back.
        """
        for py in PLUGINS.rglob("*.py"):
            if py.parent.name == "scripts":
                continue  # vendored copies of the client itself
            text = py.read_text()
            self.assertNotIn("/mnt/.remote-plugins", text,
                             f"{py.relative_to(REPO)} greps plugin roots — import from the "
                             "skill's vendored scripts/ folder instead")
            self.assertNotIn("hits[-1]", text,
                             f"{py.relative_to(REPO)} picks glob hits by name order")

    def test_no_relative_cross_plugin_paths_in_docs(self):
        """Plugins install into separate versioned dirs — '../other-plugin' never resolves."""
        offenders = []
        for md in PLUGINS.rglob("*.md"):
            for i, line in enumerate(md.read_text().splitlines(), 1):
                if "CLAUDE_PLUGIN_ROOT}/.." in line:
                    offenders.append(f"{md.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "A path like ${CLAUDE_PLUGIN_ROOT}/../argo-core resolves inside the current plugin's "
            f"own directory, not next to it, so it never exists: {offenders}",
        )


class TestVersionsAreInStep(unittest.TestCase):
    """All five plugins and the marketplace share one version — they release as one unit.

    argo-core ships the shared REDCap client that every role plugin vendors, so a mix of old and
    new plugins isn't a supported combination. Separate numbers would imply an independence that
    doesn't exist. Bumping everything each release also guarantees update-detection fires, which
    keys off the version field.
    """

    SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

    def versions(self):
        import json
        found = {}
        for manifest in sorted(REPO.glob("plugins/*/.claude-plugin/plugin.json")):
            found[manifest.parents[1].name] = json.loads(manifest.read_text()).get("version")
        found["(marketplace)"] = json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text())["metadata"].get("version")
        return found

    def test_every_version_matches(self):
        found = self.versions()
        distinct = set(found.values())
        self.assertEqual(
            len(distinct), 1,
            "Plugin versions have drifted apart. They ship as one unit — run "
            f"`python3 release.py --set <version>`. Found: {found}",
        )

    def test_marketplace_descriptions_mirror_plugin_json(self):
        """The marketplace's per-plugin descriptions are a copy of each plugin.json's
        description, synced by release.py — a hand-edited third copy would silently drift."""
        import json
        plugin_desc = {}
        for manifest in sorted(REPO.glob("plugins/*/.claude-plugin/plugin.json")):
            data = json.loads(manifest.read_text())
            plugin_desc[data.get("name", manifest.parents[1].name)] = data.get("description", "")
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        for entry in market.get("plugins", []):
            name = entry.get("name")
            if name in plugin_desc:
                self.assertEqual(
                    entry.get("description", ""), plugin_desc[name],
                    f"marketplace.json's description for {name} drifted from its plugin.json — "
                    "edit plugin.json and run release.py; never hand-edit marketplace.json")

    def test_runtime_stamp_matches(self):
        import re as _re
        trackers = (REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_trackers.py").read_text()
        stamp = _re.search(r'TOOLKIT_VERSION = "([^"]+)"', trackers).group(1)
        marketplace = self.versions()["(marketplace)"]
        self.assertEqual(stamp, marketplace,
                         "argo_trackers.TOOLKIT_VERSION drifted from the release version — "
                         "release.py stamps it; don't edit by hand")

    def test_versions_are_plain_semver(self):
        for name, version in self.versions().items():
            self.assertIsNotNone(version, f"{name} has no version")
            self.assertRegex(str(version), self.SEMVER,
                             f"{name}'s version {version!r} isn't a plain X.Y.Z number")

    def test_every_plugin_is_listed_in_the_marketplace(self):
        import json
        listed = {p["name"] for p in json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text())["plugins"]}
        on_disk = {p.parents[1].name for p in REPO.glob("plugins/*/.claude-plugin/plugin.json")}
        self.assertEqual(listed, on_disk,
                         "the marketplace listing and the plugins on disk disagree")


class TestEverythingShipsInsideASkill(unittest.TestCase):
    """No plugin asset may live outside a skills/<name>/ folder.

    Chat-surface distribution mounts each SKILL folder, not the plugin root. scripts/ and
    references/ used to sit at argo-core's root — so a chat session received bare SKILL.mds
    with no executable layer and no reference docs, while everything worked locally. Anything
    a skill needs must live inside the skill folder to travel.
    """

    ALLOWED_AT_ROOT = {"plugin.json"}  # .claude-plugin/plugin.json is plugin metadata

    def test_no_scripts_or_references_outside_skills(self):
        offenders = []
        for plugin in sorted(PLUGINS.iterdir()):
            if not plugin.is_dir():
                continue
            for path in plugin.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(plugin)
                if rel.parts[0] in ("skills", ".claude-plugin"):
                    continue
                offenders.append(str(path.relative_to(REPO)))
        self.assertFalse(
            offenders,
            "These files sit outside every skills/<name>/ folder, so chat-surface installs "
            f"will not include them: {offenders}",
        )


class TestStandaloneBundleInSync(unittest.TestCase):
    """Every skill's vendored scripts/ must be byte-identical to argo-core's source.

    Vendored copies are what killed cross-plugin discovery (each skill is self-contained), and
    many copies is normally the disease this repo kills on sight — so it's mechanised instead:
    release.py syncs every target on every release, and this test fails the moment any differs.
    """

    SOURCE = REPO / "plugins/argo-core/skills/redcap-api/scripts"

    def test_every_vendored_copy_matches_source_exactly(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("release_mod", REPO / "release.py")
        release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        src = {p.name: p.read_bytes() for p in self.SOURCE.glob("*.py")}
        self.assertTrue(src, "argo-core has no shared scripts?")
        for target in release.VENDOR_TARGETS:
            self.assertTrue(target.is_dir(), f"{target} missing — run release.py")
            dst = {p.name: p.read_bytes() for p in target.glob("*.py")}
            self.assertEqual(sorted(src), sorted(dst),
                             f"{target.relative_to(REPO)} has different files than argo-core — "
                             "run `python3 release.py --bump patch` to re-sync")
            for name in src:
                self.assertEqual(src[name], dst[name],
                                 f"{target.relative_to(REPO)}/{name} differs from argo-core — "
                                 "run `python3 release.py --bump patch` to re-sync")


class TestWikilinksResolve(unittest.TestCase):
    """Every [[name]] link must point at a real skill or reference doc.

    The start-here front door is almost entirely links — a dangling one sends a brand-new user
    to a skill that doesn't exist, which is the worst possible first experience. Applies
    repo-wide: a rename that orphans links elsewhere fails here too.
    """

    def test_every_wikilink_has_a_target(self):
        targets = set()
        for path in PLUGINS.rglob("*"):
            if path.is_dir() and path.parent.name == "skills":
                targets.add(path.name)
            if path.suffix == ".md" and path.parent.name == "references":
                targets.add(path.stem)
        dangling = []
        for md in PLUGINS.rglob("*.md"):
            for link in re.findall(r"\[\[([a-z0-9-]+)\]\]", md.read_text()):
                if link not in targets:
                    dangling.append(f"{md.relative_to(REPO)} -> [[{link}]]")
        self.assertFalse(dangling,
                         f"These links point at skills or reference docs that don't exist: {dangling}")


class TestSetupIsSafe(unittest.TestCase):
    """argo_setup.py creates folders — so it must never do that just for being run."""

    SETUP = PLUGINS / "argo-core/skills/redcap-api/scripts/argo_setup.py"

    def test_no_args_creates_nothing(self):
        import tempfile
        home = tempfile.mkdtemp()
        env = dict(os.environ, HOME=home)
        before = set(os.listdir(home))
        proc = subprocess.run([sys.executable, str(self.SETUP)],
                              capture_output=True, text=True, timeout=60, env=env)
        after = set(os.listdir(home))
        self.assertEqual(before, after,
                         "running argo_setup.py with no arguments created something")
        self.assertIn("Nothing has been created yet", proc.stdout)

    def test_setup_writes_a_private_env_file(self):
        import tempfile
        work = Path(tempfile.mkdtemp()) / "argo-work"
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, text=True, timeout=60)
        env_file = work / ".env"
        self.assertTrue(env_file.exists(), "no .env was created")
        self.assertEqual(oct(env_file.stat().st_mode & 0o777)[2:], "600",
                         "the settings file must be readable only by its owner")
        self.assertIn(".env", (work / ".gitignore").read_text(),
                      "the settings file must be git-ignored so keys can't be committed")
        for sub in ("project-manager", "qa-specialist", "database-manager", "data-analyst"):
            self.assertTrue((work / sub).is_dir(), f"workspace is missing {sub}/")

    def test_setup_never_overwrites_existing_keys(self):
        import tempfile
        work = Path(tempfile.mkdtemp()) / "argo-work"
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, timeout=60)
        env_file = work / ".env"
        env_file.write_text(env_file.read_text().replace("DATA_REQUEST=", "DATA_REQUEST=keepme"))
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, timeout=60)
        self.assertIn("DATA_REQUEST=keepme", env_file.read_text(),
                      "re-running setup destroyed a key the user had filled in")

    def test_returning_user_in_local_agent_mode_is_recognised(self):
        """Round 7's bug: a staged .env in a ~/mnt connected folder got the FIRST-TIME banner."""
        import tempfile
        home = Path(tempfile.mkdtemp())
        (home / "mnt" / "ARGO-work").mkdir(parents=True)
        (home / "mnt" / "ARGO-work" / ".env").write_text("REDCAP_URL=https://x.org/api/\n")
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME=str(home), ARGO_SETUP_NO_OPEN="1"),
                              cwd=str(home))
        self.assertIn("setup skipped", proc.stdout,
                      "a settings file in a local-agent-mode mount must be recognised")
        self.assertNotIn("FIRST-TIME", proc.stdout)

    def test_setup_has_no_private_search_list(self):
        """The search list lives once, in the client. Setup must delegate, never copy."""
        text = (PLUGINS / "argo-core/skills/redcap-api/scripts/argo_setup.py").read_text()
        self.assertIn("settings_candidates", text)
        self.assertNotIn('candidates.append(Path.home() / ".argo" / ".env")', text,
                         "argo_setup grew its own copy of the search paths again")

    def test_ensure_skips_when_settings_exist(self):
        import tempfile
        home = Path(tempfile.mkdtemp())
        (home / ".argo").mkdir()
        (home / ".argo" / ".env").write_text("REDCAP_URL=https://x.org/api/\n")
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME=str(home)), cwd=str(home))
        self.assertIn("setup skipped", proc.stdout)
        self.assertFalse((home / "argo-work").exists(),
                         "--ensure must not scaffold when settings already exist")

    def test_ensure_scaffolds_loudly_when_nothing_exists(self):
        import tempfile
        home = Path(tempfile.mkdtemp())
        env = dict(os.environ, HOME=str(home))
        env.pop("ARGO_ENV_FILE", None)
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=env, cwd=str(home))
        self.assertIn("FIRST-TIME SETUP", proc.stdout, "the scaffold must announce itself loudly")
        env_file = home / "argo-work" / ".env"
        self.assertTrue(env_file.exists(), "--ensure must create the settings file")
        self.assertEqual(oct(env_file.stat().st_mode & 0o777)[2:], "600")
        # And running it again must now skip.
        proc2 = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                               capture_output=True, text=True, timeout=60,
                               env=env, cwd=str(home))
        self.assertIn("setup skipped", proc2.stdout)

    def test_ensure_survives_an_unwritable_home(self):
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME="/nonexistent-home"), cwd="/tmp")
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_connected_workspace_detection(self):
        """Cowork rule: setup lands in the user's connected folder, and never guesses."""
        import importlib.util, tempfile
        spec = importlib.util.spec_from_file_location("argo_setup_ws", self.SETUP)
        s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
        base = Path(tempfile.mkdtemp())
        (base / "skills").mkdir()          # system mount — always ignored
        # ARGO-named folder wins outright.
        (base / "My ARGO Files").mkdir()
        self.assertEqual(s.find_connected_workspace(base), base / "My ARGO Files")
        # A lone generic folder gets an argo-work subfolder.
        import shutil; shutil.rmtree(base / "My ARGO Files")
        (base / "projects").mkdir()
        self.assertEqual(s.find_connected_workspace(base), base / "projects" / "argo-work")
        # Two unrelated folders: refuse to guess.
        (base / "photos").mkdir()
        self.assertIsNone(s.find_connected_workspace(base))

    def test_client_searches_the_scaffolded_locations(self):
        """The file --ensure creates must be findable by the client — this was a real gap."""
        client_text = (PLUGINS / "argo-core/skills/redcap-api/scripts/argo_redcap_client.py").read_text()
        self.assertIn('"argo-work" / ".env"', client_text,
                      "load_env_file must search argo-work/.env under home and connected folders")

    def test_template_never_asks_for_a_token_on_the_command_line(self):
        text = self.SETUP.read_text()
        self.assertNotIn('"--token"', text)
        self.assertNotIn("'--token'", text)
        self.assertIn("never pass one on the command line", text.lower().replace("**", ""))


class TestScriptsDegradeGracefully(unittest.TestCase):
    """Finding #3's smoke test: no script may traceback when run with no arguments."""

    SKIP = {"__init__.py"}

    def test_no_args_never_tracebacks(self):
        env = dict(os.environ)
        # Simulate a machine with nothing configured — the hardest case.
        for var in list(env):
            if var.endswith(("_TOKEN", "_REQUEST", "_INITIATION")) or var == "REDCAP_URL":
                env.pop(var)
        env["ARGO_PM_ROOT"] = str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm")

        failures = []
        for py in sorted(PLUGINS.rglob("*.py")):
            if py.name in self.SKIP:
                continue
            proc = subprocess.run(
                [sys.executable, str(py)],
                capture_output=True, text=True, timeout=60, env=env, cwd=str(REPO),
            )
            combined = proc.stdout + proc.stderr
            if "Traceback (most recent call last)" in combined:
                last = combined.strip().splitlines()[-1]
                failures.append(f"{py.relative_to(REPO)} → {last}")

        self.assertFalse(
            failures,
            "Run with no arguments and nothing configured, these crashed with a raw traceback "
            f"instead of explaining what was missing:\n  " + "\n  ".join(failures),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
