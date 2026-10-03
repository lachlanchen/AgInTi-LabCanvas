# Windows WeChat Launch Task Recovery

## Incident and Evidence

The existing KVM and authenticated helper were reachable, but personal Windows
WeChat had no running client or visible window. WeCom remained present and its
automation stayed paused.

The owned `LabCanvas-Start-Weixin-Once` task had the default `PT72H` execution
limit. Its last run was September 30 at 19:48:29 HKT; the corresponding deadline
was October 3 at 19:48:29. It reported `0x41306` (task terminated). These facts
strongly support a scheduler timeout rather than an application crash. No
matching termination event was available to prove the precise termination path.
Do not attribute this incident to a Tencent security check without evidence.

The limit was changed to `PT0S`, keeping the existing action, principal,
triggers, profile, account, and other settings. The absent client was launched
through its existing interactive task, not through SSH session zero. A Tencent
updater elevation prompt was declined. A subsequent normal launch displayed
the remembered-account entry; using that entry restored the account without a
QR, reinstall, update, data removal, or phone input. The client version remained
4.1.15.9.

The declined updater's exact orphaned process was closed after verifying its
known executable path and that its old launch parent no longer existed. Native
WeChat and WeCom process IDs were unchanged by that cleanup.

## Reusable Commands

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py audit-client-launch
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py start-client
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py status
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py sync
```

`audit-client-launch` stages and verifies the read-only audit script; it neither
starts a client nor changes the task. `start-client` is an explicit operator
action: it repairs the owned task limit and starts it only when no personal
WeChat process exists. It does not restart an existing client, enter a login,
approve an updater, restart the helper/VM, switch accounts, or invoke Android.
A successful task operation is not proof of authentication: inspect the
separate helper `client_state` and `input_ready` fields.

`Repair-WeChatLaunchTask.ps1` checks the expected computer, exact known action,
interactive principal, installed executable, and valid Tencent signature.
Before changing the task, it exports its XML under the guest's private
`C:\LabCanvas\Recovery\wechat-launch-task` directory. Unexpected state fails
closed. Do not reintroduce the default three-day limit when provisioning this
long-lived client task. No automatic client-restart loop was added.

## Window Fitting

The old placement selector accepted only generic window titles such as Weixin.
The logged-in main window used the account's display name, so it was missed.
The revised selector accepts one unowned, maximizable native main window,
independently of account name. Owned menus, search popups, ambiguous main-window
sets, and auxiliary Channels surfaces are not repositioned.

The guard also queries the native primary working area each tick and compares
its bounds to the last placement. It places new windows or responds to changed
work areas without moving an unchanged window every three seconds. Invalid
layouts are not acted on. This prevents stale dimensions on future resolution
changes; no VM resolution change was needed for this recovery.

Only the owned `LabCanvas-App-Screens` helper was refreshed. Native WeChat and
WeCom process IDs were unchanged during deployment. The current main WeChat
rectangle is `(1284, 0, 1276, 1392)` inside the 2560x1440 desktop. Image previews
can be scaled: do not mistake their display size for the native framebuffer.

## Verification and Boundaries

- Helper reports `client_state=ready`, `input_ready=true`, no input blocker.
- Cached-key database sync succeeds without probing process-memory keys.
- Exact-title navigation to EchoMind passes with `sent=false`.
- Repeating `start-client` reports `started=false` for the existing client.
- Placement task is running after PowerShell parsing and native C# compilation.
- Focused unit suite: 120 tests, 6 optional view-dependency skips. All 18 view
  tests also pass in the existing view-service environment.
- Full `npm test`: 2,271 tests passed, with 16 optional-dependency skips.

The sync still exports five of seven configured message tables, with no missing
contact binding. That pre-existing coverage limitation is not resolved by a
client launch and is not evidence that every chat/task/schedule works.

Console: <http://127.0.0.1:6143/>. Reuse the current VM, helper and noVNC stack.
Guest task backups and screenshots remain ignored private runtime evidence.
WeCom remains paused; the Android mirror and unrelated maintenance are untouched.
