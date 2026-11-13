# ical-sync

Keeps iCal (`.ics`) calendars, for example the secret iCal address of a Google calendar or a public calendar, in the Maemo Calendar of the Nokia N900
(Maemo 5), events and tasks. Python 3 + [hildonlite](https://github.com/n900-resurrection/hildonlite); the Calendar is written through its own
library `libcalendar_backend` (ctypes), so the Calendar application and its home widget show the items as if they were made by hand.

- **Command** `ical-sync` (`ical_sync.py`): `add`, `list`, `set`, `remove NAME --events all|future|none`, `sync [--force] [--dry-run] [--if-online]`, `init`.
  Every item of a feed is tracked by its UID and a hash: new ones are imported, changed ones replaced, removed or cancelled ones deleted, ones deleted in the
  phone come back. Items that ended more than `keep_past_days` ago (default 30, at most 365) are left in the calendar as they are: not imported, updated or deleted any more. The future is synced as far as the feed goes. Items made by hand are never touched.
- **Cron:** the job `/etc/event.d/ical-sync` runs BusyBox `crond`; the crontab line of `user` starts `ical-sync sync --if-online` every 30 minutes. The command exits at once
  unless the interval of a source (default 6 hours) has elapsed and the phone is online already, so the sleeping phone is never woken and no connection is started.
- **GUI** `ical-sync-gui` (menu: Calendar sync): the list of followed calendars, Add / Edit (address, calendar name, interval, how much of the past to keep), Remove
  (asks whether to delete all events, only the future ones, or none), Sync now, and a switch for the log (`~/.ical-sync/sync.log`, cut to 100 kB).
- The Czech public holidays are the default source (first run). Settings: `~/.ical-sync/sources.conf` (mode 600: the secret address is a password), state: `state.json`.

Notes on the Calendar library and the design: `DOC/calendar.md` in the N900 project. Licence: MIT.
