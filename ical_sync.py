#!/opt/python3/bin/python3
"""Keep iCal feeds (Google Calendar, public calendars) in the Maemo Calendar. Run ON THE PHONE as user.

  ical-sync add NAME URL [--calendar TITLE] [--interval MINUTES] [--keep-past DAYS]
  ical-sync list
  ical-sync set NAME KEY=VALUE ...            (url, calendar, interval_minutes, keep_past_days)
  ical-sync set --general logging=yes|no
  ical-sync remove NAME [--events all|future|none]     what happens with the events of the calendar (default: none)
  ical-sync sync [NAME] [--force] [--dry-run] [--if-online]
      (sources whose interval has elapsed; --force: all given; --if-online: do nothing unless the phone is connected already,
       so a timer never brings up Wi-Fi or mobile data: that is what costs the battery, not the sync itself)
  ical-sync init                              (creates the settings with the Czech holidays when there are none)

Sources are kept in ~/.ical-sync/sources.conf (mode 600, the URL of a secret iCal address is a password), the map
"UID -> items in the Calendar" in ~/.ical-sync/state.json, the log (when switched on) in ~/.ical-sync/sync.log.

The Calendar library finds duplicates only by summary + start + type (not by UID), so every item of the feed is
tracked by its UID and a hash of its text: a new UID is imported, a changed one is deleted and imported again,
one that disappeared from the feed (or is cancelled) is deleted; one that ended more than --keep-past days ago (at most 365) is left in the calendar as it is and no longer synced (not imported either);
one that was deleted in the phone comes back (the feed is the master). The future is kept as far as the feed goes.
Items that are not in the map (made by hand in the phone) are never touched.
"""
import configparser
import ctypes as C
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import ssl
import sys
import tempfile
import time
import urllib.request
from datetime import date, datetime, timedelta

HOME = os.environ.get("HOME") or "/home/user"
DIR = os.environ.get("ICALSYNC_DIR") or os.path.join(HOME, ".ical-sync")
CONF = os.path.join(DIR, "sources.conf")
STATE = os.path.join(DIR, "state.json")
LOG = os.path.join(DIR, "sync.log")
LOCK = os.path.join(DIR, "lock")
CALDB = os.environ.get("ICALSYNC_CALDB") or os.path.join(HOME, ".calendar", "calendardb")
CAFILE = "/opt/curl/etc/ssl/cacert.pem"
MAX_PAST_DAYS = 365
LOG_LIMIT = 100000
DEFAULT_SOURCES = {
    "holidays": {"url": "https://calendar.google.com/calendar/ical/cs.czech%23holiday%40group.v.calendar.google.com/public/basic.ics",
                 "calendar": "Svatky", "interval_minutes": "360", "keep_past_days": "30"},
}

# ---------------------------------------------------------------------------------------------------------------------
# libcalendar_backend through ctypes (see DOC/calendar.md): std::string of the phone's own libstdc++, by pointer.

P = C.c_void_p
_bk = _std = None


class Str:
    """A std::string made and destroyed by the libstdc++ of the phone; keep the object alive while the library uses it."""
    def __init__(self, text=""):
        self.buf = C.create_string_buffer(16)
        self.alloc = C.create_string_buffer(8)
        _std._ZNSsC1EPKcRKSaIcE(self.buf, text.encode(), self.alloc)

    def __del__(self):
        _std._ZNSsD1Ev(self.buf)


def _fn(name, restype, *argtypes):
    f = getattr(_bk, name)
    f.restype, f.argtypes = restype, argtypes
    return f


class Backend:
    def __init__(self):
        global _bk, _std
        _bk = C.CDLL("libcalendar_backend.so.0", mode=C.RTLD_GLOBAL)
        _std = C.CDLL("libstdc++.so.6", mode=C.RTLD_GLOBAL)
        ip = C.POINTER(C.c_int)
        self.mc = _fn("_ZN14CMulticalendar10MCInstanceEv", P)()
        self._by_name = _fn("_ZN14CMulticalendar17getCalendarByNameESsRi", P, P, P, ip)
        self._add = _fn("_ZN14CMulticalendar11addCalendarESs14CalendarColourii12CalendarTypeSsSsRi", P,
                        P, P, C.c_int, C.c_int, C.c_int, C.c_int, P, P, ip)
        self._cal_id = _fn("_ZN9CCalendar13getCalendarIdEv", C.c_int, P)
        self._import = _fn("_ZN14CMulticalendar17importIcsFileDataESsiRSsRiS1_S1_S1_", C.c_ubyte,
                           P, P, C.c_int, P, ip, ip, ip, ip)
        self._del_comp = _fn("_ZN9CCalendar15deleteComponentESsRi", C.c_ubyte, P, P, ip)
        self._del_cal = _fn("_ZN14CMulticalendar14deleteCalendarEiRi", C.c_ubyte, P, C.c_int, ip)

    def calendar(self, title, create=True):
        """The CCalendar pointer of the calendar with this title (created when missing)."""
        s = Str(title)
        err = C.c_int(0)
        cal = self._by_name(self.mc, s.buf, C.byref(err))
        if not cal and create:
            empty, ver = Str(""), Str("1.0")
            err = C.c_int(0)
            cal = self._add(self.mc, s.buf, 2, 0, 1, 0, empty.buf, ver.buf, C.byref(err))   # colour 2, visible, local
        return cal or None

    def calendar_id(self, cal):
        return self._cal_id(cal)

    def import_file(self, path, cal_id):
        """Import an .ics file; returns (ok, error code)."""
        s_path, s_ev = Str(path), Str("")
        n = [C.c_int(0) for _ in range(4)]
        ok = self._import(self.mc, s_path.buf, cal_id, s_ev.buf, *(C.byref(x) for x in n))
        return bool(ok), n[3].value

    def delete_component(self, cal, comp_id):
        s, err = Str(str(comp_id)), C.c_int(0)
        return bool(self._del_comp(cal, s.buf, C.byref(err)))

    def delete_calendar(self, title):
        cal = self.calendar(title, create=False)
        if not cal:
            return False
        err = C.c_int(0)
        return bool(self._del_cal(self.mc, self.calendar_id(cal), C.byref(err)))


def component_ids(cal_id):
    con = sqlite3.connect("file:%s?mode=ro" % CALDB, uri=True, timeout=30)
    try:
        return {r[0] for r in con.execute("select Id from Components where CalendarId=?", (cal_id,))}
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------------------------------
# iCalendar text

def unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def fold(line):
    parts, b = [], line.encode()
    while len(b) > 74:
        cut = 74
        while cut > 0 and (b[cut] & 0xC0) == 0x80:      # not inside a UTF-8 character
            cut -= 1
        parts.append(b[:cut].decode())
        b = b[cut:]
        b = b" " + b
    parts.append(b.decode())
    return "\r\n".join(parts)


def parse_feed(text):
    """-> (VTIMEZONE blocks, {uid: [component blocks]}); a block is a list of unfolded lines BEGIN..END."""
    lines = unfold(text)
    blocks, cur, depth = [], None, 0
    for ln in lines:
        key = ln.split(":", 1)[0].split(";", 1)[0].upper()
        if key == "BEGIN":
            depth += 1
            if depth == 2:
                cur = []
        if cur is not None:
            cur.append(ln)
        if key == "END":
            if depth == 2 and cur is not None:
                blocks.append(cur)
                cur = None
            depth -= 1
    tz, items = [], {}
    for b in blocks:
        kind = b[0].split(":", 1)[1].strip().upper()
        if kind == "VTIMEZONE":
            tz.append(b)
        elif kind in ("VEVENT", "VTODO"):
            uid = None
            d = 0
            for ln in b:
                k = ln.split(":", 1)[0].split(";", 1)[0].upper()
                if k == "BEGIN":
                    d += 1
                elif k == "END":
                    d -= 1
                elif k == "UID" and d == 1:
                    uid = ln.split(":", 1)[1].strip()
            if uid:
                items.setdefault(uid, []).append(b)
    return tz, items


def prop(block, name):
    """The first top-level property of a block: (parameters, value) or None."""
    d = 0
    for ln in block:
        head, _, val = ln.partition(":")
        k = head.split(";", 1)[0].upper()
        if k == "BEGIN":
            d += 1
        elif k == "END":
            d -= 1
        elif d == 1 and k == name:
            return head, val
    return None


def item_hash(blocks):
    h = hashlib.sha256()
    for b in blocks:
        for ln in b:
            if not ln.upper().startswith("DTSTAMP"):          # Google writes the download time into it
                h.update(ln.encode())
                h.update(b"\n")
    return h.hexdigest()


def ics_date(value):
    m = re.match(r"(\d{4})(\d\d)(\d\d)", value or "")
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def is_old(blocks, limit):
    """True for a single (not repeating) event that ended before `limit`; tasks and repeating items are never old."""
    for b in blocks:
        if b[0].upper() != "BEGIN:VEVENT" or prop(b, "RRULE") or prop(b, "RDATE"):
            return False
        end = prop(b, "DTEND") or prop(b, "DTSTART")
        d = ics_date(end[1]) if end else None
        if d is None or d >= limit:
            return False
    return True


def is_cancelled(blocks):
    return all((prop(b, "STATUS") or ("", ""))[1].strip().upper() == "CANCELLED" for b in blocks)


def write_ics(path, tz, blocks):
    with open(path, "w", encoding="utf-8", newline="") as f:
        out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//N900 ical-sync//EN"]
        for b in tz + blocks:
            out += b
        f.write("\r\n".join(fold(x) for x in out + ["END:VCALENDAR"]) + "\r\n")


# ---------------------------------------------------------------------------------------------------------------------
# sources, state

def load_conf():
    """The settings; a first run (no file) creates them with the Czech public holidays as the default source."""
    cp = configparser.ConfigParser(interpolation=None)
    if os.path.exists(CONF):
        cp.read(CONF)
    else:
        cp["general"] = {"logging": "yes"}
        for name, sec in DEFAULT_SOURCES.items():
            cp[name] = sec
        save_conf(cp)
    return cp


def save_conf(cp):
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        cp.write(f)


def set_general(cp, key, value):
    """Change a general setting (logging) and save."""
    if not cp.has_section("general"):
        cp.add_section("general")
    cp["general"][key] = value
    save_conf(cp)


def source_names(cp):
    return [n for n in cp.sections() if n != "general"]


def logging_on(cp):
    return cp.get("general", "logging", fallback="yes").strip().lower() in ("yes", "true", "1", "on")


_log_on = True


def log(msg):
    """A line to the standard output and, when the logging is switched on, to the log file (cut to its newest half above 100 kB)."""
    print(msg, flush=True)
    if not _log_on:
        return
    try:
        os.makedirs(DIR, mode=0o700, exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_LIMIT:
            with open(LOG, "rb") as f:
                f.seek(-LOG_LIMIT // 2, 2)
                f.readline()
                tail = f.read()
            with open(LOG, "wb") as f:
                f.write(tail)
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(DIR, mode=0o700, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def download(url):
    ctx = ssl.create_default_context(cafile=CAFILE if os.path.exists(CAFILE) else None)
    req = urllib.request.Request(url.replace("webcal://", "https://"), headers={"User-Agent": "n900-ical-sync"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def sync_source(be, name, sec, st, dry=False):
    url, title = sec["url"], sec.get("calendar") or name
    keep = max(0, min(MAX_PAST_DAYS, int(sec.get("keep_past_days", "30"))))
    text = download(url)
    if "BEGIN:VCALENDAR" not in text[:4096].upper():
        raise ValueError("not an iCal feed (a web page?): use the secret/public address in iCal format, ending with .ics")
    tz, items = parse_feed(text)
    limit = date.today() - timedelta(days=keep)
    live = {uid: bl for uid, bl in items.items() if not is_cancelled(bl)}
    want = {uid: bl for uid, bl in live.items() if not is_old(bl, limit)}
    frozen = {uid for uid in live if uid not in want}          # over for more than keep_past_days: stays in the phone as it is
    mine = st.setdefault(name, {"items": {}})["items"]
    cal = be.calendar(title, create=not dry)
    if cal is None:
        log("%s: calendar %r would be created" % (name, title))
        cal_id = -1
    else:
        cal_id = be.calendar_id(cal)
    new = [u for u in want if u not in mine]
    existing = component_ids(cal_id) if cal_id >= 0 else set()
    # changed in the feed, or deleted in the phone meanwhile (it comes back: the feed is the master)
    changed = [u for u in want if u in mine and (mine[u]["hash"] != item_hash(want[u]) or not set(mine[u]["ids"]) <= existing)]
    gone = [u for u in mine if u not in want and u not in frozen]
    log("%s: feed has %d items; new %d, changed %d, removed %d, unchanged %d, old (left alone) %d" %
          (name, len(items), len(new), len(changed), len(gone), len(want) - len(new) - len(changed), len(frozen)))
    if dry:
        return
    for uid in gone + changed:
        for cid in mine[uid]["ids"]:
            be.delete_component(cal, cid)
        if uid in gone:
            del mine[uid]
    tmp = tempfile.mkdtemp(prefix="ical-sync-")
    try:
        for uid in new + changed:
            before = component_ids(cal_id)
            path = os.path.join(tmp, "item.ics")
            write_ics(path, tz, want[uid])
            ok, err = be.import_file(path, cal_id)
            ids = sorted(component_ids(cal_id) - before)
            if not ok:
                log("  import of %s failed (error %d)" % (uid, err))
                mine.pop(uid, None)
                continue
            if not ids:
                log("  %s: the library took it for a duplicate of an item already there (not imported)" % uid)
            mine[uid] = {"hash": item_hash(want[uid]), "ids": ids}
            save_state(st)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    st[name]["last"] = int(time.time())
    st[name]["error"] = ""
    save_state(st)


def online():
    """True when a default route exists (a connection is up); does not touch the connection manager."""
    try:
        with open("/proc/net/route") as f:
            return any(ln.split()[1:2] == ["00000000"] for ln in f.read().splitlines()[1:])
    except OSError:
        return False


def due(sec, st, name, force):
    if force:
        return True
    interval = int(sec.get("interval_minutes", "360"))
    return time.time() - st.get(name, {}).get("last", 0) >= interval * 60


def live_ids(ids):
    """Of these component ids those that are still ahead: a task, a repeating item, or an event that has not ended yet."""
    if not ids:
        return []
    now = int(time.time())
    marks = ",".join("?" * len(ids))
    con = sqlite3.connect("file:%s?mode=ro" % CALDB, uri=True, timeout=30)
    try:
        repeating = {r[0] for r in con.execute("select Id from RECURSIVE where Id in (%s)" % marks, ids)}
        rows = con.execute("select Id, DateEnd, ComponentType from Components where Id in (%s)" % marks, ids).fetchall()
    finally:
        con.close()
    return [i for i, end, typ in rows if i in repeating or typ == 2 or end is None or end < 0 or end >= now]


def remove_source(cp, name, events):
    """Stop following a source. events: "all" deletes the whole calendar, "future" the items that are not over yet, "none" nothing."""
    title = cp[name].get("calendar") or name if cp.has_section(name) else name
    st = load_state()
    mine = st.get(name, {}).get("items", {})
    if events == "all":
        log("%s: calendar %r %s" % (name, title, "deleted" if Backend().delete_calendar(title) else "not found"))
    elif events == "future":
        be = Backend()
        cal = be.calendar(title, create=False)
        ids = live_ids(sorted({i for it in mine.values() for i in it["ids"]}))
        if cal:
            for i in ids:
                be.delete_component(cal, i)
        log("%s: %d future items deleted, the past stays in %r" % (name, len(ids), title))
    if cp.has_section(name):
        cp.remove_section(name)
        save_conf(cp)
    st.pop(name, None)
    save_state(st)


def main():
    global _log_on
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd, args = a[0], a[1:]
    opts = {}
    pos = []
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            k = args[i][2:]
            if k in ("force", "dry-run", "if-online", "general"):
                opts[k] = True
            else:
                i += 1
                opts[k] = args[i]
        else:
            pos.append(args[i])
        i += 1
    cp = load_conf()
    _log_on = logging_on(cp)
    if cmd == "init":
        print("settings in %s" % CONF)
    elif cmd == "add" and len(pos) == 2:
        cp[pos[0]] = {"url": pos[1], "calendar": opts.get("calendar", pos[0]),
                      "interval_minutes": opts.get("interval", "360"), "keep_past_days": opts.get("keep-past", "30")}
        save_conf(cp)
        print("source %r added" % pos[0])
    elif cmd == "set" and pos:
        target = "general" if opts.get("general") else pos.pop(0)
        if not cp.has_section(target):
            cp.add_section(target)
        for kv in pos:
            k, _, v = kv.partition("=")
            cp[target][k] = v
        save_conf(cp)
    elif cmd == "list":
        st = load_state()
        for n in source_names(cp):
            last = st.get(n, {}).get("last")
            print("%s: calendar %r, every %s min, last sync %s, %d items" %
                  (n, cp[n].get("calendar"), cp[n].get("interval_minutes"),
                   datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M") if last else "never",
                   len(st.get(n, {}).get("items", {}))))
    elif cmd == "remove" and len(pos) == 1:
        ev = opts.get("events", "none")
        if ev not in ("all", "future", "none"):
            sys.exit("--events all|future|none")
        remove_source(cp, pos[0], ev)
    elif cmd == "sync":
        os.makedirs(DIR, mode=0o700, exist_ok=True)
        lock = open(LOCK, "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another synchronisation is running")
            return
        st = load_state()
        todo = [n for n in source_names(cp) if not pos or n in pos]
        todo = [n for n in todo if due(cp[n], st, n, opts.get("force") or opts.get("dry-run"))]
        if not todo or (opts.get("if-online") and not online()):
            return                      # nothing due or no connection: exit at once (no library, no network)
        be = Backend()
        for n in todo:
            try:
                sync_source(be, n, cp[n], st, bool(opts.get("dry-run")))
            except Exception as e:      # a failed source (no network...) must not stop the others
                log("%s: failed: %r" % (n, e))
                st.setdefault(n, {"items": {}})["error"] = repr(e)
                save_state(st)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
