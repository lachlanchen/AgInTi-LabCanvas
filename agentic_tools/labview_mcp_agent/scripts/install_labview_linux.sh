#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
SEARCH_DIR="${LABVIEW_INSTALLER_DIR:-$HOME/Downloads}"
WORK_DIR="${LABVIEW_INSTALL_WORK:-$HOME/.cache/labview-linux-install}"

usage() {
  cat <<'USAGE'
Usage: install_labview_linux.sh [--dry-run] [--search-dir DIR]

Installs Linux support packages and consumes a locally downloaded NI LabVIEW
Linux installer .zip or feed .deb. This script cannot download LabVIEW from NI,
because NI requires web login/license entitlement for the installer.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --search-dir) SEARCH_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '[dry-run] %q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

need_sudo() {
  if [[ "$EUID" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

echo "LabVIEW installer search dir: $SEARCH_DIR"
echo "Work dir: $WORK_DIR"

echo "Installing/checking Linux runtime prerequisites..."
run need_sudo apt-get update
run need_sudo apt-get install -y xvfb libopenal1 libncurses6 ca-certificates curl unzip

mkdir -p "$WORK_DIR"

mapfile -t archives < <(find "$SEARCH_DIR" -maxdepth 1 -type f \( \
  -iname '*labview*.zip' -o \
  -iname '*labview*.deb' -o \
  -iname 'ni-labview*.deb' \
\) | sort)

if [[ "${#archives[@]}" -eq 0 ]]; then
  cat <<EOF
No LabVIEW Linux installer archive was found.

Download LabVIEW for Linux from NI, then place the .zip or feed .deb in:
  $SEARCH_DIR

NI download page:
  https://www.ni.com/en/support/downloads/software-products/download.labview.html

Then rerun:
  $0 --search-dir "$SEARCH_DIR"
EOF
  exit 3
fi

echo "Found installer candidates:"
printf '  %s\n' "${archives[@]}"

for archive in "${archives[@]}"; do
  case "${archive,,}" in
    *.zip)
      echo "Extracting $archive"
      run unzip -n "$archive" -d "$WORK_DIR/$(basename "$archive" .zip)"
      ;;
    *.deb)
      echo "Using direct deb $archive"
      ;;
  esac
done

mapfile -t feed_debs < <(find "$SEARCH_DIR" "$WORK_DIR" -type f \( \
  -iname 'ni-labview*.deb' -o \
  -iname '*ubuntu*.deb' \
\) | sort)

if [[ "${#feed_debs[@]}" -eq 0 ]]; then
  echo "No NI feed .deb package found after extraction." >&2
  exit 4
fi

echo "Installing NI feed packages:"
printf '  %s\n' "${feed_debs[@]}"
for deb in "${feed_debs[@]}"; do
  run need_sudo dpkg -i "$deb" || true
done

run need_sudo apt-get update

echo "Candidate LabVIEW apt packages after feed install:"
apt-cache search '^ni-labview' | sed -n '1,80p' || true

mapfile -t packages < <(apt-cache search '^ni-labview' | awk '{print $1}' | grep -E '^ni-labview-[0-9].*-(community|pro|full|base)$|^ni-labview-[0-9].*$' | sort -Vr | sed -n '1,8p')

if [[ "${#packages[@]}" -eq 0 ]]; then
  echo "No installable ni-labview package was visible to apt." >&2
  exit 5
fi

echo "Installing package: ${packages[0]}"
run need_sudo apt-get install -y "${packages[0]}"

echo "Done. Run scripts/probe_labview.sh to verify."
