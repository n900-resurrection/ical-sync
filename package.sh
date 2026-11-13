#!/bin/bash
# Package ical-sync as a .deb for Maemo 5: make -C apps/ical-sync deb
# Output: /project/build/deb/ical-sync_<VERSION>-<REV>_armel.deb
# Installs an upstart job (/etc/event.d/ical-sync: BusyBox crond) and the crontab line of the user (every 30 minutes, --if-online).
set -euo pipefail
PROJ=/project
. "$PROJ/scripts/debpack.sh"

PKG=ical-sync
VERSION="${VERSION:-0.1}"
STAGE="$PROJ/build/deb/stage-$PKG"
HERE="$PROJ/apps/ical-sync"

rm -rf "$STAGE"
mkdir -p "$STAGE/opt/$PKG" "$STAGE/usr/bin" "$STAGE/usr/share/applications/hildon" "$STAGE/etc/event.d" "$STAGE/DEBIAN"
install -m 755 "$HERE/ical-sync" "$HERE/ical-sync-gui" "$STAGE/opt/$PKG/"
install -m 644 "$HERE/ical_sync.py" "$STAGE/opt/$PKG/"
mkdir -p "$STAGE/opt/$PKG/icons"
install -m 644 "$HERE/icons/reload.png" "$HERE/icons/remove.png" "$STAGE/opt/$PKG/icons/"
install -m 644 "$HERE/ical-sync.upstart" "$STAGE/etc/event.d/ical-sync"
for sz in 48 64; do
    mkdir -p "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps"
    install -m 644 "$HERE/icons/$sz.png" "$STAGE/usr/share/icons/hicolor/${sz}x${sz}/apps/$PKG.png"
done
ln -s ../../opt/$PKG/ical-sync "$STAGE/usr/bin/ical-sync"
ln -s ../../opt/$PKG/ical-sync-gui "$STAGE/usr/bin/ical-sync-gui"
cat > "$STAGE/usr/share/applications/hildon/$PKG.desktop" <<'EOT'
[Desktop Entry]
Encoding=UTF-8
Version=1.0
Type=Application
Name=Calendar sync
Icon=ical-sync
Exec=/usr/bin/ical-sync-gui
X-Osso-Type=application/x-executable
EOT
cat > "$STAGE/DEBIAN/postinst" <<'EOT'
#!/bin/sh
# The crontab of the user gets one line (an older line of ours is replaced), the settings are created with the Czech holidays when
# there are none, and the job with crond is started. A failure here must not break the installation.
case "$1" in configure)
    rm -f /opt/ical-sync/ical-sync.py                      # the first, hand-made version
    mkdir -p /var/spool/cron/crontabs
    CT=/var/spool/cron/crontabs/user
    [ -f "$CT" ] && grep -v "ical-sync" "$CT" > "$CT.new" || : > "$CT.new"
    echo '*/30 * * * * HOME=/home/user /opt/ical-sync/ical-sync sync --if-online >/dev/null 2>&1   # ical-sync' >> "$CT.new"
    chmod 600 "$CT.new"; mv "$CT.new" "$CT"
    su user -c "HOME=/home/user /opt/ical-sync/ical-sync init" >/dev/null 2>&1 || true
    initctl start ical-sync >/dev/null 2>&1 || true ;;
esac
exit 0
EOT
cat > "$STAGE/DEBIAN/prerm" <<'EOT'
#!/bin/sh
case "$1" in remove) initctl stop ical-sync >/dev/null 2>&1 || true ;; esac
exit 0
EOT
cat > "$STAGE/DEBIAN/postrm" <<'EOT'
#!/bin/sh
# Remove: the crontab line goes, the settings and the Calendar events stay (~/.ical-sync).
CT=/var/spool/cron/crontabs/user
case "$1" in remove|purge) [ -f "$CT" ] && { grep -v "ical-sync" "$CT" > "$CT.new" || true; mv "$CT.new" "$CT"; chmod 600 "$CT"; } ;; esac
exit 0
EOT
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

SECTION=user/office
DEPENDS="python3.11, python3-hildonlite (>= 0.4.0), calendar-backend, curl"
DISPLAY_NAME="Calendar sync"
SHORT_DESC="Keep iCal calendars (Google Calendar, holidays) in the Maemo Calendar"
LONG_DESC="Follows iCal (.ics) addresses, for example the secret iCal address of a Google calendar or a public calendar, and keeps their events and
tasks in the Maemo Calendar: new items are added, changed ones replaced, removed ones deleted; the past is kept for at most a month, the future as far
as the feed goes. A job with cron checks every 30 minutes, only when the phone is online already (it never starts a connection), and updates each
calendar at its own interval. The application adds and removes the addresses, sets the interval and switches the log. The Czech public holidays are the
default calendar. Command line: ical-sync (see ical-sync --help). Upstream: this project (MIT)."
debpack_build
