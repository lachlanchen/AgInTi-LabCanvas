# Reuse the Official Baidu Desktop Client

For an owner-authorized supplier share, check the installed official client before asking for a separate browser login. A logged-out Chrome profile does not establish that the desktop client is logged out.

## Proven Route

The method was recovered read-only from the Jianshiyiliao download handoff, then independently verified on this motor-board share on 2026-11-16. No Jianshiyiliao data, running service, source file, or active session was changed.

1. Inspect `/opt/baidunetdisk/baidunetdisk`, its existing process, and localhost CDP port. Do not start a duplicate client. Check available memory and storage before a large transfer.
2. If the client is stopped, launch it with the existing user's normal profile on the already-owned CAD desktop. This run reused display `:148` and CDP `9498`; do not assume those ports are always free. Do not copy profiles or export account cookies.
3. For this older Electron client, connect with `chromium.connect_over_cdp(url, no_defaults=True)`. Without that option, Playwright attempts unsupported browser download-context management and reports `Browser.setDownloadBehavior: Browser context management is not supported`.
4. Use an owned, visible provider window inside the client, sharing its existing Electron session. Keep remote content sandboxed with `nodeIntegration=False`, `contextIsolation=True`, `enableRemoteModule=False`, and `sandbox=True`. A website may define an AMD `require`; that alone is not proof that Node integration is enabled.
5. Open only the exact supplied share and enter its extraction code through the normal flow. Genuine login, verification, expired-share, or access-limit failures still stop the operation; do not bypass them.
6. Verify the exact root folder title. Use its visible download control once. A share folder row may be a `dd` rather than `.list-view-item`; inspect the actual DOM. Match links by exact filename, not page indices or a breadcrumb with the same text.
7. Watch the native `正在下载` queue. Folder byte totals can rise during recursive enumeration; an early displayed total is not the final inventory. Do not retry the download merely because the queue appears after a short delay.
8. Require `下载完成` for the exact folder, no active partials, and a local per-file size/SHA-256 inventory. Keep executables as reference only; never run supplier installers or examples merely to inspect documentation. Inspect archives before extracting them.
9. Move only the newly completed requested download into its reference folder. Leave unrelated account files and completed-history rows alone. Do not move active `.downloading` files or change the app's global download directory.
10. Close the owned share window and normally quit only the client started for this task, after verifying no unrelated downloads or uploads are active. Preserve its profile. Keep the existing CAD Chrome/noVNC stack only if an owner review is still waiting.

## Verification For This Download

- Exact package: `008.B 42 57电机扩展板资料`.
- One normal native download action; no new login, account binding, purchase, or cloud save.
- Native completed row verified; 12 top-level folders, 44 completed files, 861928004 bytes.
- Reusable public evidence: `supplier-manifest.json` and the wiring guide.
- Private runtime evidence, extraction code and account-dependent state stay in ignored `local/` and `output/cad_sourcing/runtime/`, not Git or public documentation.
