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
if command -v labview >/dev/null 2>&1; then
  command -v labview
else
  echo "labview is not in PATH."
fi

echo
echo "== Likely LabVIEW files =="
find /usr/local /opt -maxdepth 5 -iname 'labview*' 2>/dev/null | sed -n '1,80p' || true

echo
echo "== Support packages =="
for pkg in xvfb libopenal1 libncurses6; do
  dpkg -s "$pkg" >/dev/null 2>&1 && echo "$pkg: installed" || echo "$pkg: missing"
done
