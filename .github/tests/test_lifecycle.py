import contextlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".github/scripts"))
import release
import source_version as source


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(path, *args):
    location = ["--git-dir", str(path)] if path.name.endswith(".git") else ["-C", str(path)]
    return subprocess.run(
        ["git", *location, *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def copy_source(destination):
    for path in source.SOURCE_PATHS:
        (destination / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination / path)


def entry(tag="v9.8.7", draft=False):
    return {"id": 42, "tag_name": tag, "draft": draft, "prerelease": False}


class AvailabilityTests(unittest.TestCase):
    def test_page_two_draft_published_and_successful_absence(self):
        for draft in (True, False):
            with self.subTest(draft=draft), patch.object(release, "remote_ref", return_value=None), \
                    patch.object(release, "api", side_effect=[
                        [entry()] * 100, [entry("v1.2.3", draft)]
                    ]) as api:
                with self.assertRaisesRegex(ValueError, "draft or published"):
                    release.available("owner/repo", "v1.2.3")
                self.assertEqual(api.call_args_list[1].args[0],
                                 "repos/owner/repo/releases?per_page=100&page=2")
        with patch.object(release, "remote_ref", return_value=None), \
                patch.object(release, "api", side_effect=[[entry()] * 100, []]) as api:
            release.available("owner/repo", "v1.2.3")
            self.assertEqual(api.call_count, 2)

    def test_errors_and_malformed_every_page_fail_closed(self):
        errors = [
            *(subprocess.CalledProcessError(1, ["gh", "api", str(status)])
              for status in (401, 403, 404, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
        ]
        bad_pages = [{}, None, "[]", [None], [{}], [dict(entry(), id=True)],
                     [dict(entry(), id=0)], [dict(entry(), tag_name=None)],
                     [dict(entry(), tag_name="")], [dict(entry(), draft="false")],
                     [dict(entry(), prerelease=None)], [entry()] * 101]
        for page in (1, 2):
            for response in errors + bad_pages:
                with self.subTest(page=page, response=response), \
                        patch.object(release, "remote_ref", return_value=None), \
                        patch.object(release, "api", side_effect=(
                            [[entry()] * 100] * (page - 1) + [response])):
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        release.available("owner/repo", "v1.2.3")

    def test_remote_errors_and_malformed_fail_closed(self):
        with patch.object(release, "remote_ref", return_value="a" * 40), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.available("o/r", "v1.2.3")
            api.assert_not_called()
        for output in ("invalid\trefs/tags/v1.2.3", "a" * 40,
                       "a" * 40 + "\trefs/tags/wrong",
                       ("a" * 40 + "\trefs/tags/v1.2.3\n") * 2):
            with self.subTest(output=output), patch.object(release, "run", return_value=output):
                with self.assertRaises(ValueError):
                    release.remote_ref("refs/tags/v1.2.3")
        with patch.object(release, "run", side_effect=OSError("network")):
            with self.assertRaises(OSError):
                release.available("o/r", "v1.2.3")

    def test_transport_explicit_methods_and_no_retry(self):
        with patch.object(release, "run", return_value="[]") as run:
            release.api("repos/o/r/releases?per_page=100&page=2")
            self.assertEqual(run.call_args.args, ("gh", "api", "--method", "GET",
                             "repos/o/r/releases?per_page=100&page=2"))
        with patch.object(release, "run", return_value='{"id": 7}') as run:
            payload = {"tag_name": "v1.2.3", "draft": False}
            release.api("repos/o/r/releases", payload)
            self.assertIn("POST", run.call_args.args)
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), payload)
        with patch.object(release, "run", side_effect=subprocess.CalledProcessError(1, "gh")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                release.api("repos/o/r/releases")
            self.assertEqual(run.call_count, 1)
        with patch.object(release, "run", return_value='{"id": 8}') as run:
            asset = Path("Common String Algorithm-1.2.3.zip")
            release.api("https://uploads.github.com/repos/o/r/releases/123/assets", asset=asset)
            self.assertEqual(run.call_args.args, (
                "gh", "api", "--method", "POST",
                "https://uploads.github.com/repos/o/r/releases/123/assets",
                "--header", "Content-Type: application/octet-stream", "--input", str(asset)))


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".lifecycle-git-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.local = self.root / "local"
        self.peer = self.root / "peer"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "init", "-b", "selected", str(self.local))
        for key, value in (("user.name", "Lifecycle Test"), ("user.email", "test@example.invalid"),
                           ("push.followTags", "true")):
            git(self.local, "config", key, value)
        git(self.local, "commit", "--allow-empty", "-m", "ancestor")
        self.ancestor = git(self.local, "rev-parse", "HEAD")
        copy_source(self.local)
        shutil.copytree(ROOT / ".github/scripts", self.local / ".github/scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "fixture")
        git(self.local, "remote", "add", "origin", str(self.remote))
        git(self.local, "push", "origin", "HEAD:refs/heads/selected")
        self.sha = git(self.local, "rev-parse", "HEAD")
        self.version = source.read(self.local)
        self.tag = f"v{self.version}"
        self.published = None
        self.uploaded = []
        git(self.root, "clone", "--branch", "selected", str(self.remote), str(self.peer))
        git(self.peer, "config", "user.name", "Peer")
        git(self.peer, "config", "user.email", "peer@example.invalid")
        self.enter = cwd(self.local)
        self.enter.__enter__()
        self.addCleanup(self.enter.__exit__, None, None, None)

    def advance_peer(self):
        (self.peer / "peer.txt").write_text("concurrent branch update")
        git(self.peer, "add", ".")
        git(self.peer, "commit", "-m", "peer")
        git(self.peer, "push", "origin", "HEAD:refs/heads/selected")

    def test_bump_only_explicit_branch_source_no_follow_tags(self):
        git(self.local, "tag", "-a", "unrelated-annotated", "-m", "must not follow")
        git(self.remote, "update-ref", "refs/heads/other", self.sha)
        release.bump_branch(self.sha, "selected", "patch")
        self.assertNotEqual(git(self.remote, "rev-parse", "refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/other"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertEqual(git(self.local, "rev-parse", "HEAD^"), self.sha)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(set(git(self.local, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "HEAD").splitlines()),
                         {str(source.PROJECT), str(source.LOCALIZED)})
        self.assertEqual((self.local / source.PLIST).read_bytes(), (ROOT / source.PLIST).read_bytes())
        self.assertEqual(
            [m[3] for m in source.SETTING.finditer(source.text(self.local / source.PROJECT))
             if m[2] == "CURRENT_PROJECT_VERSION"],
            [m[3] for m in source.SETTING.finditer(source.text(ROOT / source.PROJECT))
             if m[2] == "CURRENT_PROJECT_VERSION"])

    def test_cli_bytecode_keeps_clean_checkout(self):
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        subprocess.run(
            [sys.executable, ".github/scripts/release.py", "bump", "--sha", self.sha,
             "--branch", "selected", "--mode", "patch"],
            env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_preparation_races(self):
        self.advance_peer()
        with self.assertRaisesRegex(ValueError, "moved"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)

    def test_race_during_preparation(self):
        real_bump = release.bump

        def concurrent_bump(mode):
            result = real_bump(mode)
            self.advance_peer()
            return result

        with patch.object(release, "bump", side_effect=concurrent_bump):
            with self.assertRaisesRegex(ValueError, "moved during"):
                release.bump_branch(self.sha, "selected", "minor")
        self.assertEqual(release.remote_ref("refs/heads/selected"),
                         git(self.peer, "rev-parse", "HEAD"))

    def advertised_race(self, kind):
        real_run = release.run
        expected = None
        pushes = 0

        def concurrent_push(*args, **kwargs):
            nonlocal expected, pushes
            # After the final ls-remote, before receive-pack advertisement.
            if "push" in args:
                pushes += 1
                if kind == "rewind":
                    expected = self.ancestor
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                elif kind == "delete":
                    git(self.remote, "update-ref", "-d", "refs/heads/selected")
                elif kind == "advance":
                    self.advance_peer()
                    expected = git(self.peer, "rev-parse", "HEAD")
                elif kind == "same-result":
                    expected = git(self.local, "rev-parse", "HEAD")
                    git(self.remote, "fetch", "--no-tags", str(self.local), "HEAD")
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                else:
                    self.fail(kind)
            return real_run(*args, **kwargs)

        with patch.object(release, "run", side_effect=concurrent_push):
            with self.assertRaises(subprocess.CalledProcessError):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(pushes, 1)
        self.assertEqual(release.remote_ref("refs/heads/selected"), expected)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_advertised_rewind(self):
        self.advertised_race("rewind")

    def test_advertised_deletion(self):
        self.advertised_race("delete")

    def test_advertised_advance(self):
        self.advertised_race("advance")

    def test_advertised_same_result(self):
        self.advertised_race("same-result")

    def test_missing_nonexecutable_guard_and_dirty_source(self):
        guard = self.local / ".github/scripts/bump-hooks/pre-push"
        guard.chmod(0o644)
        for absent in (False, True):
            if absent:
                guard.unlink()
            with self.subTest(absent=absent), \
                    patch.object(release, "__file__", str(self.local / ".github/scripts/release.py")):
                with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                    release.bump_branch(self.sha, "selected", "patch")
            self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            release.bump_branch(self.sha, "selected", "patch")

    def guard_loss_after_final_read(self, missing):
        runtime = self.root / "runtime"
        shutil.copytree(self.local / ".github/scripts", runtime)
        guard = runtime / "bump-hooks/pre-push"
        real_remote_ref = release.remote_ref
        reads = 0

        def lose_guard(ref):
            nonlocal reads
            result = real_remote_ref(ref)
            reads += 1
            if reads == 2:
                if missing:
                    guard.unlink()
                else:
                    guard.chmod(0o644)
            return result

        with patch.object(release, "__file__", str(runtime / "release.py")), \
                patch.object(release, "remote_ref", side_effect=lose_guard), \
                patch.object(release.os, "access", wraps=os.access) as access:
            with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                release.bump_branch(self.sha, "selected", "patch")
            self.assertEqual(access.call_count, 1 if missing else 2)
        self.assertEqual(reads, 2)
        self.assertEqual(real_remote_ref("refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_nonexecutable_guard_rechecked_after_final_remote_read(self):
        self.guard_loss_after_final_read(False)

    def test_missing_guard_rechecked_after_final_remote_read(self):
        self.guard_loss_after_final_read(True)

    def test_immutable_invalid_sha_and_branch(self):
        for sha in ("selected", "a" * 40, "a" * 39, "a" * 41):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                release.selected_sha(sha)
        release.selected_sha(self.sha)
        with self.assertRaises(subprocess.CalledProcessError):
            release.bump_branch(self.sha, "invalid..branch", "patch")

    def test_preflight_clean_and_final_source_drift(self):
        (self.local / source.PLIST).write_text("dirty source")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "clean source"):
                release.preflight(self.sha)
            api.assert_not_called()
        copy_source(self.local)
        paths = self.assets()
        source.bump("patch")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "differs from the selected commit"):
                release.publish(self.sha, paths)
            api.assert_not_called()
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_preflight_immutable_clean_source_and_remote_absence(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[]) as api:
            self.assertEqual(release.preflight(self.sha), (self.version, self.tag))
            api.assert_called_once_with("repos/owner/repo/releases?per_page=100&page=1")
        git(self.local, "commit", "--allow-empty", "-m", "different selected checkout")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "Checkout does not match"):
                release.preflight(self.sha)
            api.assert_not_called()
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_bump_rejects_merge_commit_before_push(self):
        real_run = release.run

        def merge_after_commit(*args, **kwargs):
            result = real_run(*args, **kwargs)
            if args[:2] == ("git", "commit"):
                tree = git(self.local, "rev-parse", "HEAD^{tree}")
                new = subprocess.run(
                    ["git", "commit-tree", tree, "-p", self.sha, "-p", self.ancestor],
                    input="merge bump fixture\n", text=True, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ).stdout.strip()
                git(self.local, "update-ref", "HEAD", new)
            return result

        with patch.object(release, "run", side_effect=merge_after_commit) as run:
            with self.assertRaisesRegex(ValueError, "single-parent direct child"):
                release.bump_branch(self.sha, "selected", "patch")
            self.assertFalse(any("push" in call.args for call in run.call_args_list))
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_guard_local_sha_target_parent_and_missing_env(self):
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        git(self.local, "commit", "--allow-empty", "-m", "direct child")
        new = git(self.local, "rev-parse", "HEAD")
        env = {**os.environ, "BUMP_EXPECTED_SHA": self.sha,
               "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new}
        valid = f"{new} {new} refs/heads/selected {self.sha}\n"
        result = subprocess.run([str(guard)], input=valid, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in (
            f"{new} {new} refs/heads/wrong {self.sha}\n",
            f"HEAD {new} refs/heads/selected {self.sha}\n",
            f"{new} {self.ancestor} refs/heads/selected {self.sha}\n",
            f"{new} {new} refs/heads/selected {self.ancestor}\n",
            valid * 2, "",
        ):
            result = subprocess.run([str(guard)], input=row, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([str(guard)], input=valid, env={}, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)

    def assets(self):
        paths = [Path(f"Common String Algorithm-{self.version}.{ext}") for ext in ("zip", "dmg")]
        for asset in paths:
            asset.write_bytes(b"fixture asset")
        return paths

    def test_guard_rejects_multiple_parents_even_with_selected_first_parent(self):
        tree = git(self.local, "rev-parse", "HEAD^{tree}")
        new = subprocess.run(
            ["git", "commit-tree", tree, "-p", self.sha, "-p", self.ancestor],
            input="merge fixture\n", text=True, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()
        git(self.local, "update-ref", "HEAD", new)
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        result = subprocess.run(
            [str(guard)], input=f"{new} {new} refs/heads/selected {self.sha}\n",
            env={**os.environ, "BUMP_EXPECTED_SHA": self.sha,
                 "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("advertised branch state differs", result.stderr)
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)

    def publication_api(self, calls, fail=None, race=None):
        def api(endpoint, payload=None, asset=None):
            calls.append((endpoint, payload, asset))
            if "/releases?" in endpoint:
                return []
            if endpoint.endswith("/git/refs"):
                if race:
                    git(self.remote, "update-ref", f"refs/tags/{self.tag}", race)
                # Atomic create-only bare Git models POST refs, including same-SHA rejection.
                git(self.remote, "update-ref", payload["ref"], payload["sha"], "0" * 40)
                return {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
            if endpoint.endswith("/releases"):
                if fail == "release":
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.published = {"id": 123, "tag_name": self.tag, "draft": False, "prerelease": False}
                return self.published
            if asset is not None:
                if fail == asset.suffix:
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.uploaded.append(asset.name)
                return {"id": 456, "name": asset.name,
                        "size": asset.stat().st_size, "state": "uploaded"}
            raise AssertionError(endpoint)
        return api

    def test_create_only_sha_new_release_id_original_notes(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)):
            release.publish(self.sha, self.assets())
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIn("/releases?", calls[0][0])
        self.assertTrue(calls[1][0].endswith("/git/refs"))
        self.assertEqual(calls[2][1], {
            "tag_name": self.tag, "target_commitish": self.sha, "name": self.tag,
            "draft": False, "prerelease": False, "body": ""})
        self.assertEqual(len(calls), 5)
        for endpoint, payload, asset in calls[3:]:
            self.assertIn("/releases/123/assets?name=", endpoint)
            self.assertIsNone(payload)
            self.assertIsNotNone(asset)

    def tag_race(self, sha):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, race=sha)):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), sha)
        self.assertIsNone(self.published)

    def test_same_sha_tag_race(self):
        self.tag_race(self.sha)

    def test_different_sha_tag_race(self):
        self.advance_peer()
        self.tag_race(git(self.peer, "rev-parse", "HEAD"))

    def test_release_post_failure_retains_tag(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, fail="release")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 3)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIsNone(self.published)
        self.assertEqual(self.uploaded, [])

    def test_upload_failure_retains_tag_release_earlier_asset(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, fail=".dmg")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 5)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [f"Common String Algorithm-{self.version}.zip"])

    def test_first_upload_failure_retains_tag_and_release(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, fail=".zip")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 4)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [])

    def test_tag_post_failure_does_not_create_release_or_upload(self):
        calls = []

        def failed_tag(endpoint, payload=None, asset=None):
            calls.append((endpoint, payload, asset))
            if "/releases?" in endpoint:
                return []
            raise subprocess.CalledProcessError(1, ["gh", "api", "git/refs"])

        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=failed_tag):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertIsNone(self.published)
        self.assertEqual(self.uploaded, [])

    def test_final_recheck_new_draft(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[]):
            release.preflight(self.sha)
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[entry(self.tag, True)]) as api:
            with self.assertRaisesRegex(ValueError, "draft or published"):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 1)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_final_later_page_failure_stops_before_creation(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[]):
            release.preflight(self.sha)
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=[
                    [entry()] * 100, subprocess.CalledProcessError(1, ["gh", "api", "404"])
                ]) as api:
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 2)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertIsNone(self.published)

    def test_remote_verification_blocks_release(self):
        calls = []
        real_remote_ref = release.remote_ref

        def incorrect_verification(ref):
            return "a" * 40 if real_remote_ref(ref) else None

        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)), \
                patch.object(release, "remote_ref", side_effect=incorrect_verification):
            with self.assertRaisesRegex(ValueError, "exact-SHA verification"):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertIsNone(self.published)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)

    def test_malformed_post_and_upload_retain_state(self):
        for kind in ("release", "upload"):
            with self.subTest(kind=kind):
                if kind == "upload":
                    git(self.remote, "update-ref", "-d", f"refs/tags/{self.tag}")
                calls = []
                real_api = self.publication_api(calls)

                def malformed(endpoint, payload=None, asset=None):
                    result = real_api(endpoint, payload, asset)
                    if (kind == "release" and endpoint.endswith("/releases")) or (
                            kind == "upload" and asset is not None):
                        return {"id": None}
                    return result

                with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                        patch.object(release, "api", side_effect=malformed):
                    with self.assertRaisesRegex(ValueError, "Malformed"):
                        release.publish(self.sha, self.assets())
                self.assertEqual(len(calls), 3 if kind == "release" else 4)
                self.assertEqual(self.published["id"], 123)
                self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)

    def test_malformed_tag_post_response_retains_tag_without_release(self):
        calls = []
        real_api = self.publication_api(calls)

        def malformed(endpoint, payload=None, asset=None):
            result = real_api(endpoint, payload, asset)
            return {"ref": None} if endpoint.endswith("/git/refs") else result

        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=malformed):
            with self.assertRaisesRegex(ValueError, "exact-SHA verification"):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIsNone(self.published)

    def test_missing_empty_wrong_assets_before_mutation(self):
        for paths in (
            [Path(f"Common String Algorithm-{self.version}.{ext}") for ext in ("zip", "dmg")],
            [Path("wrong.zip"), Path("wrong.dmg")],
        ):
            with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                    patch.object(release, "api") as api:
                with self.assertRaises(ValueError):
                    release.publish(self.sha, paths)
                api.assert_not_called()
        paths = self.assets()
        paths[0].write_bytes(b"")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.publish(self.sha, paths)
            api.assert_not_called()


class WiringTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is required for the Windows path fixture")
    def test_windows_cleanup_and_normalization_ignore_committed_stale_candidates(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()

        def script(step):
            body = workflow.split(f"      - name: {step}\n", 1)[1].split(
                "\n      - name:", 1)[0].split("        run: |\n", 1)[1]
            return "\n".join(line[10:] for line in body.splitlines()).replace(
                "${{ env.PRODUCT_NAME }}", "Common String Algorithm").replace(
                "${{ env.BASE_DIR }}", "test")

        with tempfile.TemporaryDirectory(prefix=".windows-path-tests-", dir=ROOT) as temp:
            root = Path(temp)
            output = root / (
                "Common String Algorithm.4dbase/plugins/Common String Algorithm.bundle/"
                "contents/windows64/Common String Algorithm.4DX")
            output.parent.mkdir(parents=True)
            output.write_bytes(b"committed stale binary")
            dependency = output.with_name("preserved-runtime.dll")
            dependency.write_bytes(b"keep dependency")
            other = root / "other/Plugins/Common String Algorithm.4DX"
            other.parent.mkdir(parents=True)
            other.write_bytes(b"wrong recursive candidate")
            destination = root / (
                "test/Plugins/Common String Algorithm.bundle/Contents/Windows64/"
                "Common String Algorithm.4DX")

            def execute(step):
                runner = root / "fixture.ps1"
                runner.write_text("$ErrorActionPreference = 'Stop'\n" + script(step))
                return subprocess.run(
                    ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(runner)],
                    cwd=root, text=True, capture_output=True)

            cleaned = execute("clean stale outputs")
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(dependency.read_bytes(), b"keep dependency")
            self.assertEqual(other.read_bytes(), b"wrong recursive candidate")
            missing = execute("normalize windows output to canonical case")
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(destination.exists())
            output.write_bytes(b"fresh selected-source binary")
            normalized = execute("normalize windows output to canonical case")
            self.assertEqual(normalized.returncode, 0, normalized.stderr)
            self.assertEqual(destination.read_bytes(), b"fresh selected-source binary")
            self.assertEqual(output.read_bytes(), destination.read_bytes())
            self.assertEqual(dependency.read_bytes(), b"keep dependency")
            self.assertEqual(other.read_bytes(), b"wrong recursive candidate")

    def test_exact_fresh_windows_outdir_and_original_native_contract(self):
        project = ET.parse(ROOT / "Common String Algorithm.vcxproj")
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        output = [node.text for node in project.findall(".//m:OutDir", ns)
                  if node.get("Condition") == "'$(Configuration)|$(Platform)'=='Release|x64'"]
        self.assertEqual(output, [
            r"$(ProjectDir)$(ProjectName).4dbase\plugins\$(ProjectName).bundle\contents\windows64\\"
            [:-1]])
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        source_path = "$product.4dbase/plugins/$product.bundle/contents/windows64"
        self.assertIn(f'$output = "{source_path}/$product.4DX"', workflow)
        self.assertIn("Test-Path -LiteralPath $output", workflow)
        self.assertIn("Remove-Item -LiteralPath $output -Force -ErrorAction Stop", workflow)
        self.assertIn(f'$source = "{source_path}/$product.4DX"', workflow)
        self.assertIn("Test-Path -LiteralPath $source -PathType Leaf", workflow)
        self.assertIn("Copy-Item -LiteralPath $source -Destination $destination -Force -ErrorAction Stop",
                      workflow)
        self.assertNotIn("Select-Object -First", workflow)
        self.assertIn("BASE_DIR: test", workflow)
        self.assertIn("MACOS_DEPLOYMENT_TARGET: '11.0'", workflow)
        self.assertIn('CONFIGURATION_BUILD_DIR="$PWD/$PLUGINS_DIR"', workflow)
        self.assertIn("-configuration Default", workflow)
        project_source = source.text(ROOT / source.PROJECT)
        for resource in ("constants.xlf in CopyFiles", "manifest.json in CopyFiles",
                         "InfoPlist.strings in Resources", "Cocoa.framework in Frameworks",
                         "AppKit.framework in Frameworks", "CoreGraphics.framework in Frameworks"):
            self.assertIn(resource, project_source)

    def test_notary_acceptance_and_transport_failures_block_publication(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        function = workflow.split("          notarize() {", 1)[1].split(
            '          notarize "$ZIP_PATH"', 1)[0]
        function = "notarize() {" + function
        # Exercise only the extracted shell gate with a local stub, never Apple's tools.
        with tempfile.TemporaryDirectory(prefix=".notary-gate-tests-", dir=ROOT) as temp:
            path = Path(temp)
            tool = path / "xcrun"
            tool.write_text('#!/bin/sh\nprintf "%s" "$NOTARY_RESPONSE"\nexit "$NOTARY_EXIT"\n')
            tool.chmod(0o755)
            for response, code, accepted in (
                ('{"status":"Accepted"}', "0", True),
                ('{"status":"Invalid"}', "0", False),
                ('{"status":"In Progress"}', "0", False),
                ('{"status":"Accepted"}', "1", False),
                ("{}", "0", False), ("invalid", "0", False),
                ("[]", "0", False), ('{"status":null}', "0", False),
            ):
                with self.subTest(response=response, code=code):
                    result = subprocess.run(
                        ["bash", "-c", 'set -euo pipefail\n' + function +
                         '\nnotarize fixture.zip\nprintf "PUBLICATION_GATE_PASSED\\n"\n'],
                        env={**os.environ, "PATH": f"{path}{os.pathsep}{os.environ['PATH']}",
                             "NOTARY_RESPONSE": response, "NOTARY_EXIT": code,
                             "KEYCHAIN_PATH": "unused-fixture"},
                        text=True, capture_output=True)
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
                    self.assertEqual("PUBLICATION_GATE_PASSED" in result.stdout, accepted)

    def test_manual_zero_inputs_immutable_native_gate_wiring(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertRegex(workflow, r"(?m)^name: Build$")
        self.assertEqual(workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip(),
                         "workflow_dispatch:")
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 3)
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 3)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", workflow)
        self.assertIn("needs: [version, build-windows]", workflow)
        self.assertIn("needs: version", workflow)
        self.assertEqual(workflow.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertNotIn("REF_TYPE", workflow)
        gates = [
            "validate source and publication availability",
            "build x64", "upload windows binaries", "download windows binaries",
            "import Developer ID certificate", "store notarytool credentials",
            "build macOS plugin (universal)", "verify universal binary",
            "merge Windows binaries into the bundle", "- name: codesign",
            "package, notarize & staple", "- name: create GitHub Release",
        ]
        self.assertEqual([workflow.index(gate) for gate in gates],
                         sorted(workflow.index(gate) for gate in gates))
        for required in ("PlatformToolset=v143", "WindowsTargetPlatformVersion=10.0",
                         'ARCHS="arm64 x86_64"', "CODE_SIGNING_ALLOWED=NO",
                         "codesign --verify --deep --strict", 'stapler staple "$DMG_PATH"',
                         'notarytool submit "$1"', 'notarize "$ZIP_PATH"', 'notarize "$DMG_PATH"',
                         "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
                         "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
                         "NOTARYTOOL_PASSWORD", "if-no-files-found: error",
                         "windows-binaries", "runs-on: windows-latest", "runs-on: macos-latest"):
            self.assertIn(required, workflow)
        for prohibited in ("continue-on-error", "always()", "inputs.", "softprops/",
                           "github.ref_name", "branches:", "refs/heads/master"):
            self.assertNotIn(prohibited, workflow)
        final = workflow.split("- name: create GitHub Release", 1)[1]
        self.assertEqual(final.count("python3 "), 1)
        self.assertIn('publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"', final)

    def test_bump_no_tag_or_destructive_publication(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("SELECTED_BRANCH: ${{ github.ref_name }}", workflow)
        self.assertIn('test "$REF_TYPE" = branch', workflow)
        for mode in ("patch", "minor", "major"):
            self.assertIn(f"- {mode}", workflow)
        helper = (ROOT / ".github/scripts/release.py").read_text()
        for prohibited in ('"DELETE"', '"PATCH"', "--clobber", "--force",
                           '"gh", "release", "create"', '"git", "tag"'):
            self.assertNotIn(prohibited, helper)
        self.assertIn('"push.followTags=false"', helper)
        self.assertIn('"--no-follow-tags"', helper)
        self.assertNotIn("workflow_dispatch", helper)

    def test_cli_asset_options(self):
        assets = [Path(f"Common String Algorithm-1.2.3.{ext}") for ext in ("zip", "dmg")]
        with patch.object(sys, "argv", ["release.py", "publish", "--sha", "a" * 40,
                                       *map(str, assets)]), \
                patch.object(release, "publish") as publish:
            release.main()
        publish.assert_called_once_with("a" * 40, assets)


if __name__ == "__main__":
    unittest.main()
