"""Host tests of the pure parts of ical_sync (no Calendar library): python3 -I tests/test_ical_sync.py"""
import os, sys, tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ["ICALSYNC_DIR"] = tempfile.mkdtemp(prefix="ical-sync-test-")
import ical_sync as S

fails = []


def ok(cond, what):
    print(("ok    " if cond else "FAIL  ") + what)
    if not cond:
        fails.append(what)


text = open(os.path.join(HERE, "test1.ics")).read()
tz, items = S.parse_feed(text)
ok(sorted(items) == ["test-event-1@n900", "test-event-2@n900", "test-todo-1@n900"], "feed is split into items by UID")
ok(tz == [], "no VTIMEZONE in the sample")
a = items["test-event-1@n900"]
ok(S.prop(a[0], "SUMMARY")[1] == "Test event (calimport)", "prop() reads a property")
h1 = S.item_hash(a)
changed = [[l.replace("20261112T100000Z", "20271212T100000Z") if l.startswith("DTSTAMP") else l for l in a[0]]]
ok(S.item_hash(changed) == h1, "DTSTAMP does not change the hash")
changed = [[l.replace("Lab", "Office") for l in a[0]]]
ok(S.item_hash(changed) != h1, "a real change changes the hash")
ok(S.is_old(a, date(2027, 1, 1)) and not S.is_old(a, date(2026, 1, 1)), "a single event is old when it ended before the limit")
ok(not S.is_old(items["test-event-2@n900"], date(2030, 1, 1)), "a repeating event is never old")
ok(not S.is_old(items["test-todo-1@n900"], date(2030, 1, 1)), "a task is never old")
ok(S.is_cancelled([["BEGIN:VEVENT", "STATUS:CANCELLED", "END:VEVENT"]]) and not S.is_cancelled(a), "cancelled items are recognised")
long = "DESCRIPTION:" + "žluťoučký " * 30
folded = S.fold(long)
ok(all(len(x.encode()) <= 75 for x in folded.split("\r\n")), "folded lines are at most 75 octets")
ok(S.unfold(folded) == [long], "fold and unfold are inverse (UTF-8 is not cut)")
path = os.path.join(os.environ["ICALSYNC_DIR"], "x.ics")
S.write_ics(path, tz, a)
tz2, it2 = S.parse_feed(open(path).read())
ok(list(it2) == ["test-event-1@n900"], "write_ics output is read back")

cp = S.load_conf()
ok(S.source_names(cp) == ["holidays"] and S.logging_on(cp), "first run creates the Czech holidays source with the log on")
ok(oct(os.stat(S.CONF).st_mode & 0o777) == "0o600", "the settings file is private (mode 600)")
S.set_general(cp, "logging", "no")
ok(not S.logging_on(S.load_conf()), "the logging switch is stored")
S._log_on = False
S.log("not written")
ok(not os.path.exists(S.LOG), "no log file while the logging is off")
S._log_on = True
S.log("written")
ok("written" in open(S.LOG).read(), "a log line is written when the logging is on")
sys.exit(1 if fails else 0)
