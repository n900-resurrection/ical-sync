TEST_NAME=ical-sync
need_pkg ical-sync
ok in-path sh -c 'command -v ical-sync && command -v ical-sync-gui'
ok upstart-job sh -c 'initctl status ical-sync | grep -q "(start) running"'
ok crond-running sh -c 'ps | grep -q "[c]rond"'
ok crontab-line sh -c 'grep -q "ical-sync sync --if-online" /var/spool/cron/crontabs/user'
ok hildonlite-new sh -c '/opt/python3/bin/python3 -c "import hildonlite; hildonlite.Scale, hildonlite.CheckButton, hildonlite.Dialog"'
ok calendar-library sh -c 'ls /usr/lib/libcalendar_backend.so.0 /usr/lib/libstdc++.so.6'
ok settings-private sh -c 'test "$(stat -c %a /home/user/.ical-sync/sources.conf)" = 600'
ok list sh -c 'su user -c "HOME=/home/user ical-sync list" | grep -q "calendar"'
ok due-check-quick sh -c 'su user -c "HOME=/home/user ical-sync sync --if-online"'
ok calendar-exists sh -c 'sqlite3 /home/user/.calendar/calendardb "select Name from Calendars" | grep -q .'
# The synchronisation itself (import, change, removal) and the GUI were checked by hand; see DOC/calendar.md.
summary
