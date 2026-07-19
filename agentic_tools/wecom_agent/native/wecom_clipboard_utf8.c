#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_INPUT_BYTES (1024 * 1024)

static int open_clipboard_retry(void) {
    for (int attempt = 0; attempt < 50; ++attempt) {
        if (OpenClipboard(NULL)) {
            return 1;
        }
        Sleep(20);
    }
    return 0;
}

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
    if (!open_clipboard_retry()) {
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

static int write_file_clipboard(const char *input, size_t input_length) {
    int source_length = MultiByteToWideChar(
        CP_UTF8, MB_ERR_INVALID_CHARS, input, (int)input_length, NULL, 0
    );
    if (source_length <= 0) {
        fprintf(stderr, "invalid UTF-8 file list\n");
        return 20;
    }
    wchar_t *source = calloc((size_t)source_length + 1, sizeof(wchar_t));
    if (source == NULL || MultiByteToWideChar(
            CP_UTF8, MB_ERR_INVALID_CHARS, input, (int)input_length, source, source_length
        ) != source_length) {
        free(source);
        fprintf(stderr, "file-list conversion failed\n");
        return 21;
    }

    SIZE_T allocation_size = sizeof(DROPFILES) + ((SIZE_T)source_length + 2) * sizeof(wchar_t);
    HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, allocation_size);
    if (memory == NULL) {
        free(source);
        fprintf(stderr, "GlobalAlloc failed\n");
        return 22;
    }
    DROPFILES *drop = GlobalLock(memory);
    if (drop == NULL) {
        free(source);
        GlobalFree(memory);
        fprintf(stderr, "GlobalLock failed\n");
        return 23;
    }
    drop->pFiles = sizeof(DROPFILES);
    drop->fWide = TRUE;
    wchar_t *files = (wchar_t *)((BYTE *)drop + sizeof(DROPFILES));
    size_t used = 0;
    int file_count = 0;
    int in_file = 0;
    for (int index = 0; index < source_length; ++index) {
        wchar_t value = source[index];
        if (value == L'\r') {
            continue;
        }
        if (value == L'\n') {
            if (in_file) {
                files[used++] = L'\0';
                ++file_count;
                in_file = 0;
            }
            continue;
        }
        files[used++] = value;
        in_file = 1;
    }
    if (in_file) {
        files[used++] = L'\0';
        ++file_count;
    }
    files[used] = L'\0';
    free(source);
    GlobalUnlock(memory);
    if (file_count == 0) {
        GlobalFree(memory);
        fprintf(stderr, "expected at least one file path\n");
        return 24;
    }
    if (!open_clipboard_retry()) {
        GlobalFree(memory);
        fprintf(stderr, "OpenClipboard failed\n");
        return 25;
    }
    if (!EmptyClipboard() || SetClipboardData(CF_HDROP, memory) == NULL) {
        CloseClipboard();
        GlobalFree(memory);
        fprintf(stderr, "SetClipboardData(CF_HDROP) failed\n");
        return 26;
    }
    CloseClipboard();
    return 0;
}

static int read_file_clipboard(void) {
    if (!open_clipboard_retry()) {
        fprintf(stderr, "OpenClipboard failed\n");
        return 30;
    }
    HDROP drop = (HDROP)GetClipboardData(CF_HDROP);
    if (drop == NULL) {
        CloseClipboard();
        fprintf(stderr, "CF_HDROP is unavailable\n");
        return 31;
    }
    UINT count = DragQueryFileW(drop, 0xFFFFFFFF, NULL, 0);
    for (UINT index = 0; index < count; ++index) {
        UINT length = DragQueryFileW(drop, index, NULL, 0);
        wchar_t *wide = calloc((size_t)length + 1, sizeof(wchar_t));
        if (wide == NULL || DragQueryFileW(drop, index, wide, length + 1) != length) {
            free(wide);
            CloseClipboard();
            return 32;
        }
        int utf8_length = WideCharToMultiByte(CP_UTF8, 0, wide, (int)length, NULL, 0, NULL, NULL);
        char *utf8 = malloc((size_t)utf8_length + 1);
        if (utf8 == NULL || WideCharToMultiByte(
                CP_UTF8, 0, wide, (int)length, utf8, utf8_length, NULL, NULL
            ) != utf8_length) {
            free(utf8);
            free(wide);
            CloseClipboard();
            return 33;
        }
        utf8[utf8_length] = '\0';
        fwrite(utf8, 1, (size_t)utf8_length, stdout);
        fputc('\n', stdout);
        free(utf8);
        free(wide);
    }
    CloseClipboard();
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
    if (argc == 2 && strcmp(argv[1], "--read-files") == 0) {
        return read_file_clipboard();
    }
    if (argc != 1 && !(argc == 2 && strcmp(argv[1], "--files") == 0)) {
        fprintf(stderr, "usage: wecom_clipboard_utf8.exe [--read|--files|--read-files]\n");
        return 1;
    }

    size_t input_length = 0;
    char *input = read_stdin(&input_length);
    if (input == NULL || input_length == 0) {
        free(input);
        fprintf(stderr, "expected UTF-8 text on stdin\n");
        return 2;
    }
    if (argc == 2) {
        int result = write_file_clipboard(input, input_length);
        free(input);
        return result;
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

    if (!open_clipboard_retry()) {
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
