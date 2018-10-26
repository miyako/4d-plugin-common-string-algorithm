//http://en.wikibooks.org/wiki/Algorithm_implementation/Strings/Longest_common_substring

#include "lcs.h"

#include <string>
#include <algorithm>
#include <vector>
#include <stdio.h>
#include <string.h>

using namespace std;

// See http://www-igm.univ-mlv.fr/~lecroq/seqcomp/node4.html.
class LCS
{
    class LCSTable
    {
        size_t   m_;
        size_t   n_;
        size_t*  data_;
    public:
        LCSTable(size_t m, size_t n)
        : m_(m)
        , n_(n)
        {
            data_ = new size_t[(m_ + 1) * (n_ + 1)];
        }
        ~LCSTable()
        {
            delete [] data_;
        }
		
        void setAt(size_t i, size_t j, size_t value)
        {
            data_[i + j * (m_ + 1)] = value;
        }
		
        size_t getAt(size_t i, size_t j) const
        {
            return data_[i + j * (m_ + 1)];
        }
		
        template<typename T> void
        build(const T* X, const T* Y)
        {
            for (size_t i=0; i<=m_; ++i)
                setAt(i, 0, 0);
			
            for (size_t j=0; j<=n_; ++j)
                setAt(0, j, 0);
			
            for (size_t i = 0; i < m_; ++i)
            {
                for (size_t j = 0; j < n_; ++j)
                {
                    if (X[i] == Y[j])
                        setAt(i+1, j+1, getAt(i, j)+1);
                    else
                        setAt(i+1, j+1, max(getAt(i+1, j), getAt(i, j+1)));
                }
            }
        }
    };
	
    template<typename T> static void
    backtrackOne(const LCSTable& table,
                 const T* X, const T* Y, size_t i, size_t j,
                 std::vector<T>& result)
    {
        if (i == 0 || j == 0)
            return;
        if (X[i - 1] == Y[j - 1])
        {
            backtrackOne(table, X, Y, i - 1, j - 1, result);
            result.push_back(X[i - 1]);
            return;
        }
        if (table.getAt(i, j - 1) > table.getAt(i -1, j))
            backtrackOne(table, X, Y, i, j - 1, result);
        else
            backtrackOne(table, X, Y, i - 1, j, result);
    }
	
public:
    template<typename T> static void
    findOne(T* X, size_t m, T* Y, size_t n,
            std::vector<T>& result)
    {
        LCSTable table(m, n);
        table.build(X, Y);
        backtrackOne(table, X, Y, m, n, result);
    }
};

void LongestCommonSubsequence(C_TEXT& Param1, C_TEXT& Param2, C_TEXT& returnValue)
{
	CUTF8String str1, str2;
	
	Param1.copyUTF8String(&str1);
	Param2.copyUTF8String(&str2);	
	
	std::vector<char> result;
	LCS::findOne(( char *)str1.c_str(), str1.size(), ( char *)str2.c_str(), str2.size(), result);
	returnValue.setUTF8String((const uint8_t *)&result.front(), result.size());
}	

int LongestCommonSubstring(C_TEXT& Param1, C_TEXT& Param2, C_TEXT& returnValue)
{
	CUTF8String str1, str2, str0;
	
	Param1.copyUTF8String(&str1);
	Param2.copyUTF8String(&str2);	
	
	if(str1.empty() || str2.empty())
	{
		return 0;
	}
	
	int *curr = new int [str2.size()];
	int *prev = new int [str2.size()];
#if VERSIONMAC
	int *swap = __null;		
#else
	int *swap = nullptr;
#endif	
	int maxSubstr = 0;
	int lastSubsBegin = 0;
	
	for(unsigned int i = 0; i<str1.size(); ++i)
	{
		for(unsigned int j = 0; j<str2.size(); ++j)
		{
			if(str1[i] != str2[j])
			{
				curr[j] = 0;
			}
			else
			{
				if(i == 0 || j == 0)
				{
					curr[j] = 1;
				}
				else
				{
					curr[j] = 1 + prev[j-1];
				}
				//The next if can be replaced with:
				//maxSubstr = max(maxSubstr, curr[j]);
				//(You need algorithm.h library for using max())
				if(maxSubstr < curr[j])
				{
					maxSubstr = curr[j];
					
					int thisSubsBegin = i - curr[j] + 1;
					
					if (lastSubsBegin != thisSubsBegin)
					{
						lastSubsBegin = thisSubsBegin;
					}

				}
			}
		}
		swap=curr;
		curr=prev;
		prev=swap;
	}
	delete [] curr;
	delete [] prev;
	
	str0.assign(str1.substr(lastSubsBegin, maxSubstr));
	returnValue.setUTF8String((const uint8_t *)str0.c_str(), str0.size());
	
	return maxSubstr;
}