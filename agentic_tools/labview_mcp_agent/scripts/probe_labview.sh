#!/usr/bin/env bash
set -euo pipefail

echo "== OS =="
if command -v lsb_release >/dev/null 2>&1; then
  lsb_release -a 2>/dev/null
else
  cat /etc/os-release
fi
uname -a

echo
echo "== NI packages =="
if command -v dpkg >/dev/null 2>&1; then
  dpkg -l | grep -Ei 'labview|national instruments|nipkg|ni-visa|ni-daqmx' || echo "No NI/LabVIEW dpkg packages found."
else
  echo "dpkg is unavailable."
fi

echo
echo "== LabVIEW launcher =="
for candidate in labview labview64 LabVIEWCLI; do
  if command -v "$candidate" >/dev/null 2>&1; then
    printf '%s: %s\n' "$candidate" "$(command -v "$candidate")"
  else
    printf '%s: not in PATH\n' "$candidate"
  fi
done

echo
echo "== Likely LabVIEW files =="
find /usr/local /opt -maxdepth 5 -iname 'labview*' 2>/dev/null | sed -n '1,80p' || true

echo
echo "== Support packages =="
for pkg in xvfb libopenal1 libncurses6; do
  dpkg -s "$pkg" >/dev/null 2>&1 && echo "$pkg: installed" || echo "$pkg: missing"
done
