#!/bin/bash
# Draw the icons of ical-sync with ImageMagick: icons/48.png and 64.png (a calendar page with two circular arrows on a dark rounded square).
# The PNGs are committed; run this only to change the design.
set -euo pipefail
cd "$(dirname "$0")"
# ImageMagick writes the creation time into the PNG: without these options every run changes the files although the picture is the same.
convert() { command convert +set date:create +set date:modify -define png:exclude-chunk=date,time "$@"; }
mkdir -p icons
W='#f2f2f2'
dots=()
for r in 0 1 2; do for c in 0 1 2 3; do dots+=(-draw "roundrectangle $((52+c*34)),$((112+r*28)) $((70+c*34)),$((128+r*28)) 3,3"); done; done
convert -size 256x256 xc:none -fill '#26323f' -draw 'roundrectangle 8,8 247,247 44,44' \
  -fill "$W" -draw 'roundrectangle 30,40 226,216 16,16' \
  -fill '#d9534f' -draw 'roundrectangle 30,40 226,92 16,16' -draw 'rectangle 30,70 226,92' \
  -fill '#26323f' -draw 'roundrectangle 70,24 82,56 4,4' -draw 'roundrectangle 174,24 186,56 4,4' \
  "${dots[@]}" \
  -fill none -stroke '#3d9bd9' -strokewidth 14 -draw 'arc 112,150 214,232 200,60' \
  -fill '#3d9bd9' -stroke none -draw 'polygon 204,150 232,176 190,184' \
  icons/256.png
for s in 64 48; do convert icons/256.png -resize ${s}x${s} icons/$s.png; done
rm icons/256.png
