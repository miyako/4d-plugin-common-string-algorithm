#!/usr/bin/env python3
"""Unsigned actual-source ownership checks; never invokes project build phases."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "5df0dc6d65504e66fc9c357e4f30af4d9a4fd65a"
TESTS = ("file", "bytes", "copy", "gray", "size", "thumbnail", "arrays", "dispatch")


def build(source, output):
    sdk = source / "4D Plugin API"
    sources = [
        sdk / "4DPluginAPI.c", *sorted((sdk / "Classes").glob("*.cpp")),
        source / "4DPlugin.cpp",
        *(source / name for name in ("dice.c", "lcs.c", "jaro_winkler.c", "levenshtein.c")),
        ROOT / "tests/native/ownership.cpp",
    ]
    subprocess.run([
        "clang++", "-std=c++11", "-x", "objective-c++", "-include", "Cocoa/Cocoa.h",
        "-include", "Carbon/Carbon.h", "-I", str(sdk), "-I", str(sdk / "Classes"),
        "-I", str(source), "-Wno-deprecated-declarations", "-Wno-c++11-compat-deprecated-writable-strings",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
        *map(str, sources), "-framework", "Cocoa", "-framework", "Carbon",
        "-o", str(output),
    ], check=True)


def run(executable, case):
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
    return subprocess.run([str(executable), case], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true",
                        help="also prove named failures against immutable original sources")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ownership-", dir=ROOT / "tests/native") as temp:
        work = Path(temp)
        if args.baseline:
            baseline = work / "baseline"
            baseline.mkdir()
            paths = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", BASELINE], cwd=ROOT, text=True
            ).splitlines()
            for name in paths:
                if Path(name).suffix in (".c", ".cpp", ".h"):
                    destination = baseline / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(subprocess.check_output(
                        ["git", "show", f"{BASELINE}:{name}"], cwd=ROOT))
            build(baseline, work / "original")
            for case in TESTS:
                result = run(work / "original", case)
                expected = {
                    "file": "double disposal of string",
                    "bytes": "unbalanced picture references",
                    "copy": "AddressSanitizer: heap-buffer-overflow",
                    "gray": "unbalanced picture references",
                    "size": "unbalanced picture references",
                    "thumbnail": "unbalanced picture references",
                }.get(case)
                if expected:
                    if result.returncode == 0 or expected not in result.stdout:
                        raise RuntimeError(f"baseline {case}: wrong failure\n{result.stdout}")
                    print(f"BASELINE FAIL (expected) {case}: {expected}", flush=True)
                elif result.returncode:
                    raise RuntimeError(f"baseline {case}:\n{result.stdout}")
                else:
                    print(f"BASELINE PASS {case}", flush=True)
        build(ROOT, work / "fixed")
        for case in TESTS:
            result = run(work / "fixed", case)
            if result.returncode:
                raise RuntimeError(f"fixed {case}:\n{result.stdout}")
            print(f"FIXED PASS {case}: {result.stdout.strip()}", flush=True)


if __name__ == "__main__":
    main()
