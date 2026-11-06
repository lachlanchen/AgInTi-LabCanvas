# Recovering Chrome input after a stuck native file picker

## Symptom and confirmed cause

Chrome remained readable through CDP, but mouse clicks and keyboard input from
VNC did not reach the page. Even the native refresh button stopped responding.
No webpage modal or file-picker window was visible.

The desktop portal still held a file-selection request owned by the same Chrome
process. Closing its visible GTK window had not completed that request. Chromium
disables native event listening while a portal dialog is active and restores it
when the dialog is unparented. The observed request and successful recovery
support this diagnosis; an invisible website overlay was not the cause.

Implementation reference: [Chromium portal file dialog source](https://raw.githubusercontent.com/chromium/chromium/main/ui/shell_dialogs/select_file_dialog_linux_portal.cc),
particularly `DialogCreatedOnInvoker()` and `UnparentOnInvoker()`.

## Diagnose before restarting

1. Inspect visible webpage dialogs and native windows on the exact project
   display. Cancel only the relevant picker, not unrelated desktop services.
2. Check the VNC server's input mode and client sockets. A moving pointer alone
   does not prove Chrome accepts clicks or typing.
3. Test native input separately from CDP. Send a VNC click to a harmless temporary
   input, type a short marker, and read its value through CDP. Remove the input
   afterward. Never test by changing credentials or submitting an order.
4. If native input is blocked but CDP works, inspect only the relevant desktop
   portal request and resolve its D-Bus sender to the Chrome PID. Avoid unbounded
   enumeration of the shared workstation's portal requests.

## Minimal recovery

If a cancelled picker remains pending, use the same browser context to create a
replacement tab at a previously observed, read-only URL. Wait for that page to
load, then close only the stuck tab and bring the replacement forward. This
released the portal request and restored input without restarting Chrome or
changing its profile, login, or submitted order.

Do not close a tab containing unsaved work without first preserving it. Do not
resubmit an order to recover browser input. A D-Bus request cancellation from a
different sender can be denied; respect that boundary rather than patching or
killing the shared portal service.

## Viewer defaults and verification

New shared-launcher desktops now use one interactive viewer:

```text
x11vnc ... -localhost -nopw -forever -nevershared ...
vnc.html?...&autoconnect=1&resize=scale&view_only=0&shared=0&reconnect=0
```

This prevents stale viewers from repeatedly reconnecting and competing for
input. It is separate from the stuck portal fix. Existing stacks are not
automatically restarted or migrated by the launcher.

On the affected dedicated desktop, only its x11vnc relay was restarted; Xvfb,
Chrome and its profile were retained. Verification used actual RFB pointer and
keyboard events: clicking Chrome's refresh button changed `performance.timeOrigin`,
and typing into the temporary input produced the exact marker. The logged-in
order page remained accessible. Keep the active URL, PIDs and private evidence
in the ignored runtime handoff, never in public documentation.

## Separate website limitation

During the subsequent invoice check, the modern invoice-management page worked,
but the older invoice-information link led to an `index.php?route=account/login`
page. Returning from that legacy route showed the modern site as signed out.
Do not confuse this later website authentication problem with VNC input failure,
or report login preservation after that redirect. Use the modern sign-in dialog
and avoid the legacy invoice-information route. The submitted order remains
unchanged; invoice eligibility and payment must be checked independently.
