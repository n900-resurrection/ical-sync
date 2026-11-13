#!/bin/bash
# Draw the row icons of the GUI with ImageMagick: icons/reload.png (blue circular arrow) and icons/remove.png (red cross), 48x48.
set -euo pipefail
cd "$(dirname "$0")"
convert() { command convert +set date:create +set date:modify -define png:exclude-chunk=date,time "$@"; }
convert -size 48x48 xc:none -fill none -stroke '#3d9bd9' -strokewidth 5 -draw 'arc 8,8 40,40 40,330' \
  -fill '#3d9bd9' -stroke none -draw 'polygon 30,3 44,16 28,22' icons/reload.png
convert -size 48x48 xc:none -stroke '#d9322f' -strokewidth 8 -draw 'line 11,11 37,37' -draw 'line 37,11 11,37' icons/remove.png
