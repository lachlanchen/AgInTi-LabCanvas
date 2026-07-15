#!/usr/bin/env bash
set -euo pipefail

tool="${1:-}"
root="${LABCANVAS_SOCIAL_TOOLS_HOME:-$HOME/.local/share/labcanvas/social-tools}"
bin_dir="$HOME/.local/bin"

mkdir -p "$root" "$bin_dir"

case "$tool" in
  postiz)
    command -v npm >/dev/null 2>&1 || { echo "npm is required" >&2; exit 1; }
    mkdir -p "$root/postiz"
    npm install --prefix "$root/postiz" postiz
    ln -sfn "$root/postiz/node_modules/.bin/postiz" "$bin_dir/postiz"
    "$bin_dir/postiz" --version || "$bin_dir/postiz" --help >/dev/null
    printf 'Installed Postiz CLI at %s\n' "$bin_dir/postiz"
    ;;
  xmcp)
    command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
    command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
    if [[ -d "$root/xmcp/.git" ]]; then
      git -C "$root/xmcp" pull --ff-only
    else
      git clone https://github.com/xdevplatform/xmcp.git "$root/xmcp"
    fi
    python3 -m venv "$root/xmcp/.venv"
    "$root/xmcp/.venv/bin/pip" install -r "$root/xmcp/requirements.txt"
    printf '%s\n' \
      '#!/usr/bin/env bash' \
      'set -euo pipefail' \
      "exec \"$root/xmcp/.venv/bin/python\" \"$root/xmcp/server.py\" \"\$@\"" \
      >"$bin_dir/xmcp-server"
    chmod +x "$bin_dir/xmcp-server"
    printf 'Installed official X MCP launcher at %s\n' "$bin_dir/xmcp-server"
    ;;
  *)
    echo "usage: $0 postiz|xmcp" >&2
    exit 2
    ;;
esac
