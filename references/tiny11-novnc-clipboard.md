# Bidirectional text clipboard in the Tiny11 browser views

The `/wechat` and `/wecom` display pages use the existing Windows clipboard
transport, not the limited clipboard channel in the raw VM console. They
remain loopback-only, same-origin, and protected by the existing input lease.

1. Open the relevant page and choose **Take control** when the GUI worker is
   not using the desktop.
2. Choose **Clipboard**. The current Windows text is shown in the dialog.
3. **Copy to this device** copies that text to the device running the browser.
   If Firefox is running inside Ubuntu, that means Ubuntu's clipboard.
4. **Paste from this device** loads client text into the dialog. Review it,
   then choose **Send to Windows clipboard**. Paste in the Windows app yourself.
5. **Reload Windows clipboard** explicitly replaces the dialog's current text
   with a fresh copy from Windows.

There is no automatic clipboard polling, typing, paste shortcut or message
submission. Opening the dialog does not overwrite the browser device's
clipboard. A failed send or loss of control preserves the draft, including
when the dialog is closed, control is reacquired, and the dialog is reopened.
Reloading the page itself is not durable draft storage.

## Phones and nested remote desktops

Browser clipboard permission and transport clipboard permission are different
boundaries. The Clipboard API generally requires a secure context and may
require a user gesture. Copy has its own button after the network read so an
iOS/Safari user gesture is not spent waiting for the Windows request.

When browser clipboard APIs are unavailable or permission is denied, the
dialog selects text for manual Copy and explains how to long-press Paste.
It does not repeatedly ask for permission. The layout was checked at a
390-pixel phone width. This is not a real iOS/Android device certification.

If the browser is inside Ubuntu reached through RDP, text must also cross
Ubuntu's RDP clipboard channel to reach the outer client. This page cannot
silently grant that permission or configure another RDP/VNC client. For
remote web access, use an authenticated loopback forward; do not relax the
server's Host/Origin/lease checks or expose the raw VM ports publicly.

The frontend change is a static file served without caching. Reload the page
to receive it. No VM restart, Windows app restart, desktop logout, or new
noVNC server is required. A reload releases the browser's current input lease.

## Isolated validation

With Node.js 22 and the existing Google Chrome installation on Linux:

```bash
node agentic_tools/wecom_agent/scripts/test_display_clipboard.mjs
```

The test uses a disposable headless browser and mock RFB/clipboard server.
It never connects to the real VM, reads an actual desktop clipboard or sends
a chat message. It checks view-only protection, CJK/emoji/quotes/multiline
text, explicit send, local-copy behavior, rejected sends, draft preservation
across control reconnects, permission fallback and mobile overflow. Test
artifacts are written to a printed temporary directory; the browser and
server stop, and the disposable browser profile is removed afterward.

Backend authentication, input-lease policy, and Windows transport behavior
are unchanged. Controller-side permission prompts and the outer RDP/VNC
clipboard still need verification in the user's actual connection chain.

Reference: [Browser Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API).
