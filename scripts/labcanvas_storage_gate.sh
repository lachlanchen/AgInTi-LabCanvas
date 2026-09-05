#!/usr/bin/env bash
# Optional installed host-side gate, before private config, queues, or log writes.
labcanvas_storage_ready() {
  local guard="${LABCANVAS_STORAGE_GUARD:-$HOME/.local/lib/labcanvas/storage_guard.py}"
  local config="${LABCANVAS_STORAGE_CONFIG:-$HOME/.config/labcanvas/storage-guard.json}"
  [[ -f "$config" ]] || return 0
  /usr/bin/python3 "$guard" --config "$config" --root "$ROOT" check >/dev/null
}
