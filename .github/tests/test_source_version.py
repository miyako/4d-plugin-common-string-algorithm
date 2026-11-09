import importlib.util
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("source_version", ROOT / ".github/scripts/source_version.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".source-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.copy_source()
        self.current = source.read(self.root)

    def copy_source(self):
        for name in source.SOURCE_PATHS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)

    def plist(self, **values):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.update(values)
        path.write_bytes(plistlib.dumps(data))

    def snapshot(self):
        return {name: ((self.root / name).read_bytes(),
                       stat.S_IMODE((self.root / name).stat().st_mode))
                for name in source.SOURCE_PATHS if (self.root / name).exists()}

    def assert_rejected(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.read(self.root)
        with self.assertRaises(ValueError):
            source.bump("patch", self.root)
        self.assertEqual(before, self.snapshot())

    def set_current(self, value):
        path = self.root / source.PROJECT
        path.write_text(source.SETTING.sub(
            lambda m: f"{m[1]}{value}{m[4]}" if m[2] == "CURRENT_PROJECT_VERSION" else m[0],
            source.text(path)))

    def fixture(self):
        (self.root / source.PROJECT).write_text(
            ("MARKETING_VERSION = 3.2.1;\nCURRENT_PROJECT_VERSION = 14.3;\n")
            * source.SETTING_COUNT)
        (self.root / source.PLIST).write_bytes(plistlib.dumps({
            "CFBundleName": "Common String Algorithm",
            "CFBundleShortVersionString": "3.2.1", "CFBundleVersion": "77",
        }))
        (self.root / source.LOCALIZED).write_text(
            'CFBundleName = "Common String Algorithm";\n'
            'CFBundleShortVersionString = "3.2.1";\n'
            'CFBundleGetInfoString = "Common String Algorithm version 3.2.1, '
            'Copyright 2019 miyako.";\n')

    def expected_bytes(self, name, data, old, new):
        if name == source.PROJECT:
            pattern = rb'(\bMARKETING_VERSION[ \t]*=[ \t]*"?)' + re.escape(old.encode())
        elif name == source.PLIST:
            pattern = (rb'(<key>CFBundleShortVersionString</key>\s*<string>)'
                       + re.escape(old.encode()) + rb'(?=</string>)')
        else:
            pattern = (rb'(\bCFBundleShortVersionString[ \t]*=[ \t]*"|'
                       rb'\bCFBundleGetInfoString[ \t]*=[ \t]*"Common String Algorithm version )'
                       + re.escape(old.encode()))
        return re.sub(pattern, lambda m: m[1] + new.encode(), data)

    def assert_bumped_bytes(self, before, old, new):
        for name, (data, mode) in before.items():
            path = self.root / name
            self.assertEqual(path.read_bytes(), self.expected_bytes(name, data, old, new))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.assertEqual(source.read(self.root), new)

    def test_live_metadata_and_all_bump_modes(self):
        self.assertEqual(source.PROJECT, Path("Common String Algorithm.xcodeproj/project.pbxproj"))
        self.assertEqual(source.PLIST, Path("Info.plist"))
        self.assertEqual(source.LOCALIZED, Path("English.lproj/InfoPlist.strings"))
        self.assertEqual(source.SETTING_COUNT, 3)
        self.assertEqual(set(source.KEYS), {"MARKETING_VERSION", "CURRENT_PROJECT_VERSION"})
        parts = list(map(int, self.current.split(".")))
        for mode, expected in (
            ("patch", [parts[0], parts[1], parts[2] + 1]),
            ("minor", [parts[0], parts[1] + 1, 0]),
            ("major", [parts[0] + 1, 0, 0]),
        ):
            with self.subTest(mode=mode):
                self.copy_source()
                before = self.snapshot()
                expected = ".".join(map(str, expected))
                self.assertEqual(source.bump(mode, self.root), expected)
                self.assert_bumped_bytes(before, self.current, expected)

    def test_stable_fixture_preserves_independent_build_metadata(self):
        self.fixture()
        before = self.snapshot()
        self.assertEqual(source.read(self.root), "3.2.1")
        self.assertEqual(source.bump("minor", self.root), "3.3.0")
        self.assert_bumped_bytes(before, "3.2.1", "3.3.0")
        self.assertEqual(source.text(self.root / source.PROJECT).count(
            "CURRENT_PROJECT_VERSION = 14.3;"), source.SETTING_COUNT)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         "77")
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)")
        self.assert_rejected()

    def test_invalid_missing_extra_and_drifted_settings(self):
        path = self.root / source.PROJECT
        for key in source.KEYS:
            for bad in ("v1.2.3", "1.2.3-beta", "$(UNKNOWN)", "${UNKNOWN}", "",
                        "$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
                for count in (1, source.SETTING_COUNT):
                    with self.subTest(key=key, bad=bad, count=count):
                        self.copy_source()
                        remaining = count

                        def replace(m):
                            nonlocal remaining
                            if m[2] == key and remaining:
                                remaining -= 1
                                return f"{m[1]}{bad}{m[4]}"
                            return m[0]

                        path.write_text(source.SETTING.sub(replace, source.text(path)))
                        self.assert_rejected()
            self.copy_source()
            original = source.text(path)
            matches = [m for m in source.SETTING.finditer(original) if m[2] == key]
            self.assertEqual(len(matches), source.SETTING_COUNT)
            first = matches[0]
            for replacement in ("", f"{key} = 987654.3.2;"):
                path.write_text(original[:first.start()] + replacement + original[first.end():])
                self.assert_rejected()
            for extra in (
                f"{key} = {self.current};", f'"{key}" = "{self.current}";',
                f"{key} = {self.current}", f"{key} = ;", f"{key} = 1.2.3; junk",
            ):
                path.write_text(original + "\n" + extra + "\n")
                self.assert_rejected()
        for bad in ("1.2", "14.3", "77", "01.2.3", "$(MARKETING_VERSION)",
                    "${MARKETING_VERSION}"):
            self.copy_source()
            path.write_text(source.SETTING.sub(
                lambda m: f"{m[1]}{bad}{m[4]}" if m[2] == "MARKETING_VERSION" else m[0],
                source.text(path)))
            self.assert_rejected()
        for bad in ("1.2.3.4", "-1", "1.", ".1", "1..2"):
            self.copy_source()
            self.set_current(bad)
            self.assert_rejected()

    def test_independent_current_and_build_versions(self):
        for value in ("0", "7", "14.3", "01.002.003", "123.456.789"):
            with self.subTest(value=value):
                self.copy_source()
                self.set_current(value)
                self.plist(CFBundleVersion=value)
                before = self.snapshot()
                new = source.bump("patch", self.root)
                self.assert_bumped_bytes(before, self.current, new)

    def test_plist_invalid_values_and_short_version_drift(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            bad_values = ("$(UNKNOWN)", "${UNKNOWN}", "$(PRODUCT_NAME)", "", "invalid",
                          123, True, [], {}, "v1.2.3", "1.2.3.4", "-1")
            if key == "CFBundleShortVersionString":
                bad_values += ("1.2", "14.3", "7", "01.2.3", self.current + ".0",
                               str(int(self.current.split(".")[0]) + 1) + ".0.0")
            for value in bad_values:
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: value})
                    self.assert_rejected()
        path = self.root / source.PLIST
        for value in ([], "not a dictionary", 123):
            path.write_bytes(plistlib.dumps(value))
            self.assert_rejected()

    def test_optional_plist_keys_stay_absent_and_literal_short_co_bumps(self):
        for short in (False, True):
            for build in (False, True):
                with self.subTest(short=short, build=build):
                    self.copy_source()
                    path = self.root / source.PLIST
                    data = plistlib.loads(path.read_bytes())
                    data.pop("CFBundleShortVersionString", None)
                    data.pop("CFBundleVersion", None)
                    if short:
                        data["CFBundleShortVersionString"] = self.current
                    if build:
                        data["CFBundleVersion"] = "77"
                    path.write_bytes(plistlib.dumps(data))
                    before = self.snapshot()
                    new = source.bump("minor", self.root)
                    self.assert_bumped_bytes(before, self.current, new)
                    result = plistlib.loads(path.read_bytes())
                    self.assertEqual("CFBundleShortVersionString" in result, short)
                    self.assertEqual("CFBundleVersion" in result, build)

    def test_supported_references_preserved_and_resolved(self):
        for reference in source.REFERENCES:
            for current in ("14.3", '"$(MARKETING_VERSION)"', '"${MARKETING_VERSION}"'):
                with self.subTest(reference=reference, current=current):
                    self.copy_source()
                    self.set_current(current)
                    self.plist(CFBundleShortVersionString=reference, CFBundleVersion=reference)
                    if (source.REFERENCES[reference] == "CURRENT_PROJECT_VERSION"
                            and current == "14.3"):
                        self.assert_rejected()
                    else:
                        before = self.snapshot()
                        new = source.bump("patch", self.root)
                        self.assert_bumped_bytes(before, self.current, new)
        for reference in source.REFERENCES:
            self.copy_source()
            self.set_current("14.3")
            self.plist(CFBundleVersion=reference)
            before = self.snapshot()
            new = source.bump("patch", self.root)
            self.assert_bumped_bytes(before, self.current, new)
        for reference in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
            self.copy_source()
            self.set_current(reference)
            self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)")
            before = self.snapshot()
            new = source.bump("patch", self.root)
            self.assert_bumped_bytes(before, self.current, new)

    def test_duplicate_plist_keys_and_invalid_serialization_fail_closed(self):
        path = self.root / source.PLIST
        for key in ("CFBundleShortVersionString", "CFBundleVersion", "CFBundleName"):
            for value in (self.current, "invalid"):
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: value})
                    data = source.text(path)
                    path.write_text(data.replace(
                        "</dict>", f"<key>{key}</key><string>{value}</string>\n</dict>"))
                    self.assert_rejected()
        self.copy_source()
        self.plist(CFBundleShortVersionString=self.current)
        original = (self.root / source.PLIST).read_bytes()
        for malformed in (
            b"not a plist", b"", original.replace(b"</dict>", b""),
            original.replace(self.current.encode(),
                             f"&#{ord(self.current[0])};{self.current[1:]}".encode()),
            plistlib.dumps(plistlib.loads(original), fmt=plistlib.FMT_BINARY),
        ):
            with self.subTest(serialization=malformed[:40]):
                path.write_bytes(malformed)
                self.assert_rejected()

    def test_localized_validation(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for pattern in (source.LOCALIZED_SHORT, source.LOCALIZED_INFO):
            for bad in ("1.0", self.current + ".0", "invalid", "", "$(UNKNOWN)",
                        "$(MARKETING_VERSION)", "${CURRENT_PROJECT_VERSION}", "01.2.3",
                        "1.2.3-beta", str(int(self.current.split(".")[0]) + 1) + ".0.0"):
                with self.subTest(pattern=pattern.pattern, bad=bad):
                    path.write_text(pattern.sub(lambda m: f"{m[1]}{bad}{m[3]}", original))
                    self.assert_rejected()
            path.write_text(pattern.sub("", original))
            self.assert_rejected()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            for modified in (
                original.replace(key, "UnknownKey"),
                original + f'\n{key} = "{self.current}";\n',
                original + f'\n"{key}" = "{self.current}";\n',
                original.replace(f'{key} = "', f'{key} = ').replace('";', ";"),
                original + f'\n{key} = "unterminated\n',
            ):
                path.write_text(modified)
                self.assert_rejected()
        for old, new in (
            ("Common String Algorithm", "Other Product"),
            ("Copyright 2019", "Copyright 2018"),
            ("Copyright 2019 miyako", "Copyright 2019 someone"),
        ):
            path.write_text(original.replace(old, new))
            self.assert_rejected()

    def test_missing_source_files_rejected_without_writes(self):
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).unlink()
            before = self.snapshot()
            with self.assertRaises(FileNotFoundError):
                source.bump("patch", self.root)
            self.assertEqual(before, self.snapshot())

    def test_byte_preserving_endings_bom_and_modes(self):
        for newline in ("\n", "\r", "\r\n", "mixed"):
            for bom in (b"", b"\xef\xbb\xbf"):
                with self.subTest(newline=newline, bom=bom):
                    self.copy_source()
                    for i, name in enumerate(source.SOURCE_PATHS):
                        path = self.root / name
                        lines = source.text(path).splitlines(keepends=True)
                        data = "".join(line.replace(
                            "\n", ("\r", "\r\n", "\n")[j % 3] if newline == "mixed" else newline)
                            for j, line in enumerate(lines))
                        path.write_bytes(bom + data.encode())
                        path.chmod((0o755, 0o640, 0o644)[i])
                    before = self.snapshot()
                    new = source.bump("minor", self.root)
                    self.assert_bumped_bytes(before, self.current, new)

    def test_whitespace_quotes_and_unrelated_version_bytes_preserved(self):
        for quoted in (False, True):
            self.copy_source()
            path = self.root / source.PROJECT
            path.write_text(source.SETTING.sub(
                lambda m: f'{m[2]} \t= \t'
                + (f'"{m[3].strip()}"' if quoted else m[3].strip()) + " \t;",
                source.text(path)))
            with path.open("a") as stream:
                stream.write(f'\n// unrelated version {self.current}\n')
            self.plist(UnrelatedVersion=self.current, CFBundleVersion=self.current)
            localized = self.root / source.LOCALIZED
            localized.write_bytes(localized.read_bytes().replace(b" = ", b" \t= \t")
                                  .replace(b'";', b'" \t; \t'))
            with localized.open("a") as stream:
                stream.write(f'\nUnrelatedVersion = "{self.current}";\n')
            before = self.snapshot()
            new = source.bump("patch", self.root)
            self.assert_bumped_bytes(before, self.current, new)

    def test_prebuilt_4d_schema_and_native_files_ignored(self):
        bundle = ("Common String Algorithm.4dbase/Plugins/"
                  "Common String Algorithm.bundle/Contents/")
        excluded = (
            bundle + "Info.plist", bundle + "Resources/English.lproj/InfoPlist.strings",
            bundle + "Resources/manifest.json", bundle + "Resources/constants.xlf",
            bundle + "MacOS/Common String Algorithm",
            bundle + "Windows64/Common String Algorithm.4DX",
            "Common String Algorithm.4dbase/Data/Common String Algorithm.4DD",
            "Common String Algorithm.4dbase/Project/Common String Algorithm.4DProject",
            "Common String Algorithm.4dbase/Project/Sources/catalog.4DCatalog",
            "4D_Plugin_Wizard.4dd", "English.lproj/locversion.plist", "manifest.json",
            "constants.xlf", "4D Plugin API/4DPluginAPI.h", "4D Plugin API/Classes/C_TYPES.h",
            "Common String Algorithm.vcxproj", "Common String Algorithm.vcxproj.filters",
            "Common String Algorithm.sln", "4DPlugin.h", "4DPlugin.cpp",
            "dice.c", "jaro_winkler.c", "lcs.c", "levenshtein.c",
        )
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"], check=True, capture_output=True, text=True
        ).stdout.splitlines()
        self.assertTrue(set(excluded).issubset(tracked))
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        before = {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
                  for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {
            name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
            for name in excluded
        })

    def test_invalid_mode_and_cli_read_do_not_write(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("other", self.root)
        output = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/source_version.py")],
            cwd=self.root, check=True, capture_output=True, text=True,
        )
        self.assertEqual(output.stdout.strip(), self.current)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
