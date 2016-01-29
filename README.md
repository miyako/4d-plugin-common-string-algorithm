4d-plugin-common-string-algorithm
=================================

Suite of classic hash functions: Dice's coefficient, Levenshtein distance, LCS and Jaro Winkler.

##Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|🆗|🚫|🆗|🆗|

Commands
---

```c
// --- Dice's coefficient
void Coefficient(sLONG_PTR *pResult, PackagePtr pParams);

// --- Levenshtein distance
void Levenshtein(sLONG_PTR *pResult, PackagePtr pParams);

// --- LCS
void Longest_common_subsequence(sLONG_PTR *pResult, PackagePtr pParams);
void Longest_common_substring(sLONG_PTR *pResult, PackagePtr pParams);

// --- Jaro Winkler
void Jaro_winkler(sLONG_PTR *pResult, PackagePtr pParams);
void Jaro(sLONG_PTR *pResult, PackagePtr pParams);
```
