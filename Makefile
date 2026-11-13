# ical-sync: keeps iCal feeds (Google Calendar, public calendars) in the Maemo Calendar; cron + settings GUI. Targets and conventions: ../../mk/app.mk
override APP     := ical-sync
VERSION ?= 0.1
DEPS    := hildonlite
RUN_CMD := /usr/bin/ical-sync-gui
ICON_OUT := icons/64.png
include ../../mk/app.mk
