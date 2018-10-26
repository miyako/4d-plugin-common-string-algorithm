//http://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Dice%27s_coefficient

#include "dice.h"

#include <set>
#include <string>

using namespace std;

/*
 * dice coefficient = bigram overlap * 2 / bigrams in a + bigrams in b
 * (C) 2007 Francis Tyers 
 * Modifications made by Stefan Koshiw 2010
 * Now it outputs values [0..1]
 * Released under the terms of the GNU GPL.
 */

float dice_coefficient(C_TEXT& Param1, C_TEXT& Param2)
{
	
	CUTF16String string1;
	CUTF16String string2;
	
	Param1.copyUTF16String(&string1);
	Param2.copyUTF16String(&string2);
	
	set<CUTF16String> string1_bigrams;
	set<CUTF16String> string2_bigrams;
	
	//base case
	if(string1.length() == 0 || string2.length() == 0)
	{
		return 0;
	}        
	
	for(unsigned int i = 0; i < (string1.length() - 1); i++) {      // extract character bigrams from string1
		string1_bigrams.insert(string1.substr(i, 2));
	}
	for(unsigned int i = 0; i < (string2.length() - 1); i++) {      // extract character bigrams from string2
		string2_bigrams.insert(string2.substr(i, 2));
	}
	
	int intersection = 0;
	
	// find the intersection between the two sets
	
	for(set<CUTF16String>::iterator IT = string2_bigrams.begin(); 
		IT != string2_bigrams.end(); 
		IT++)
	{    
		intersection += string1_bigrams.count((*IT));
	}
	
	// calculate dice coefficient
	int total = string1_bigrams.size() + string2_bigrams.size();
	float dice = (float)(intersection * 2) / (float)total;
	
	return dice;
}