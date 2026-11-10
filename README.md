![version](https://img.shields.io/badge/version-17%2B-3E8B93)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-common-string-algorithm)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-common-string-algorithm/total)

# 4d-plugin-common-string-algorithm

## Native ownership maintenance

The bounded audit baseline is `5df0dc6d65504e66fc9c357e4f30af4d9a4fd65a`.
Both root and committed-bundle `manifest.json` files declare the same six
two-Text commands, in the order dispatched by `PluginMain` ->
`CommandDispatcher` (selectors 1-6). Neither declares an array parameter;
`&Y` metadata would indicate array capability, not ownership.

The inventory includes all 22 tracked native implementation files, 27 headers,
the prefix header and export definition, not just exported-command matches:

| Surface | Reachability and ownership |
|---|---|
| `4DPlugin.cpp/.h` | Six scalar entry points copy borrowed input text into `C_TEXT`; the two Text results use the content setter, not descriptor transfer. |
| `dice`, `lcs`, `jaro_winkler`, `levenshtein` (`.c/.h`) | Algorithm boundaries use copied C++ strings and wrapper results. Third-party algorithm implementations are unchanged. |
| `Classes/C_TEXT.cpp/.h`, `ARRAY_TEXT.cpp/.h` | Own C++ string copies; array output creates an independent descriptor per element and leaves accepted transfers with the array. No immediate post-transfer disposal was found. |
| `Classes/C_PICTURE.cpp/.h` | Compiled but dormant from these six commands. Fixed the path descriptor's double disposal, initial empty-string/picture overwrites, missing temporary/argument picture releases, and conversion byte-count overread. |
| `Classes/C_POINTER.cpp/.h` | Compiled but dormant; metadata/value interpretation is deferred, not blindly cleared. |
| `Classes/C_BLOB.cpp/.h` | Compiled but dormant; owns copied bytes and transfers newly allocated output handles. No string descriptor assignment. |
| `Classes/C_DATE`, `C_INTEGER`, `C_LONGINT`, `C_REAL`, `C_TIME` (`.cpp/.h`) | Scalar value wrappers, with no string descriptor ownership. |
| `Classes/ARRAY_BOOLEAN`, `ARRAY_DATE`, `ARRAY_INTEGER`, `ARRAY_LONGINT`, `ARRAY_REAL`, `ARRAY_TIME` (`.cpp/.h`) | C++ value arrays and scalar SDK setters; no string descriptor ownership. |
| `Classes/C_TYPES.h`, `4D Plugin_Prefix.pch` | Shared types/platform imports and Carbon prefix. |
| `4DPluginAPI.c/.h`, `EntryPoints.h`, `Flags.h`, `PrivateTypes.h`, `PublicTypes.h`, `4DPluginAPI.def` | Bundled SDK/ABI boundary, inspected and unchanged; `FourDPackex` calls `PluginMain`. |

The Xcode Sources phase and current `Common String Algorithm.vcxproj` compile
all 22 implementations, including all 16 wrapper implementations; Windows uses
the bundled SDK and Classes include directories. The legacy
`Common String Algorithm.vc10.vcxproj` also compiles all wrappers and the entry
point/SDK, but omits the four algorithm implementations. The API header includes
all wrapper headers; none of these dormant helpers is excluded by a manifest.

### Bundled contracts and fixes

The SDK implementation last changed in repository commit
`62b138f57b9f66f997aa38cdd5a4a692d87e94e6` (`2.0`).
Its Git blob is `29788ed041effaf67269ccd93f971e8aee2ce5f8`;
the API header blob is `9054b45ffc7ff6f5b8d57529a3788a55d977b314`.
The implementation's `v14` and header's `v13` comments are **not verified
upstream release identities**. Guidance was checked against
`miyako/skills` commit `e6b492fcb81e5e1a7f7db723594b420e63bf6eb9`,
including merged ownership-guidance PRs 69 and 71.

In this SDK, `PA_SetStringInArray` disposes the old element and shallow-transfers
the incoming descriptor only for Unicode arrays with non-null data, indices
from zero through the element count, and a non-null descriptor pointer.
Rejected assignments retain caller ownership. `PA_GetStringInArray` is borrowed:
copy before replacing, shrinking or clearing its owner. Accepted independent
outputs must not share an allocation.

`PA_SetStringVariable` and `PA_SetPictureVariable` also shallow-assign, without
clearing overwritten content. `PA_CreateVariable(Unistring/Picture)` may already
own an allocated empty value. Picture arguments immediately assigned by the
wrapper now start Undefined. The path descriptor has exactly one owner,
`args[0]`, cleared once after synchronous execution. `setPicture` retains;
`fromFileAtPath` therefore clears its picture argument after retaining, and
`setBytes` releases its temporary created picture after retaining.
Returned copies/thumbnails still hand an owning picture reference to the caller.
`createCopy` converts the charset converter's returned byte length to UTF-16
code units before constructing a string. `PA_ReturnString`/`PA_SetUnistring`
use an engine content setter and must not be treated as array transfers.

### Unsigned regression

On macOS with the existing Apple toolchain:

```sh
python3 tests/native/run.py --baseline
```

This directly compiles the actual entry point, all algorithms/wrappers and
**the full unchanged bundled SDK** as Objective-C++, with ASan/UBSan and an
engine-boundary callback shim. It never invokes Xcode project phases. The same
harness is also linked against native sources extracted from the immutable
baseline. Baseline `file` fails for double string disposal, `copy` for an ASan
heap-buffer-overread, and `bytes`, `gray`, `size`, `thumbnail` for unbalanced
picture references; all eight fixed cases pass. `arrays` and `dispatch` pass
on both revisions.

Fixtures assert exact ASCII, BMP, supplementary surrogate-pair and empty text;
null and allocated empty descriptors; byte capacities, code-unit counts and
termination; borrowed-copy survival after mutation/churn; independent accepted
array transfers, replacement, shrink, clear and type/index/data/null-descriptor
rejections; synchronous scalar cleanup independence; and picture handoff
survival with unchanged/replaced command arguments. Explicit allocation, handle
and picture-reference balances cover leaks because macOS LSan is not used.
The existing 54 source/lifecycle tests also pass; release behavior is unchanged.

### Deferred boundaries

`C_POINTER::getVariable` consumes variable-definition metadata from
`PA_GetPointerValue`, whose header calls for clearing returned values, but whose
engine representation is not established here. Clearing it as an ordinary
value, or clearing then relabeling it borrowed, is not justified. SDK
application-path and successful picture-data output ownership is also
undocumented locally; no guessed disposal was added. The shim uses no picture
representations and does not certify those outputs.

This older SDK and the first-party code contain no object-property/collection
getter callsites or JSON Parse callbacks. The picture command callsites are
procedures; general owning method/command return values must still be cleared
by their consumers. Normal-array checks do not certify the SDK's resize
allocation-failure count behavior. OOM handling, unrelated algorithm hardening
and wrapper redesign remain out of scope.

There was no real 4D or Windows host execution, and this is not reproduction or
certification of the reported Windows Poppler crash. Both Actions workflows
remain manual-only. The Xcode project contains a signing/packaging shell phase,
so no project build, signing, notarization, packaging, release dispatch, tag or
binary publication is part of this validation.

## Manual source-version release workflow

Run **Bump version** manually on an explicitly selected branch, choosing `patch`,
`minor`, or `major`. It checks out the immutable dispatch `github.sha`, validates
source metadata, commits only the applicable source version literals, and pushes
one non-force branch update. It creates no tag, dispatches no build, and requires
a clean checkout and an unchanged remote branch. The mandatory executable
`.github/scripts/bump-hooks/pre-push` is checked initially and immediately before
push; its advertised old SHA must equal the selected SHA, its literal new SHA
must equal HEAD, and that commit must have exactly the selected SHA as its single
parent. Missing guards, branch advance/rewind/deletion, same-result races and
extra updates fail closed. Follow-tags is disabled even if enabled in Git config.

Run **Build** separately on the desired source commit (no inputs). It checks out
that exact `github.sha` in every job and derives `vX.Y.Z`,
`Common String Algorithm-X.Y.Z.zip` and `Common String Algorithm-X.Y.Z.dmg` from
validated source metadata. No default-branch-only restriction is imposed.
Publication uses one repository-wide concurrency group across branches, without
cancelling a running publication. Before native work, and again after all native,
signature verification, notarization acceptance and DMG stapling gates, it
requires both an absent remote tag and an absent draft/published release.
Authenticated release-list pages are validated through the last page; network,
authorization, 404, malformed responses and later-page errors are failures, not
evidence of availability.

Publication is create-only: POST a new tag ref at the selected SHA, verify that
exact remote SHA, POST a new public/non-prerelease release with the original empty
notes, then POST assets only to the newly returned release ID. There is no
reuse, update, delete, clobber, retry or rollback. **If publication stops, any tag,
release and earlier uploaded assets remain.** Do not rerun expecting to resume:
inspect the Actions error and the actual remote tag, release ID and asset state.
After deliberate human review, resolve partial state manually outside these
workflows, or bump to a new source version and start a new Build. These workflows
never perform destructive recovery.

### Source authority and preserved native settings

The original bump header explicitly selected `MARKETING_VERSION` when present,
with `CURRENT_PROJECT_VERSION` only a fallback for older unsplit projects; its
implementation did the same. Accordingly the three marketing settings are the
strict release authority, currently **1.0.6**. The three independent current
settings remain **1.0.0**. Unlike a coordinated-key project, independent valid
current metadata is validated separately and never incremented or normalized.

Xcode actually copies root `Info.plist` (`INFOPLIST_FILE`) and
`English.lproj/InfoPlist.strings` (Resources phase). Root `CFBundleVersion` last
changed from `2.0` to `2.1` in historical commit
`06fb934eebb03eeb48e4bc4b897771653d651d0f` (2019), alongside the old display
strings. The later explicit marketing-first workflow never coordinated that
build field. Its valid independent **2.1** remains unchanged; root
`CFBundleShortVersionString` remains absent. Only the two actual localized
release-display overrides are repaired from stale `2.1` to existing marketing
**1.0.6**, without a release increment. Copyright 2019, CR-only line endings,
the original lack of BOM, modes and unrelated bytes are preserved.

Future bumps update marketing and the localized display strings together, plus
an existing literal source short version if supplied. Supported variable
references and absent keys are preserved. Inconsistent/invalid versions,
duplicate quoted/unquoted assignments and duplicate plist keys are rejected.
Independent current/build metadata, prebuilt bundles, 4D data/schema, localization
revision counters, manifests, dependencies and native project settings are not
rewritten.

Windows retains Release/x64, the existing v143/Windows SDK 10.0 command-line
overrides and artifact merge. Its configured MSBuild `.4dbase` x64 output is now
cleared before compilation and consumed by exact path rather than recursively
finding a possibly committed prebuilt binary; canonical packaging remains under
`test/Plugins`. macOS retains the existing Default configuration, universal
arm64/x86_64 flags, workflow deployment target 11.0, frameworks/resources,
signing, verification, ZIP/DMG, notarization, stapling and all six secret names.
Both notary responses must explicitly report `Accepted` (a successful tool exit
alone is insufficient). No native build, signing, notarization or 4D execution
was performed as part of this migration; hosted native toolchain compatibility
is not established by source/lifecycle checks.

Helpers/tests adapt immutable prior art: proxy
`4dc9995e5523f86f4d6d4d111f89ad3f81d8fb87`, mapm
`739178b4b8629bb03fc716fd0872355c1b758666`, apple-speech-recognizer
`7b06cdc0657547234d67e7bb1a5756881cd2b353`, mail-applescript
`6c8c10ecb82618b60acb3ff1ae6df3f2cf824a6f` (duplicate-assignment checks),
and jsmin `fb9087a70130bce570c1cf2c687e09ee931ae3e8`
(explicit marketing-first/separate-build contract). Native settings are this
project's own, not copied from those projects.

Local source/lifecycle checks (no native execution):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/tests -v
actionlint .github/workflows/*.yml
sh -n .github/scripts/bump-hooks/pre-push
```

This plugin adds six native 4D commands for comparing pairs of strings: Dice's coefficient, Levenshtein distance, longest common subsequence, longest common substring, and Jaro/Jaro-Winkler similarity. Every command is a pure in-memory string computation — none of them touch the file system, network, or any OS-level graphics/permission API — and each takes exactly two `Text` parameters and returns a single `Real`, `Longint`, or `Text` result.

| Command | Returns | Purpose |
|---|---|---|
| [`Coefficient`](#coefficient) | Real | Dice's coefficient similarity ratio between two strings |
| [`Levenshtein`](#levenshtein) | Longint | Levenshtein edit distance between two strings |
| [`Longest common subsequence`](#longest-common-subsequence) | Text | Longest common subsequence shared by two strings |
| [`Longest common substring`](#longest-common-substring) | Text | Longest common contiguous substring shared by two strings |
| [`Jaro winkler`](#jaro-winkler) | Real | Jaro-Winkler similarity score between two strings |
| [`Jaro`](#jaro) | Real | Jaro similarity score between two strings |

**Platforms:** Carbon, Cocoa, Win32, Win64 (per the project's own README). The plugin has no OS-level API dependency, so behavior should be identical across all four — there's no platform-specific branch in the dispatch source to diverge in the first place.

---

## Requirements & platform notes

- **All parameters are mandatory.** Every command's manifest syntax (`(&T;&T)`) takes exactly two `Text` parameters — there's no optional/omittable parameter on any of these six commands.
- **No permissions or minimum OS version apply.** The commands don't call any OS graphics, file, or capture API, so there's nothing to grant or configure beyond having the plugin installed.
- **Thread-safety:** the plugin's manifest declares all six commands `threadSafe: true`, and the dispatch code holds no global/static state, so calling them from a preemptive process (as the plugin's own sample method does — see below) is safe at the dispatcher level. This can't be independently confirmed for the internals of each algorithm, since their implementation source wasn't available to check — if you're calling these heavily from concurrent preemptive processes and see inconsistent results, that's the first place to look.
- **Very long input strings may be slow.** Levenshtein distance and the LCS commands are commonly implemented with a comparison cost that grows with the product of the two input lengths. Whether that's the case for this specific build isn't confirmed against the actual algorithm source — treat it as a caution rather than a documented limit, and test with realistically-sized input if you're comparing long text (e.g. full paragraphs) rather than short fields.
- **Unexpected internal errors now return a safe default instead of hanging.** As of this write-up, each command always returns a value — `0`, `0.0`, or empty text, depending on its return type — even if the underlying computation hits an internal error on unusual input, rather than leaving the call unanswered. This is forward-looking: it's true once the plugin is rebuilt from the current source, not necessarily true of whatever compiled binary you already have installed.

---

## Coefficient

### Syntax
```
Coefficient ( text1 ; text2 ) -> Real
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Real | Dice's coefficient similarity ratio between `text1` and `text2`, from `0` (no similarity) to `1` (identical) |

### Description
Dice's coefficient measures similarity based on shared character bigrams between the two strings. The comparison is symmetric — swapping `text1` and `text2` gives the same result. Exact case-sensitivity and whitespace handling weren't verified against the algorithm's own source, so don't rely on a specific behavior there without testing it against your own data first.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$c1:=Coefficient("dictate"; "dictionary")  //0.4
$c2:=Coefficient("world"; "words")  //0.5
$c3:=Coefficient("mamal"; "small")  //0.5
```

A threshold check:
```4d
$similarity:=Coefficient($name1; $name2)
If ($similarity>=0.7)
   ALERT("Likely a match")
End if 
```

---

## Levenshtein

### Syntax
```
Levenshtein ( text1 ; text2 ) -> Longint
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Longint | Minimum number of single-character insertions, deletions, or substitutions needed to turn `text1` into `text2`; `0` means the strings are identical |

### Description
The edit distance is symmetric and always a non-negative integer. There's no upper bound enforced on input length — see the input-size caution under Requirements above if you're comparing long text.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$l1:=Levenshtein("kitten"; "sitting")  //3
$l2:=Levenshtein("rosettacode"; "raisethysword")  //8
```

Finding the closest match in a list:
```4d
$best:=Levenshtein($target; $list{1})
$bestIndex:=1
For ($i;2;Size of array($list))
   $d:=Levenshtein($target; $list{$i})
   If ($d<$best)
	  $best:=$d
	  $bestIndex:=$i
   End if 
End for 
```

---

## Longest common subsequence

### Syntax
```
Longest common subsequence ( text1 ; text2 ) -> Text
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Text | A longest common subsequence of `text1` and `text2` — characters need not be contiguous, but their relative order is preserved in both strings |

### Description
When more than one longest common subsequence of the same maximal length exists, which one is returned isn't confirmed against the algorithm's own source — treat the exact result as implementation-defined in that tie-breaking case, and rely only on its length being maximal.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$sq:=Longest common subsequence("XMJYAUZ"; "MZJAWXU")
```

---

## Longest common substring

### Syntax
```
Longest common substring ( text1 ; text2 ) -> Text
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Text | The longest contiguous run of characters common to both `text1` and `text2` |

### Description
As with the subsequence command above, if more than one substring of the same maximal length exists, which one is returned isn't confirmed against the algorithm's own source.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$ss:=Longest common substring("ABABC"; "BABCA")
```

---

## Jaro winkler

### Syntax
```
Jaro winkler ( text1 ; text2 ) -> Real
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Real | Jaro-Winkler similarity score, from `0` (no similarity) to `1` (identical); a variant of the Jaro score below that boosts strings sharing a common prefix |

### Description
Generally used for short strings like names, where a shared prefix is a strong signal of similarity. See [`Jaro`](#jaro) below for the unweighted score this builds on.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$jw1:=Jaro winkler("MARTHA"; "MARHTA")  //0.961
$jw2:=Jaro winkler("DWAYNE"; "DUANE")  //0.84
$jw3:=Jaro winkler("DIXON"; "DICKSONX")  //0.813
```

---

## Jaro

### Syntax
```
Jaro ( text1 ; text2 ) -> Real
```

| Parameter | Type | Description |
|---|---|---|
| `text1` | Text | First string to compare |
| `text2` | Text | Second string to compare |
| Result | Real | Jaro similarity score, from `0` (no similarity) to `1` (identical) |

### Description
The unweighted counterpart to [`Jaro winkler`](#jaro-winkler) above — it doesn't give extra weight to a shared prefix.

### Example
From the plugin's own test method (`Method1.4dm`):
```4d
$jr1:=Jaro("MARTHA"; "MARHTA")  //0.944
$jr2:=Jaro("DWAYNE"; "DUANE")  //0.822
$jr3:=Jaro("DIXON"; "DICKSONX")  //0.767
```

---

## Error handling & troubleshooting

- **All six commands require exactly two `Text` parameters** — there's no optional form. Passing the wrong parameter count or a non-Text value is a call-syntax error, not something these commands handle at runtime.
- **A call now always returns a value, even on an unexpected internal error** — `0` for `Coefficient`/`Jaro`/`Jaro winkler`, `0` for `Levenshtein`, or empty text for the two LCS commands — instead of leaving 4D waiting indefinitely. This is forward-looking: true once the plugin is rebuilt from the current source, not necessarily true of an already-installed binary built from an older version.
- **Very long strings can be slow to compare.** If you're comparing long text (documents, large notes fields) rather than short fields (names, codes, single words), test with realistic input sizes — the exact performance characteristics for large inputs weren't verified against the algorithm's own implementation.
- **Command names containing spaces** (`Longest common subsequence`, `Longest common substring`, `Jaro winkler`) are typed exactly as shown, spaces included — 4D command names are matched by the full name, not by omitting the spaces.

---

## Quick reference

```4d
$dice:=Coefficient("kitten"; "sitting")
$lev:=Levenshtein("kitten"; "sitting")
$lcs_seq:=Longest common subsequence("kitten"; "sitting")
$lcs_sub:=Longest common substring("kitten"; "sitting")
$jw:=Jaro winkler("kitten"; "sitting")
$jr:=Jaro("kitten"; "sitting")
```
