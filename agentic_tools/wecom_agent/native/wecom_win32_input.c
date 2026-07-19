#define UNICODE
#define _UNICODE

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static void send_key(WORD key, DWORD flags) {
    INPUT input = {0};
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = key;
    input.ki.dwFlags = flags;
    if (SendInput(1, &input, sizeof(input)) != 1) {
        fputs("SendInput keyboard event failed\n", stderr);
        ExitProcess(2);
    }
    Sleep(45);
}

static void send_chord(WORD key) {
    send_key(VK_CONTROL, 0);
    send_key(key, 0);
    send_key(key, KEYEVENTF_KEYUP);
    send_key(VK_CONTROL, KEYEVENTF_KEYUP);
    Sleep(100);
}

static HWND find_wecom(void) {
    HWND window = FindWindowW(NULL, L"WeCom");
    if (window == NULL) {
        window = FindWindowW(L"WeWorkWindow", L"WeCom");
    }
    if (window == NULL) {
        window = FindWindowW(L"WeWorkWindow", L"\u4f01\u4e1a\u5fae\u4fe1");
    }
    return window;
}

typedef struct {
    DWORD process_id;
    int closed;
} modal_cleanup_context;

static BOOL CALLBACK close_stale_modal(HWND window, LPARAM parameter) {
    modal_cleanup_context *context = (modal_cleanup_context *)parameter;
    DWORD process_id = 0;
    WCHAR class_name[128] = {0};
    WCHAR title[256] = {0};
    BOOL is_picker;
    BOOL is_wedoc;
    BOOL is_reminder;
    BOOL is_search_result;
    BOOL is_start_group_chat;

    GetWindowThreadProcessId(window, &process_id);
    if (process_id != context->process_id) {
        return TRUE;
    }
    GetClassNameW(window, class_name, 127);
    GetWindowTextW(window, title, 255);
    is_picker = wcscmp(class_name, L"#32770") == 0 && (
        wcscmp(title, L"Select file/folder") == 0 ||
        wcscmp(title, L"Select file") == 0
    );
    is_wedoc = wcscmp(class_name, L"Tencent.WXWork.WedocHostWindow") == 0;
    is_reminder = wcscmp(class_name, L"WeWorkMessageBoxFrame") == 0 &&
        wcscmp(title, L"Reminder") == 0;
    is_search_result = wcscmp(title, L"SearchResultWindow2") == 0;
    is_start_group_chat = wcscmp(title, L"Start Group Chat") == 0;
    if (
        is_picker || is_wedoc || is_reminder || is_search_result ||
        is_start_group_chat
    ) {
        if (PostMessageW(window, WM_CLOSE, 0, 0)) {
            context->closed += 1;
        }
    }
    return TRUE;
}

static int close_stale_modals(void) {
    HWND main_window = find_wecom();
    DWORD process_id = 0;
    modal_cleanup_context context = {0};

    if (main_window == NULL) {
        return 0;
    }
    GetWindowThreadProcessId(main_window, &process_id);
    context.process_id = process_id;
    EnumWindows(close_stale_modal, (LPARAM)&context);
    /* Wine can report the wrapper HWND disabled while its layered content is
       interactive. Exact title/class matching above is the cleanup contract;
       later OCR/title verification remains the fail-closed readiness gate. */
    Sleep(context.closed > 0 ? 250 : 50);
    return 0;
}

static int send_click(const char *x_text, const char *y_text) {
    char *x_end = NULL;
    char *y_end = NULL;
    long x = strtol(x_text, &x_end, 10);
    long y = strtol(y_text, &y_end, 10);
    INPUT events[2] = {0};

    if (x_end == x_text || *x_end != '\0' || y_end == y_text || *y_end != '\0') {
        fputs("Invalid click coordinates\n", stderr);
        return 3;
    }
    if (!SetCursorPos((int)x, (int)y)) {
        fputs("SetCursorPos failed\n", stderr);
        return 3;
    }
    events[0].type = INPUT_MOUSE;
    events[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
    events[1].type = INPUT_MOUSE;
    events[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
    if (SendInput(2, events, sizeof(INPUT)) != 2) {
        fputs("SendInput mouse click failed\n", stderr);
        return 3;
    }
    Sleep(120);
    return 0;
}

int main(int argc, char **argv) {
    HWND window;

    if (
        argc == 2 && (
            strcmp(argv[1], "--close-stale-modals") == 0 ||
            strcmp(argv[1], "--close-stale-wedoc") == 0
        )
    ) {
        return close_stale_modals();
    }

    window = find_wecom();

    if (window == NULL) {
        fputs("WeCom top-level window not found\n", stderr);
        return 1;
    }
    ShowWindow(window, SW_RESTORE);
    SetForegroundWindow(window);
    Sleep(120);

    if (argc == 4 && strcmp(argv[1], "--click") == 0) {
        if (!IsWindowEnabled(window)) {
            fputs("WeCom top-level window is disabled\n", stderr);
            return 4;
        }
        return send_click(argv[2], argv[3]);
    }

    if (argc == 2 && strcmp(argv[1], "--paste") == 0) {
        send_chord('V');
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--copy-all") == 0) {
        send_chord('A');
        send_chord('C');
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--clear") == 0) {
        send_chord('A');
        send_key(VK_BACK, 0);
        send_key(VK_BACK, KEYEVENTF_KEYUP);
        return 0;
    }
    fputs(
        "usage: wecom_win32_input --paste|--copy-all|--clear|"
        "--click X Y|--close-stale-modals\n",
        stderr
    );
    return 2;
}
