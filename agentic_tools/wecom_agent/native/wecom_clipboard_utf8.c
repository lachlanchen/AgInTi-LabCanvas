#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_INPUT_BYTES (1024 * 1024)

static char *read_stdin(size_t *length) {
    size_t capacity = 4096;
    size_t used = 0;
    char *buffer = malloc(capacity + 1);
    if (buffer == NULL) {
        return NULL;
    }

    while (!feof(stdin)) {
        if (used == capacity) {
            size_t next = capacity * 2;
            if (next > MAX_INPUT_BYTES) {
                next = MAX_INPUT_BYTES;
            }
            if (next <= capacity) {
                free(buffer);
                return NULL;
            }
            char *resized = realloc(buffer, next + 1);
            if (resized == NULL) {
                free(buffer);
                return NULL;
            }
            buffer = resized;
            capacity = next;
        }
        size_t count = fread(buffer + used, 1, capacity - used, stdin);
        used += count;
        if (ferror(stdin)) {
            free(buffer);
            return NULL;
        }
    }
    buffer[used] = '\0';
    *length = used;
    return buffer;
}

static int read_clipboard(void) {
    int opened = 0;
    for (int attempt = 0; attempt < 50; ++attempt) {
        if (OpenClipboard(NULL)) {
            opened = 1;
            break;
        }
        Sleep(20);
    }
    if (!opened) {
        fprintf(stderr, "OpenClipboard failed\n");
        return 10;
    }

    HANDLE data = GetClipboardData(CF_UNICODETEXT);
    if (data == NULL) {
        CloseClipboard();
        fprintf(stderr, "CF_UNICODETEXT is unavailable\n");
        return 11;
    }
    const wchar_t *wide = GlobalLock(data);
    if (wide == NULL) {
        CloseClipboard();
        fprintf(stderr, "GlobalLock failed\n");
        return 12;
    }

    int wide_length = (int)wcslen(wide);
    int utf8_length = WideCharToMultiByte(
        CP_UTF8, WC_ERR_INVALID_CHARS, wide, wide_length, NULL, 0, NULL, NULL
    );
    if (wide_length > 0 && utf8_length <= 0) {
        GlobalUnlock(data);
        CloseClipboard();
        fprintf(stderr, "UTF-16 conversion failed\n");
        return 13;
    }
    char *utf8 = malloc((size_t)utf8_length + 1);
    if (utf8 == NULL) {
        GlobalUnlock(data);
        CloseClipboard();
        return 14;
    }
    if (utf8_length > 0 && WideCharToMultiByte(
            CP_UTF8, WC_ERR_INVALID_CHARS, wide, wide_length, utf8, utf8_length, NULL, NULL
        ) != utf8_length) {
        free(utf8);
        GlobalUnlock(data);
        CloseClipboard();
        fprintf(stderr, "UTF-16 conversion failed\n");
        return 15;
    }
    utf8[utf8_length] = '\0';
    GlobalUnlock(data);
    CloseClipboard();
    if (utf8_length > 0) {
        fwrite(utf8, 1, (size_t)utf8_length, stdout);
    }
    free(utf8);
    return 0;
}

int main(int argc, char **argv) {
    HWND console = GetConsoleWindow();
    if (console != NULL) {
        ShowWindow(console, SW_HIDE);
    }
    if (argc == 2 && strcmp(argv[1], "--read") == 0) {
        return read_clipboard();
    }
    if (argc != 1) {
        fprintf(stderr, "usage: wecom_clipboard_utf8.exe [--read]\n");
        return 1;
    }

    size_t input_length = 0;
    char *input = read_stdin(&input_length);
    if (input == NULL || input_length == 0) {
        free(input);
        fprintf(stderr, "expected UTF-8 text on stdin\n");
        return 2;
    }

    int wide_length = MultiByteToWideChar(
        CP_UTF8, MB_ERR_INVALID_CHARS, input, (int)input_length, NULL, 0
    );
    if (wide_length <= 0) {
        free(input);
        fprintf(stderr, "invalid UTF-8 input\n");
        return 3;
    }

    SIZE_T allocation_size = ((SIZE_T)wide_length + 1) * sizeof(wchar_t);
    HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, allocation_size);
    if (memory == NULL) {
        free(input);
        fprintf(stderr, "GlobalAlloc failed\n");
        return 4;
    }
    wchar_t *wide = GlobalLock(memory);
    if (wide == NULL) {
        free(input);
        GlobalFree(memory);
        fprintf(stderr, "GlobalLock failed\n");
        return 5;
    }
    if (MultiByteToWideChar(
            CP_UTF8, MB_ERR_INVALID_CHARS, input, (int)input_length, wide, wide_length
        ) != wide_length) {
        free(input);
        GlobalUnlock(memory);
        GlobalFree(memory);
        fprintf(stderr, "UTF-8 conversion failed\n");
        return 6;
    }
    wide[wide_length] = L'\0';
    free(input);
    GlobalUnlock(memory);

    int opened = 0;
    for (int attempt = 0; attempt < 50; ++attempt) {
        if (OpenClipboard(NULL)) {
            opened = 1;
            break;
        }
        Sleep(20);
    }
    if (!opened) {
        GlobalFree(memory);
        fprintf(stderr, "OpenClipboard failed\n");
        return 7;
    }
    if (!EmptyClipboard()) {
        CloseClipboard();
        GlobalFree(memory);
        fprintf(stderr, "EmptyClipboard failed\n");
        return 8;
    }
    if (SetClipboardData(CF_UNICODETEXT, memory) == NULL) {
        CloseClipboard();
        GlobalFree(memory);
        fprintf(stderr, "SetClipboardData failed\n");
        return 9;
    }
    CloseClipboard();
    return 0;
}
