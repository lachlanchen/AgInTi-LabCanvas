#define UNICODE
#define _UNICODE

#include <windows.h>
#include <stdio.h>
#include <string.h>

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

int main(int argc, char **argv) {
    HWND window;

    window = find_wecom();

    if (window == NULL) {
        fputs("WeCom top-level window not found\n", stderr);
        return 1;
    }
    ShowWindow(window, SW_RESTORE);
    SetForegroundWindow(window);
    Sleep(120);

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
    fputs("usage: wecom_win32_input --paste|--copy-all|--clear\n", stderr);
    return 2;
}
