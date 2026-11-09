"""Marketing-first source versions; independent build and prebuilt counters are excluded."""

import argparse
from pathlib import Path
import plistlib
import re
from xml.parsers.expat import ExpatError


PROJECT = Path("Common String Algorithm.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
BUILD_VERSION = r"[0-9]+(?:\.[0-9]+){0,2}"
KEYS = ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION")
SETTING_COUNT = 3
SETTING = re.compile(
    r"(?m)^([ \t]*(MARKETING_VERSION|CURRENT_PROJECT_VERSION)[ \t]*=[ \t]*)([^;\n]*)(;)"
)
REFERENCES = {f"$({key})": key for key in KEYS}
REFERENCES.update({f"${{{key}}}": key for key in KEYS})
LOCALIZED_SHORT = re.compile(
    r'(?m)^([ \t]*CFBundleShortVersionString[ \t]*=[ \t]*")([^"]*)("[ \t]*;[ \t]*)$'
)
LOCALIZED_INFO = re.compile(
    r'(?m)^([ \t]*CFBundleGetInfoString[ \t]*=[ \t]*"Common String Algorithm version )'
    r'([^,"]*)(, Copyright 2019 miyako\."[ \t]*;[ \t]*)$'
)
PLIST_VERSION = re.compile(
    r"(<key>CFBundle(?:ShortVersionString|Version)</key>\s*<string>)([^<]*)(</string>)"
)


class UniqueDictionary(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f"Duplicate source plist key: {key}")
        super().__setitem__(key, value)


def unquote(value):
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def text(path):
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def rendered(path, transform):
    original = path.read_bytes()
    decoded = original.decode("utf-8-sig")
    endings = re.findall(r"\r\n|\r|\n", decoded)
    updated = transform(decoded.replace("\r\n", "\n").replace("\r", "\n"))
    if updated.count("\n") != len(endings):
        raise ValueError("Metadata rewrite changed line structure")
    iterator = iter(endings)
    encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
    return re.sub("\n", lambda _: next(iterator), updated).encode(encoding)


def rewrite(path, transform):
    path.write_bytes(rendered(path, transform))


def read(root=Path(".")):
    root = Path(root)
    project = text(root / PROJECT)
    fields = {key: [] for key in KEYS}
    for key in KEYS:
        assignments = re.findall(rf'(?m)^[ \t]*(?:{key}\b|"{key}")', project)
        if len(assignments) != SETTING_COUNT:
            raise ValueError(f"Expected three source assignments for {key}")
    for match in SETTING.finditer(project):
        fields[match[2]].append(unquote(match[3].strip()))
    if any(len(fields[key]) != SETTING_COUNT for key in KEYS):
        raise ValueError("Expected three source settings for each version key")
    marketing = set(fields["MARKETING_VERSION"])
    if len(marketing) != 1 or not re.fullmatch(VERSION, next(iter(marketing))):
        raise ValueError("MARKETING_VERSION must be one strict X.Y.Z across configurations")
    version = next(iter(marketing))
    # The original header explicitly selected marketing, with current only a fallback.
    current = set(fields["CURRENT_PROJECT_VERSION"])
    if len(current) != 1:
        raise ValueError("Independent CURRENT_PROJECT_VERSION settings have drifted")
    build = next(iter(current))
    if not re.fullmatch(BUILD_VERSION, build) and REFERENCES.get(build) != "MARKETING_VERSION":
        raise ValueError("CURRENT_PROJECT_VERSION is invalid or cyclic")
    resolved = {"MARKETING_VERSION": version,
                "CURRENT_PROJECT_VERSION": version if build in REFERENCES else build}
    try:
        plist = plistlib.loads((root / PLIST).read_bytes(), dict_type=UniqueDictionary)
    except (plistlib.InvalidFileException, ExpatError, UnicodeError) as exc:
        raise ValueError("Source Info.plist has invalid serialization") from exc
    if not isinstance(plist, dict):
        raise ValueError("Source Info.plist must be a dictionary")
    serialized = list(PLIST_VERSION.finditer(text(root / PLIST)))
    if len(serialized) != sum(key in plist for key in (
            "CFBundleShortVersionString", "CFBundleVersion")):
        raise ValueError("Source plist versions must be editable XML strings")
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if key not in plist:
            continue
        value = plist[key]
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        actual = resolved.get(REFERENCES.get(value), value)
        if (key == "CFBundleShortVersionString" and actual != version) or (
                key == "CFBundleVersion" and not re.fullmatch(BUILD_VERSION, actual)):
            raise ValueError(f"{key} is invalid, unresolved or has drifted")
        if [m[2] for m in serialized if f"<key>{key}</key>" in m[1]] != [value]:
            raise ValueError(f"{key} has unsupported XML serialization")
    localized = text(root / LOCALIZED)
    for key, pattern in (
        ("CFBundleShortVersionString", LOCALIZED_SHORT),
        ("CFBundleGetInfoString", LOCALIZED_INFO),
    ):
        assignments = re.findall(rf'(?m)^[ \t]*(?:{key}|"{key}")[ \t]*=', localized)
        if len(assignments) != 1 or [m[2] for m in pattern.finditer(localized)] != [version]:
            raise ValueError("Localized source version is missing, invalid or has drifted")
    return version


def bump(mode, root=Path(".")):
    root = Path(root)
    current = read(root)
    index = ("major", "minor", "patch").index(mode)
    parts = list(map(int, current.split(".")))
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))

    def replace(match):
        if match[2] != "MARKETING_VERSION":
            return match[0]
        literal = match[3].strip()
        replacement = f'"{new}"' if literal.startswith('"') else new
        return f"{match[1]}{match[3].replace(literal, replacement, 1)}{match[4]}"

    def localized(value):
        for pattern in (LOCALIZED_SHORT, LOCALIZED_INFO):
            value = pattern.sub(lambda m: f"{m[1]}{new}{m[3]}", value)
        return value

    transforms = (
        (PROJECT, lambda value: SETTING.sub(replace, value)),
        (PLIST, lambda value: PLIST_VERSION.sub(
            lambda m: f"{m[1]}{new}{m[3]}"
            if "<key>CFBundleShortVersionString</key>" in m[1] and m[2] not in REFERENCES
            else m[0], value,
        )),
        (LOCALIZED, localized),
    )
    updates = [(root / path, rendered(root / path, transform)) for path, transform in transforms]
    for path, data in updates:
        path.write_bytes(data)
    if read(root) != new:
        raise ValueError("Bumped metadata did not validate")
    return new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    print(bump(args.bump) if args.bump else read())
