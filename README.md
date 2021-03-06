4d-plugin-common-string-algorithm
=================================

Suite of classic hash functions: Dice's coefficient, Levenshtein distance, LCS and Jaro Winkler

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" /> <img src="https://user-images.githubusercontent.com/1725068/41266195-ddf767b2-6e30-11e8-9d6b-2adf6a9f57a5.png" width="32" height="32" />

![preemption xx](https://user-images.githubusercontent.com/1725068/41327179-4e839948-6efd-11e8-982b-a670d511e04f.png)

### Releases

[2.0](https://github.com/miyako/4d-plugin-common-string-algorithm/releases/tag/2.0)

```
value:=Coefficient (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|REAL|

```
value:=Levenshtein (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|LONGINT|

```
value:=Longest common subsequence (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|TEXT|

```
value:=Longest common substring (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|TEXT|

```
value:=Jaro (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|REAL|

```
value:=Jaro winkler (arg1; arg2)
```

Parameter|Type|Description
------------|------|----
arg1|TEXT|
arg2|TEXT|
value|REAL|

