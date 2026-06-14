#!/usr/bin/env bash
set -euo pipefail

CANDIDATE="${1:-nineman}"
ROOT="${LABVIEW_MCP_CANDIDATE_ROOT:-$HOME/.local/share/labview-mcp-agent/candidates}"

case "$CANDIDATE" in
  nineman|Labview_mcp)
    REPO="https://github.com/nineman-YU/Labview_mcp.git"
    DEST="$ROOT/nineman-YU--Labview_mcp"
    ;;
  calmyjane|labview_assistant)
    REPO="https://github.com/CalmyJane/labview_assistant.git"
    DEST="$ROOT/CalmyJane--labview_assistant"
    ;;
  jangoebel)
    REPO="https://github.com/JanGoebel/labview_assistant.git"
    DEST="$ROOT/JanGoebel--labview_assistant"
    ;;
  *)
    echo "Unknown candidate: $CANDIDATE" >&2
    echo "Use one of: nineman, calmyjane, jangoebel" >&2
    exit 2
    ;;
esac

mkdir -p "$ROOT"

if [[ -d "$DEST/.git" ]]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning $REPO to $DEST"
  git clone "$REPO" "$DEST"
fi

cat <<EOF
Candidate ready:
  $DEST

Next steps:
  1. Install and activate LabVIEW.
  2. Open the LabVIEW project from this candidate.
  3. Run its server VI.
  4. Connect through the MCP config in agentic_tools/labview_mcp_agent/mcp.example.json.
EOF
