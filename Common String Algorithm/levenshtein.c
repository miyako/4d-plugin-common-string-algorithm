//http://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#C.2B.2B

#include "levenshtein.h"

#include <string>
#include <vector>
#include <algorithm>

using namespace std;

typedef vector< vector<unsigned int> > Tmatrix;

int levenshtein(C_TEXT& Param1, C_TEXT& Param2)
{
	CUTF8String str1, str2, str0;
	
	Param1.copyUTF8String(&str1);
	Param2.copyUTF8String(&str2);
	
	const size_t len1 = str1.size(), len2 = str2.size();
	
	vector<unsigned int> col(len2+1), prevCol(len2+1);
	
	for (unsigned int i = 0; i < prevCol.size(); i++)
		prevCol[i] = i;
	for (unsigned int i = 0; i < len1; i++) {
		col[0] = i+1;
		for (unsigned int j = 0; j < len2; j++)
			col[j+1] = min( min( 1 + col[j], 1 + prevCol[1 + j]),
						   prevCol[j] + (str1[i]==str2[j] ? 0 : 1) );
		col.swap(prevCol);
	}
	
	return prevCol[len2];		
}