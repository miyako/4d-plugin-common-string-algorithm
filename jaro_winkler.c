//http://people.rit.edu/rmb5229/320/project3/media/source/jaro_winkler.c

#include "jaro_winkler.h"

#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#define TRUE    1
#define FALSE   0

#define max(a, b) ((a) > (b) ? (a) : (b))
#define min(a, b) ((a) < (b) ? (a) : (b))
// tolower() requires its argument be representable as unsigned char or EOF.
// A plain char with the high bit set (any UTF-8 continuation byte - i.e. any
// accented/non-ASCII character, which is ordinary input for a 4D Text field)
// is negative on a platform where char is signed, and passing a negative
// value other than EOF to tolower() is undefined behavior. Casting through
// unsigned char first avoids that; it doesn't make multi-byte UTF-8
// comparison "correct" in a linguistic sense (see the byte-vs-character
// comparison caveat noted separately) but it removes the UB.
#define equal(a, b) (tolower((unsigned char)(a)) == tolower((unsigned char)(b)))
#define not_equal(a, b) (tolower((unsigned char)(a)) != tolower((unsigned char)(b)))

double _jaro(const char *str1, const char *str2) {
    // length of the strings, stops the repeated use of strlen
    int str1_len = strlen(str1);
    int str2_len = strlen(str2);
	
    // if both strings are empty return 1
    // if only one of the strings is empty return 0
    if (str1_len == 0) return str2_len == 0 ? 1.0 : 0.0;
	
    // max distance between two chars to be considered matching
    // floor() is ommitted due to integer division rules
    int match_distance = (int) max(str1_len, str2_len)/2 - 1;
	
    // arrays of bools that signify if that char in the matcing string has a match
    int *str1_matches = (int *)calloc(str1_len, sizeof(int));
    int *str2_matches = (int *)calloc(str2_len, sizeof(int));

    // calloc can return NULL (ordinary allocation failure, or str1_len/str2_len
    // having gone negative because strlen()'s size_t result overflowed the
    // int this function stores it in for a >2GB input) - both arrays are
    // dereferenced unconditionally below, so this must be checked before
    // proceeding rather than assumed to have succeeded.
    if (str1_matches == NULL || str2_matches == NULL) {
        free(str1_matches);
        free(str2_matches);
        return 0.0;
    }
	
    // number of matches and transpositions
    double matches = 0.0;
    double transpositions = 0.0;
	
    // find the matches
    for (int i = 0; i < str1_len; i++) {
        // start and end take into account the match distance
        int start = max(0, i - match_distance);
        int end = min(i + match_distance + 1, str2_len);
		
        // add comments...
        for (int k = start; k < end; k++) {
            // if str2 already has a match continue
            if (str2_matches[k]) continue;
            // if str1 and str2 are not
            if (not_equal(str1[i], str2[k])) continue;
            // otherwise assume there is a match
            str1_matches[i] = TRUE;
            str2_matches[k] = TRUE;
            matches++;
            break;
        }
    }
	
    // if there are no matches return 0
    if (matches == 0) {
        free(str1_matches);
        free(str2_matches);
        return 0.0;
    }
	
    // count transpositions
    int k = 0;
    for (int i = 0; i < str1_len; i++) {
        // if there are no matches in str1 continue
        if (!str1_matches[i]) continue;
        // while there is no match in str2 increment k
        while (!str2_matches[k]) k++;
        // increment transpositions
        if (not_equal(str1[i], str2[k])) transpositions++;
        k++;
    }
	
    // divide the number of transpositions by two as per the algorithm specs
    // this division is valid because the counted transpositions include both
    // instances of the transposed characters.
    transpositions /= 2.0;
	
    // free dat allocated memory !VERY IMPORTANT!
    free(str1_matches);
    free(str2_matches);
	
    // return the jaro distance
    return ((matches / str1_len) +
			(matches / str2_len) +
			((matches - transpositions) / matches)) / 3.0;
}

double _jaro_winkler(const char *str1, const char *str2) {
    // compute the jaro distance
    double dist = _jaro(str1, str2);
	
    // finds the number of common terms in the first 3 characters, max 3.
    //
    // Bounding the loop by min(len1, len2) up front, and indexing rather than
    // incrementing str1/str2 directly, fixes a 1-byte heap over-read that the
    // previous pointer-increment version had: when str1 and str2 are both
    // exactly 1 character, the first iteration matches the real character,
    // then the *next* iteration matched the two strings' null terminators
    // against each other (equal('\0','\0') is true) and advanced both
    // pointers one byte past each buffer's end - so the third loop check
    // dereferenced out-of-bounds memory before it could fail. Never comparing
    // past either string's actual length avoids that case entirely.
    int prefix_length = 0;
    int max_prefix = (int)min(strlen(str1), strlen(str2));
    if (max_prefix > 3) max_prefix = 3;
    while (prefix_length < max_prefix && equal(str1[prefix_length], str2[prefix_length]))
        prefix_length++;
	
    // 0.1 is the default scaling factor
    return dist + prefix_length * 0.1 * (1 - dist);
}

double jaro(C_TEXT& Param1, C_TEXT& Param2)
{
	CUTF8String str1, str2;
	
	Param1.copyUTF8String(&str1);
	Param2.copyUTF8String(&str2);	
	
	return _jaro((const char *)str1.c_str(),(const char *)str2.c_str());
}

double jaro_winkler(C_TEXT& Param1, C_TEXT& Param2)
{
	CUTF8String str1, str2;
	
	Param1.copyUTF8String(&str1);
	Param2.copyUTF8String(&str2);
	
	return _jaro_winkler((const char *)str1.c_str(),(const char *)str2.c_str());
}