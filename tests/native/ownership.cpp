#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace {

void require(bool condition, const char* message)
{
    if (!condition) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

bool allocatedEmpty = true;
bool failCommand = false;
bool replacePicture = true;
std::map<PA_Unichar*, size_t> strings;
std::map<PA_Handle, size_t> handles;
struct Picture {
    size_t refs;
    std::vector<uint8_t> bytes;
};
std::map<PA_Picture, Picture> pictures;
CUTF16String expectedPath;
CUTF16String expectedType;

PA_Unistring makeString(const PA_Unichar* content)
{
    PA_Unistring value = {};
    if (content)
        while (content[value.fLength]) ++value.fLength;
    if (value.fLength || allocatedEmpty) {
        const size_t count = value.fLength + 1;
        value.fString = new PA_Unichar[count];
        if (value.fLength)
            std::memcpy(value.fString, content, value.fLength * sizeof(PA_Unichar));
        value.fString[value.fLength] = 0;
        PA_Unichar* pointer = value.fString;
        require(strings.emplace(pointer, count).second, "duplicate string allocation");
    }
    return value;
}

void disposeString(PA_Unistring value)
{
    if (!value.fString) {
        require(value.fLength == 0, "null nonempty string");
        return;
    }
    PA_Unichar* pointer = value.fString;
    require(strings.erase(pointer) == 1, "double disposal of string");
    delete[] value.fString;
}

void expectString(PA_Unistring value, const CUTF16String& expected)
{
    require(value.fLength == expected.size(), "wrong UTF-16 code-unit count");
    if (!value.fString) {
        require(expected.empty(), "missing text buffer");
        return;
    }
    PA_Unichar* pointer = value.fString;
    auto allocation = strings.find(pointer);
    require(allocation != strings.end(), "read of disposed string");
    require(allocation->second >= expected.size() + 1, "insufficient string capacity");
    require(std::memcmp(value.fString, expected.c_str(),
                        expected.size() * sizeof(PA_Unichar)) == 0, "wrong exact text");
    require(value.fString[expected.size()] == 0, "missing text terminator");
}

PA_Picture makePicture(const void* bytes, size_t size)
{
    PA_Picture value = new int(0);
    Picture picture = {1, {}};
    if (size) {
        require(bytes != nullptr, "null picture bytes");
        const uint8_t* start = static_cast<const uint8_t*>(bytes);
        picture.bytes.assign(start, start + size);
    }
    require(pictures.emplace(value, picture).second, "duplicate picture allocation");
    return value;
}

void disposePicture(PA_Picture value)
{
    if (!value) return;
    auto found = pictures.find(value);
    require(found != pictures.end() && found->second.refs, "double disposal of picture");
    if (--found->second.refs == 0) {
        pictures.erase(found);
        delete static_cast<int*>(value);
    }
}

void expectPicture(PA_Picture value)
{
    require(pictures.count(value) == 1 && pictures.at(value).refs > 0,
            "picture handoff did not survive owner cleanup");
}

void clear(PA_Variable* value)
{
    switch (value->fType) {
        case eVK_Unistring:
            disposeString(value->uValue.fString);
            break;
        case eVK_Picture:
            disposePicture(value->uValue.fPicture);
            break;
        case eVK_ArrayUnicode: {
            PA_Handle handle = value->uValue.fArray.fData;
            if (handle) {
                require(handles.count(handle) == 1, "unknown array handle");
                const size_t count = value->uValue.fArray.fNbElements + 1;
                require(handles.at(handle) >= count * sizeof(PA_Unistring),
                        "array count exceeds allocation");
                PA_Unistring* data = reinterpret_cast<PA_Unistring*>(*handle);
                for (size_t i = 0; i < count; ++i) disposeString(data[i]);
                handles.erase(handle);
                delete[] *handle;
                delete handle;
            }
            break;
        }
        case eVK_Undefined:
        case eVK_Longint:
        case eVK_Real:
            break;
        default:
            require(false, "unhandled clear kind");
    }
    std::memset(value, 0, sizeof(*value));
    value->fType = eVK_Undefined;
}

void handleManager(EngineBlock* block)
{
    block->fError = 0;
    if (block->fParam1 == 1) {
        require(block->fParam2 >= 0, "negative handle size");
        PA_Handle handle = new char*;
        *handle = new char[block->fParam2];
        const size_t size = block->fParam2;
        handles.emplace(handle, size);
        block->fHandle = handle;
        return;
    }
    PA_Handle handle = block->fHandle;
    require(handles.count(handle) == 1, "unknown handle");
    switch (block->fParam1) {
        case 2:
            handles.erase(handle);
            delete[] *handle;
            delete handle;
            break;
        case 3: {
            require(block->fParam2 >= 0, "negative resize");
            size_t size = block->fParam2;
            char* data = new char[size];
            std::memcpy(data, *handle, std::min(size, handles.at(handle)));
            delete[] *handle;
            *handle = data;
            handles[handle] = size;
            break;
        }
        case 4: block->fParam2 = handles.at(handle); break;
        case 5: block->fParam3 = reinterpret_cast<sLONG_PTR>(*handle); break;
        case 6: break;
        case 7: block->fParam2 = 0; break;
        case 8: break;
        default: require(false, "unhandled handle operation");
    }
}

void replace(PA_Variable* value)
{
    clear(value);
    const uint8_t bytes[] = {1, 2, 3, 4};
    PA_SetPictureVariable(value, makePicture(bytes, sizeof(bytes)));
}

void execute(EngineBlock* block)
{
    PA_Variable** args = static_cast<PA_Variable**>(block->fPtr1);
    PA_Variable* result = static_cast<PA_Variable*>(block->fPtr2);
    result->fType = eVK_Undefined; // These picture commands are procedures.
    block->fError = 0;
    switch (block->fParam1) {
        case 678:
            require(block->fParam2 == 2, "wrong READ PICTURE arguments");
            expectString(args[0]->uValue.fString, expectedPath);
            if (!failCommand) replace(args[1]);
            else block->fError = 1;
            break;
        case 1002:
            require(block->fParam2 == 2, "wrong CONVERT PICTURE arguments");
            expectString(args[1]->uValue.fString, expectedType);
            expectPicture(args[0]->uValue.fPicture);
            if (replacePicture) replace(args[0]);
            break;
        case 988:
            require(block->fParam2 == 2, "wrong TRANSFORM PICTURE arguments");
            expectPicture(args[0]->uValue.fPicture);
            require(args[1]->uValue.fLongint == 101, "wrong grayscale selector");
            if (replacePicture) replace(args[0]);
            break;
        case 457:
            require(block->fParam2 == 3, "wrong PICTURE PROPERTIES arguments");
            expectPicture(args[0]->uValue.fPicture);
            PA_SetLongintVariable(args[1], 17);
            PA_SetLongintVariable(args[2], 23);
            break;
        case 679:
            require(block->fParam2 == 4, "wrong CREATE THUMBNAIL arguments");
            expectPicture(args[0]->uValue.fPicture);
            require(args[2]->uValue.fLongint == 7 && args[3]->uValue.fLongint == 9,
                    "wrong thumbnail dimensions");
            replace(args[1]);
            break;
        default: require(false, "unhandled command");
    }
}

void engine(short selector, EngineBlock* block)
{
    switch (selector) {
        case EX_HANDLE_MANAGER: handleManager(block); break;
        case EX_CREATE_UNISTRING:
            block->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(block->fHandle));
            break;
        case EX_DISPOSE_UNISTRING: disposeString(block->fUniString1); break;
        case EX_SET_UNISTRING: {
            // Read first: the content setter may be passed its own buffer.
            const PA_Unichar* input = reinterpret_cast<PA_Unichar*>(block->fHandle);
            CUTF16String copy = input ? CUTF16String(input) : CUTF16String();
            disposeString(block->fUniString1);
            block->fUniString1 = makeString(copy.c_str());
            break;
        }
        case EX_CREATE_PICTURE:
            block->fPicture = makePicture(block->fPtr1, block->fParam1);
            block->fError = 0;
            break;
        case EX_DISPOSE_PICTURE: disposePicture(block->fPicture); break;
        case EX_DUPLICATE_PICTURE: {
            PA_Picture picture = block->fPicture;
            expectPicture(picture);
            require(block->fParam1 == 0, "expected retainOnly engine operation");
            ++pictures.at(picture).refs;
            break;
        }
        case EX_GET_PICTURE_DATA:
            // No representations: do not invent ownership for successful SDK metadata.
            expectPicture(block->fPicture);
            block->fUniString1 = {};
            block->fError = 1;
            break;
        case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable*>(block->fPtr1)); break;
        case EX_EXECUTE_COMMAND_BY_ID: execute(block); break;
        case EX_CONVERT_CHARSET_TO_CHARSET: {
            require(block->fParam2 == eVTC_UTF_8 && block->fParam4 == eVTC_UTF_16,
                    "unexpected conversion charsets");
            CFStringRef input = CFStringCreateWithBytes(
                kCFAllocatorDefault, static_cast<const UInt8*>(block->fPtr1),
                block->fParam1, kCFStringEncodingUTF8, false);
            require(input != nullptr, "invalid conversion fixture");
            const size_t units = CFStringGetLength(input);
            const size_t bytes = units * sizeof(PA_Unichar);
            require(block->fParam3 >= bytes, "conversion capacity is in bytes");
            CFStringGetCharacters(input, CFRangeMake(0, units),
                                  static_cast<UniChar*>(block->fPtr2));
            // The converter returns BYTES, excluding any terminator. Do not write
            // one: the wrapper's zero-initialized extra capacity provides it.
            block->fParam3 = bytes;
            block->fError = 0;
            CFRelease(input);
            break;
        }
        default:
            std::fprintf(stderr, "unhandled engine selector %d\n", selector);
            std::exit(1);
    }
}

void balanced()
{
    require(strings.empty(), "unbalanced string allocations");
    require(handles.empty(), "unbalanced handles");
    require(pictures.empty(), "unbalanced picture references");
}

std::vector<CUTF16String> fixtures()
{
    return {
        CUTF16String(),
        CUTF16String({0x41, 0x53, 0x43, 0x49, 0x49}),
        CUTF16String({0x3042, 0x3044}),
        CUTF16String({0x41, 0xd83d, 0xde00, 0x42}),
    };
}

CUTF8String utf8(const CUTF16String& text)
{
    C_TEXT converted;
    converted.setUTF16String(text.c_str(), text.size());
    CUTF8String result;
    converted.copyUTF8String(&result);
    return result;
}

void testFile()
{
    auto texts = fixtures();
    std::rotate(texts.begin(), texts.begin() + 1, texts.end());
    for (const auto& text : texts) {
        expectedPath = text;
        CUTF8String path = utf8(text);
        for (bool failure : {false, true}) {
            failCommand = failure;
            {
                CPicture picture;
                picture.fromFileAtPath(&path);
                expectPicture(picture.getPicture());
                require(pictures.at(picture.getPicture()).refs == 1,
                        "file argument retained after wrapper took reference");
                require(strings.empty(), "path or initial empty string leaked");
            }
            balanced();
        }
    }
}

void testBytes()
{
    const uint8_t first[] = {7, 8, 9};
    {
        CPicture picture;
        picture.setBytes(first, sizeof(first));
        expectPicture(picture.getPicture());
        require(pictures.at(picture.getPicture()).bytes ==
                std::vector<uint8_t>(first, first + sizeof(first)), "wrong picture bytes");
        picture.setBytes(nullptr, 0);
        require(pictures.at(picture.getPicture()).bytes.empty(), "wrong empty picture");
    }
    balanced();
}

void testPicture(const std::string& kind)
{
    auto texts = fixtures();
    std::rotate(texts.begin(), texts.begin() + 1, texts.end());
    for (const auto& text : texts) {
        CUTF8String type = utf8(text);
        expectedType = text;
        for (bool replacement : {false, true}) {
            replacePicture = replacement;
            PA_Picture output = nullptr;
            {
                CPicture picture;
                if (kind == "copy") output = picture.createCopy(
                    reinterpret_cast<const char*>(type.c_str()));
                else if (kind == "gray") output = picture.createGrayScale();
                else if (kind == "thumbnail") output = picture.createThumbnail(7, 9);
                else {
                    unsigned int width = 0, height = 0;
                    picture.getSize(&width, &height);
                    require(width == 17 && height == 23, "wrong picture dimensions");
                }
                expectPicture(picture.getPicture());
            }
            if (output) {
                expectPicture(output);
                require(pictures.at(output).refs == 1, "wrong handoff reference count");
                PA_DisposePicture(output);
            }
            balanced();
        }
    }
}

void testArrays()
{
    auto texts = fixtures();
    PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_ResizeArray(&array, texts.size() - 1);
    for (size_t i = 0; i < texts.size(); ++i) {
        PA_Unistring owned = PA_CreateUnistring(
            const_cast<PA_Unichar*>(texts[i].c_str()));
        PA_SetStringInArray(array, i, &owned);
    }
    PA_Unistring borrowed = PA_GetStringInArray(array, 2);
    expectString(borrowed, texts[2]);
    C_TEXT independent;
    independent.setUTF16String(&borrowed);
    PA_Unistring copy = PA_CreateUnistring(
        const_cast<PA_Unichar*>(independent.getUTF16StringPtr()));
    require(copy.fString != borrowed.fString, "copy must have independent owner");
    PA_SetStringInArray(array, 1, &copy);
    PA_Unistring replacement = PA_CreateUnistring(
        const_cast<PA_Unichar*>(texts[3].c_str()));
    PA_SetStringInArray(array, 2, &replacement);
    expectString(PA_GetStringInArray(array, 1), texts[2]);
    expectString(PA_GetStringInArray(array, 2), texts[3]);
    for (size_t i = 0; i < 64; ++i) {
        PA_Unistring churn = PA_CreateUnistring(
            const_cast<PA_Unichar*>(texts[3].c_str()));
        PA_DisposeUnistring(&churn);
    }
    expectString(PA_GetStringInArray(array, 1), texts[2]);
    require(independent.getUTF16Length() == texts[2].size() &&
            CUTF16String(independent.getUTF16StringPtr()) == texts[2],
            "borrowed text copy did not survive owner mutation");

    PA_Unistring rejected = PA_CreateUnistring(
        const_cast<PA_Unichar*>(texts[1].c_str()));
    for (PA_long32 index : {-1, 100}) {
        PA_SetStringInArray(array, index, &rejected);
        expectString(rejected, texts[1]);
    }
    PA_Variable wrong = PA_CreateVariable(eVK_Longint);
    PA_SetStringInArray(wrong, 0, &rejected);
    expectString(rejected, texts[1]);
    PA_Variable noData = {};
    noData.fType = eVK_ArrayUnicode;
    PA_SetStringInArray(noData, 0, &rejected);
    expectString(rejected, texts[1]);
    PA_SetStringInArray(array, 1, nullptr);
    expectString(PA_GetStringInArray(array, 1), texts[2]);
    PA_DisposeUnistring(&rejected);

    // Independent synchronous scalar argument cleanup must not free array data.
    PA_Unistring scalar = PA_CreateUnistring(
        const_cast<PA_Unichar*>(texts[2].c_str()));
    PA_Variable argument = PA_CreateVariable(eVK_Undefined);
    PA_SetStringVariable(&argument, &scalar);
    PA_ClearVariable(&argument);
    expectString(PA_GetStringInArray(array, 1), texts[2]);

    ARRAY_TEXT wrapper;
    BytePtr parameters[] = {reinterpret_cast<BytePtr>(&array)};
    wrapper.fromParamAtIndex(parameters, 1);
    PA_ResizeArray(&array, 0);
    wrapper.toParamAtIndex(parameters, 1);
    expectString(PA_GetStringInArray(array, 1), texts[2]);
    expectString(PA_GetStringInArray(array, 2), texts[3]);
    PA_ResizeArray(&array, 1);
    PA_ClearVariable(&array);
    balanced();

    PA_Variable destination = PA_CreateVariable(eVK_Undefined);
    parameters[0] = reinterpret_cast<BytePtr>(&destination);
    wrapper.toParamAtIndex(parameters, 1);
    expectString(PA_GetStringInArray(destination, 1), texts[2]);
    PA_ClearVariable(&destination);
    balanced();
}

void testDispatch()
{
    for (const auto& text : fixtures()) {
        for (PA_long32 selector = 1; selector <= 6; ++selector) {
            PA_Unistring first = PA_CreateUnistring(const_cast<PA_Unichar*>(text.c_str()));
            PA_Unistring second = PA_CreateUnistring(const_cast<PA_Unichar*>(text.c_str()));
            BytePtr arguments[] = {
                reinterpret_cast<BytePtr>(&first), reinterpret_cast<BytePtr>(&second)};
            PA_Unistring output = PA_CreateUnistring(nullptr);
            PA_Unistring* outputPointer = &output;
            double number = -1;
            double* numberPointer = &number;
            sLONG_PTR integer = -1;
            sLONG_PTR* result = &integer;
            if (selector == 3 || selector == 4)
                result = reinterpret_cast<sLONG_PTR*>(&outputPointer);
            else if (selector != 2)
                result = reinterpret_cast<sLONG_PTR*>(&numberPointer);
            PluginBlock block = {arguments, result, nullptr};
            PluginMain(selector, &block);
            expectString(first, text);
            expectString(second, text);
            PA_DisposeUnistring(&first);
            PA_DisposeUnistring(&second);
            if (selector == 3 || selector == 4) expectString(output, text);
            else if (selector == 2)
                require(*reinterpret_cast<int*>(&integer) == 0, "wrong identical distance");
            else
                require(number == ((selector == 1 && text.empty()) ? 0.0 : 1.0),
                        "wrong identical coefficient");
            PA_DisposeUnistring(&output);
            balanced();
        }
    }
}

} // namespace

int main(int argc, char** argv)
{
    require(argc == 2, "expected named case");
    gCall4D = engine;
    const std::string kind = argv[1];
    for (bool empty : {false, true}) {
        allocatedEmpty = empty;
        if (kind == "file") testFile();
        else if (kind == "bytes") testBytes();
        else if (kind == "arrays") testArrays();
        else if (kind == "dispatch") testDispatch();
        else if (kind == "copy" || kind == "gray" || kind == "size" || kind == "thumbnail")
            testPicture(kind);
        else require(false, "unknown test");
    }
    balanced();
    std::puts("exact content and zero string/handle/picture balances (null + allocated empties)");
}
