//%attributes = {"preemptive":"capable"}
//http://www.perlmonks.org/?node_id=680166

$c1:=Coefficient("dictate"; "dictionary")  //0.4
$c2:=Coefficient("world"; "words")  //0.5
$c3:=Coefficient("mamal"; "small")  //0.5

//http://rosettacode.org/wiki/Levenshtein_distance

$l1:=Levenshtein("kitten"; "sitting")  //3
$l2:=Levenshtein("rosettacode"; "raisethysword")  //8

$ss:=Longest common substring("ABABC"; "BABCA")
$sq:=Longest common subsequence("XMJYAUZ"; "MZJAWXU")

$jr1:=Jaro("MARTHA"; "MARHTA")  //0.944
$jw1:=Jaro winkler("MARTHA"; "MARHTA")  //0.961

$jr2:=Jaro("DWAYNE"; "DUANE")  //0.822
$jw2:=Jaro winkler("DWAYNE"; "DUANE")  //0.84

$jr3:=Jaro("DIXON"; "DICKSONX")  //0.767
$jw3:=Jaro winkler("DIXON"; "DICKSONX")  //0.813
