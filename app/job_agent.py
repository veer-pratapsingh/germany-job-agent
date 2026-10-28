"""Germany Job Agent: a desktop app that finds new jobs on German job boards each time you check, and builds a
tailored CV, cover letter and prep plan for any job with Claude Code or Codex.

usage: pythonw app/job_agent.py          (what the desktop shortcut runs)
       python app/job_agent.py --selftest

Searching, filtering and checking reuse .claude/skills/job-search/scripts/jobs.py; writing the application follows
.claude/skills/job-apply/SKILL.md, run headless by the engine picked for that job.
"""
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / ".claude" / "skills" / "job-search" / "scripts"))
import jobs  # noqa: E402  the shared search pipeline

DATA = PROJECT / "jobs" / "app"  # job database, postings and run logs; git-ignored like the rest of jobs/
PROFILE = PROJECT / "Veer_Pratap_Singh_Complete_Profile.md"
# outside the repo, because it holds the Apify token
CONFIG = Path(os.environ.get("APPDATA", Path.home())) / "GermanyJobAgent" / "settings.json"
NPM = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules"
DEFAULTS = {"apify_token": "", "linkedin": True, "indeed": True, "stepstone": True, "linkedin_max": 400,
            "check_top": 60, "parallel": 3, "claude_model": "sonnet", "claude_effort": "medium",
            "codex_model": "", "codex_effort": "medium", "sort": "best"}
KEEP_DAYS = 21  # jobs not seen again for this long leave the list, unless he applied or built something for them
CHECK_FIELDS = ("status", "apply_url", "apply_check", "checked", "snippets", "workplace_hint", "lang", "domain")
ACTIVE = ("analyzing", "building")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console window flashing up for each engine run
LIMIT_HINT = re.compile(r"\b(?:limits?|quota|usage|credits?|429|overloaded)\b", re.I)
TABLE_END = re.compile(r"^\|.*\n(?!\|)", re.M)  # the last row of a markdown table
RUNNING = set()  # engine processes, so closing the app can stop them
CLOSING = threading.Event()
LIGHT = Path(tempfile.gettempdir()) / "GermanyJobAgent"  # translations run outside the project, so its instructions don't load

ANALYZE = """You are helping Veer apply for one job. Do steps 1 to 3 of .claude/skills/job-apply/SKILL.md (read the \
posting, analyse it, build the keyword map) and nothing else.
- The posting, with its links and search notes, is in {posting}.
- Read Veer_Pratap_Singh_Complete_Profile.md. Section 7 lists the skills he has confirmed; section 16 lists the skills \
he said he lacks.
- Don't create, change or delete any file.
Reply with JSON only, no other text:
{{"to_ask": [{{"skill": "<name as the posting writes it>", "priority": "must-have" or "nice-to-have", \
"why": "<where the posting asks for it, under 15 words>"}}], "posting_language": "German" or "English", \
"fit_note": "<one sentence on how well he fits>"}}
to_ask holds the posting's important skills, tools and methods that section 7 doesn't show and section 16 doesn't \
already decline: at most 8, must-haves first. Leave out degrees, certificates, years of experience and language levels."""

BUILD = """Build Veer's application for one job: follow .claude/skills/job-apply/SKILL.md steps 5, 6, 7, 9, 10 and 11.
- The posting, with its links and search notes, is in {posting}. Today is {today}.
- Step 4 is done. He has used: {have}. He has not used: {lack}. The desktop app has recorded these answers in \
profile sections 7 and 16 and records this application in section 14 itself, so don't edit the profile.
- Skills he has not used stay off the CV completely, even where his projects seem to imply them; the prep plan \
covers them.
- Write the CV and the cover letter in {language}.
- Put all three files (CV .tex and .pdf, cover letter .tex and .pdf, Prep_*.md) in the folder {folder}, with the \
skill's usual file names. Create the folder, and write nothing into the project root. Put the step-10 page images \
in jobs/app/renders/.
- Nobody can answer questions during this run, so don't ask any.
Finish with the short report step 11 describes."""

TRANSLATE = """Translate this German job posting into English. Keep its structure: headings, bullet points and line \
breaks. The first line of your reply is the job title in English, and the translated posting follows. Reply with the \
translation only.

{title}

{text}"""

ANALYZE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["to_ask", "posting_language", "fit_note"],
                  "properties": {"to_ask": {"type": "array", "maxItems": 8, "items": {
                      "type": "object", "additionalProperties": False, "required": ["skill", "priority", "why"],
                      "properties": {"skill": {"type": "string"},
                                     "priority": {"type": "string", "enum": ["must-have", "nice-to-have"]},
                                     "why": {"type": "string"}}}},
                      "posting_language": {"type": "string", "enum": ["German", "English"]},
                      "fit_note": {"type": "string"}}}


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def slug(s: str, n: int = 40) -> str:
    """ASCII file-name part: "Gebr. Heinemann" -> "Gebr_Heinemann", umlauts spelled out."""
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"\((?:[mwfdx]\s*/\s*){1,3}[mwfdx]\)|\(all genders?\)", "", s, flags=re.I)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return (s[:n + 1].rsplit("_", 1)[0][:n] if len(s) > n else s) or "job"  # cut at a word boundary


def cell(s) -> str:
    """Text that can sit in a markdown table cell."""
    return re.sub(r"\s+", " ", str(s)).replace("|", "/").strip()


def window_days(last_check: str, at: dt.datetime) -> int:
    """Days to search back: the time since the last check plus one day of overlap, between 1 and 7."""
    if not last_check:
        return 7
    gap = (at - dt.datetime.fromisoformat(last_check)).total_seconds() / 86400
    return max(1, min(7, math.ceil(gap) + 1))


def posted(j: dict, at: dt.datetime) -> tuple:
    """(sort key, "5 hours ago"): when the job was posted, to the minute where the source gives a time (freehire,
    Arbeitnow, StepStone, Indeed, fresh LinkedIn jobs), otherwise to the day (the Bundesagentur, older LinkedIn jobs)."""
    s = j.get("posted_at") or j.get("published") or ""
    try:
        ts = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return "", ""
    if len(s) <= 10:  # a date only
        days = (at.date() - ts.date()).days
        return ts.isoformat(timespec="seconds"), "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"
    ts = ts.astimezone().replace(tzinfo=None) if ts.tzinfo else ts  # to this PC's time, like `at`
    mins = max(0, int((at - ts).total_seconds() // 60))
    ago = ("just now" if mins < 2 else f"{mins} minutes ago" if mins < 60 else "1 hour ago" if mins < 120 else
           f"{mins // 60} hours ago" if mins < 1440 else "1 day ago" if mins < 2880 else f"{mins // 1440} days ago")
    return ts.isoformat(timespec="seconds"), ago


def parse_translation(reply: str) -> tuple:
    """(title, text) from an engine's translation, whose first line is the title."""
    title, _, text = reply.strip().partition("\n")
    return title.strip(" #*"), text.strip()


def parse_json(text: str) -> dict:
    """The JSON object in an engine's reply, even when it wraps it in prose or a code fence."""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start != -1 and end > start else {}


def insert_rows(text: str, section: str, rows: str) -> str:
    """Adds rows at the end of the first table in the profile section whose heading starts with `section`."""
    text = text if text.endswith("\n") else text + "\n"
    start = text.find(section)
    end = text.find("\n## ", start + 1) if start != -1 else -1
    m = TABLE_END.search(text, start) if start != -1 else None
    if not m or (end != -1 and m.start() > end):
        return text + "\n" + rows  # the section or its table is gone: keep the rows anyway, at the end
    return text[:m.end()] + rows + text[m.end():]


def record_answers(path: Path, role: str, have: list, lack: list, day: dt.date):
    """Step 4 of the job-apply skill, done by the app so parallel builds never edit the profile at once."""
    text = path.read_text(encoding="utf-8")
    if have:
        line = (f"**Confirmed by you, {day.day} {day:%B %Y}, for the {role} role (desktop app):** "
                f"{', '.join(map(cell, have))}. Where you used each one isn't recorded yet.\n\n")
        anchor = "### Skills on your LinkedIn profile"
        text = text.replace(anchor, line + anchor, 1) if anchor in text else text.rstrip("\n") + "\n\n" + line
    if lack:
        text = insert_rows(text, "## 16.", "".join(
            f"| {cell(s)} | {role} | See the prep plan in this application's folder | "
            f"Not used (confirmed {day.day} {day:%b %Y}) |\n" for s in lack))
    path.write_text(text, encoding="utf-8")


def unconfirmed_on_cv(folder: Path, asked: list, have: list) -> list:
    """Skills he was asked about and didn't confirm that the CV names anyway. Only the CV: the letter may say
    he's keen to learn one."""
    text = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in folder.glob("*_CV_*.tex"))
    text = text.replace("\\", "").lower()  # LaTeX escapes: C\# -> c#
    return [s for s in asked if s not in have and re.search(rf"(?<!\w){re.escape(s.lower())}(?!\w)", text)]


def carry_checks(found: dict, old: dict, rechecked: set):
    """Jobs not checked again this run keep their last check: status, full text and snippets."""
    for i, j in found.items():
        prev = old.get(i, {})
        if i not in rechecked and prev.get("checked"):
            j.update({k: prev[k] for k in CHECK_FIELDS if k in prev})
            j["description"] = j["description"] or prev.get("description", "")


def keywords() -> list:
    return json.loads((jobs.SKILL / "search_input.json").read_text(encoding="utf-8"))["resumeKeywords"]


def rescore(j: dict, words: list):
    """Scores a job again once its full text is in (the Bundesagentur's only arrives with the check)."""
    j["kw"] = max(j["kw"], jobs.kw_score(j["title"] + "\n" + j["description"], words))
    if j["min_years"] is None:
        j["min_years"] = jobs.min_years(jobs.years_in_text(j["description"]))
    j["prescore"] = jobs.prescore(j)


def affordable(names: list, s: dict, left: float) -> list:
    """The Apify sources whose expected cost fits in what's left of this month's credit, cheapest first."""
    cost = {"linkedin": s["linkedin_max"] * jobs.PRICE["linkedin"],
            **{n: len(jobs.BOARD_QUERIES) * 40 * jobs.PRICE[n] for n in ("indeed", "stepstone")}}
    keep = []
    for n in sorted(names, key=cost.get):
        if cost[n] <= left:
            keep.append(n)
            left -= cost[n]
    return keep


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def engine_cmd(engine: str, s: dict, reply: Path, schema: Path = None, light: bool = False) -> list:
    """The command for a CV run, or with light=True for a translation: a small, fast model with no tools."""
    if engine == "claude":
        exe = NPM / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        claude = str(exe) if exe.exists() else shutil.which("claude") or "claude"
        if light:  # Sonnet at low effort: Haiku thought through 15-25k tokens per posting and took twice as long
            return [claude, "-p", "--output-format", "json", "--model", "sonnet", "--effort", "low", "--tools", "",
                    "--strict-mcp-config",
                    "--disable-slash-commands", "--no-session-persistence",
                    "--system-prompt", "You translate German job postings into clear English."]
        rules = DATA / "claude-permissions.json"  # only file edits and the PDF tools, nothing else
        rules.write_text(json.dumps({"permissions": {"allow": [
            "Read", "Edit", "Write", "Glob", "Grep", "Bash(python .claude/skills/job-apply/scripts/build_cv.py:*)",
            "Bash(pdftoppm:*)", "Bash(pdftotext:*)", "PowerShell(python .claude/skills/job-apply/scripts/build_cv.py:*)",
            "PowerShell(pdftoppm:*)"]}}), encoding="utf-8")
        return [claude, "-p", "--output-format", "json", "--model", s["claude_model"], "--effort", s["claude_effort"],
                "--permission-mode", "acceptEdits", "--settings", str(rules)]
    js = NPM / "@openai" / "codex" / "bin" / "codex.js"
    cmd = [shutil.which("node") or "node", str(js)] if js.exists() else [shutil.which("codex") or "codex"]
    if light:
        cmd += ["exec", "-s", "read-only", "-C", str(LIGHT), "--skip-git-repo-check", "-o", str(reply),
                "-c", 'model_reasoning_effort="low"']
    else:
        # writes stay inside the project; "unelevated" runs as his own user, because MiKTeX can't start under the
        # separate sandbox user that the "elevated" Windows sandbox uses
        cmd += ["exec", "-s", "workspace-write", "-c", 'windows.sandbox="unelevated"', "-C", str(PROJECT),
                "--skip-git-repo-check", "-o", str(reply)]
        if s["codex_effort"]:
            cmd += ["-c", f'model_reasoning_effort="{s["codex_effort"]}"']
    if s["codex_model"]:
        cmd += ["-m", s["codex_model"]]
    return cmd + (["--output-schema", str(schema)] if schema else []) + ["-"]


def stop(p: subprocess.Popen):
    """Ends an engine run together with everything it started (shells, pdflatex)."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)


def run_engine(engine: str, prompt: str, log: Path, timeout: int, schema: Path = None, light: bool = False) -> tuple:
    """(ok, reply): runs Claude Code or Codex headless in the project folder (a translation: outside it), with the
    prompt on stdin."""
    closed = (False, "Stopped because the app was closed.")
    if CLOSING.is_set():
        return closed
    reply = log.with_suffix(".reply.txt")
    cmd = engine_cmd(engine, load_settings(), reply, schema, light)
    LIGHT.mkdir(exist_ok=True)
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             encoding="utf-8", errors="replace", cwd=LIGHT if light else PROJECT, creationflags=NO_WINDOW)
    except OSError as e:
        return False, f"couldn't start {engine}: {e}"
    RUNNING.add(p)
    if CLOSING.is_set():
        stop(p)
    try:
        out, err = p.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(p)
        out, err = p.communicate()
        err += f"\nStopped after {timeout // 60} minutes."
    finally:
        RUNNING.discard(p)
    log.write_text(f"$ {' '.join(cmd)}\n\n--- prompt\n{prompt}\n\n--- stdout\n{out}\n\n--- stderr\n{err}",
                   encoding="utf-8")
    if CLOSING.is_set():
        return closed
    if engine == "claude":
        try:
            env = json.loads(out[out.find("{"):])
        except ValueError:
            return False, (err or out).strip()[-600:] or f"Claude exited with code {p.returncode}"
        return env.get("subtype") == "success" and not env.get("is_error"), str(env.get("result") or "").strip()
    text = reply.read_text(encoding="utf-8", errors="replace").strip() if reply.exists() else ""
    return p.returncode == 0 and bool(text), text or err.strip()[-600:] or f"Codex exited with code {p.returncode}"


class Store:
    """The job database (jobs/app/db.json). Every read-modify-write holds the lock."""

    def __init__(self, path: Path = DATA / "db.json"):
        self.path, self.lock = path, threading.RLock()
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {"last_check_at": None, "jobs": {}, "dropped": {}}

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)

    def merge(self, found: dict, checked_at: str, dropped: dict):
        """Adds a check's jobs, keeping his flags and builds. A job leaves when its full text shows it doesn't fit
        (dropped) or after KEEP_DAYS unseen, unless he applied or built something for it."""
        with self.lock:
            old = self.data["jobs"]
            for i, j in found.items():
                prev = old.get(i, {})
                j.update({k: prev[k] for k in ("first_seen", "applied", "applied_at", "hidden", "builds", "translation")
                          if k in prev})
                j.setdefault("first_seen", checked_at)
                j["last_seen"] = checked_at
                old[i] = j
            cutoff = (dt.datetime.fromisoformat(checked_at) - dt.timedelta(days=KEEP_DAYS)).isoformat()
            self.data["dropped"] = {i: d for i, d in {**self.data.get("dropped", {}), **dropped}.items() if d >= cutoff}
            for i in [i for i, j in old.items() if (j["last_seen"] < cutoff or i in dropped)
                      and not j.get("applied") and not j.get("builds")]:
                del old[i]
            self.data["last_check_at"] = checked_at
        self.save()


class Agent:
    """The page's API (window.pywebview.api). Public methods are what the page can call; the rest is private."""

    def __init__(self, store: Store = None):
        self._store = store or Store()
        self._pool = ThreadPoolExecutor(max(1, int(load_settings()["parallel"])))
        self._profile_lock = threading.Lock()
        self._refresh = {"running": False, "message": ""}
        self._version = 0
        self._checking = {}  # job id -> "running" or "failed", for jobs checked when he opens them
        self._translating = {}  # job id -> engine
        self._queued = False  # a full check asked for while the automatic one runs
        self._opened = now()  # "new" means found since he opened the app, so the automatic check doesn't hide the rest
        for j in self._store.data["jobs"].values():
            for b in j.get("builds", []):
                if b["state"] in ACTIVE:  # the app was closed on it, so nothing is running it any more
                    b.update(state="failed", finished=now(), message="The app was closed before this finished.")

    # ----- calls from the page -----
    def state(self) -> dict:
        with self._store.lock:
            js, last = list(self._store.data["jobs"].values()), self._store.data.get("last_check_at")
        recent, tasks = (dt.datetime.now() - dt.timedelta(minutes=15)).isoformat(), []
        for j in js:
            b = (j.get("builds") or [None])[-1]
            if b and (b["state"] in ACTIVE + ("questions",) or b.get("finished", "") > recent):
                secs = int(time.time() - dt.datetime.fromisoformat(b["started"]).timestamp())
                tasks.append({"job": j["id"], "company": j["company"][:28], "engine": b["engine"], "state": b["state"],
                              "elapsed": f"{secs // 60}:{secs % 60:02d}" if b["state"] in ACTIVE else ""})
        refresh = {**self._refresh, "queued": self._queued}
        return {"refresh": refresh, "version": self._version, "tasks": tasks,
                "last_check": dt.datetime.fromisoformat(last).strftime("%d %b, %H:%M") if last else "",
                "new_count": sum(1 for j in js if j.get("first_seen", "") >= self._opened and not j.get("hidden")
                                 and not j.get("applied") and j.get("status") != "Closed")}

    def list_jobs(self) -> list:
        with self._store.lock:
            js = list(self._store.data["jobs"].values())
        js.sort(key=lambda j: j.get("published") or "", reverse=True)
        js.sort(key=lambda j: -j.get("prescore", 0))
        return [self._summary(j) for j in js]

    def get_job(self, job_id: str) -> dict:
        j = self._store.data["jobs"].get(job_id)
        if not j:
            return None
        if not j.get("checked") and job_id not in self._checking:  # the search only checks its best jobs
            self._checking[job_id] = "running"
            threading.Thread(target=self._check_one, args=(job_id,), daemon=True).start()
        src = j.get("source", "LinkedIn")
        apply = j.get("apply_url") or j.get("company_url")
        summary = self._summary(j)
        if self._checking.get(job_id) == "running":
            summary["status"] = "Checking…"
        return {**summary, "description": j.get("description", ""), "snippets": j.get("snippets") or {},
                "url": j.get("url") or j.get("linkedin"), "apply": apply, "published": j.get("published"),
                "checked": (j.get("checked") or "").replace("T", " "), "builds": j.get("builds") or [],
                "lang": j.get("lang"), "translation": j.get("translation"), "translating": self._translating.get(job_id, ""),
                "apply_route": "Company site" if apply else ("Easy Apply on LinkedIn" if j.get("apply_type") ==
                                                              "EASY_APPLY" and src == "LinkedIn" else f"Via {src}")}

    def check_jobs(self, free_only: bool = False):
        """free_only is the automatic check when the app opens: Apify (paid) runs only from the button."""
        if self._refresh["running"]:
            self._queued = self._queued or not free_only  # pressed during the automatic check: the full one runs next
            return
        self._refresh = {"running": True, "message": "Starting…", "free_only": free_only}
        threading.Thread(target=self._check, args=(free_only,), daemon=True).start()

    def translate(self, job_id: str, engine: str):
        """Translates a German posting with the engine he picked. The translation is kept with the job."""
        if engine in ("claude", "codex") and job_id in self._store.data["jobs"] and job_id not in self._translating:
            self._translating[job_id] = engine
            threading.Thread(target=self._translate, args=(job_id, engine), daemon=True).start()

    def create(self, job_id: str, engine: str):
        """Starts an application: the engine reads the posting first and lists the skills to ask him about."""
        if engine not in ("claude", "codex"):
            return
        with self._store.lock:
            builds = self._store.data["jobs"][job_id].setdefault("builds", [])
            if builds and builds[-1]["state"] in ACTIVE + ("questions",):
                return  # one at a time per job, so a double click can't start two
            build = {"bid": f"{now()}-{engine}", "engine": engine, "state": "analyzing", "started": now()}
            builds.append(build)
        self._store.save()
        self._changed()
        self._pool.submit(self._analyze, job_id, build["bid"])

    def answer(self, job_id: str, have: list, lack: list, language: str):
        j = self._store.data["jobs"][job_id]
        b = next((b for b in reversed(j.get("builds", [])) if b["state"] == "questions"), None)
        if not b:
            return
        language = "German" if language == "German" else "English"
        self._update(job_id, b["bid"], state="building", started=now(),
                     answers={"have": have, "lack": lack, "language": language})
        try:
            with self._profile_lock:
                record_answers(PROFILE, cell(f"{j['company']}, {j['title']}"), have, lack, dt.date.today())
        except OSError as e:
            return self._fail(job_id, b["bid"], f"Couldn't save your answers in the profile: {e}", None)
        self._pool.submit(self._build, job_id, b["bid"])

    def toggle(self, job_id: str, flag: str):
        if flag not in ("applied", "hidden"):
            return
        with self._store.lock:
            j = self._store.data["jobs"][job_id]
            j[flag] = not j.get(flag)
            if flag == "applied":
                j["applied_at"] = now() if j[flag] else None
        self._store.save()
        self._changed()

    def open_url(self, url: str):
        if re.match(r"https?://", url or ""):
            webbrowser.open(url)

    def open_path(self, path: str):
        p = Path(path)
        if p.exists() and PROJECT in p.resolve().parents:  # only files this app or its engines wrote
            os.startfile(p)

    def get_settings(self) -> dict:
        s = load_settings()
        return {**{k: v for k, v in s.items() if k != "apify_token"}, "token_set": bool(s["apify_token"])}

    def save_settings(self, values: dict):
        s = load_settings()
        s.update({k: type(DEFAULTS[k])(v) for k, v in values.items() if k in DEFAULTS and (k != "apify_token" or v)})
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(s, indent=1), encoding="utf-8")

    def test_apify(self, token: str) -> str:
        try:
            used, limit = jobs.apify_credit(token or load_settings()["apify_token"])
            return f"Token works. This month you've used ${used:.2f} of ${limit:.2f}."
        except Exception as e:
            return f"That didn't work: {e}"

    # ----- background work -----
    def _changed(self):
        self._version += 1

    def _say(self, message: str):
        self._refresh = {**self._refresh, "running": True, "message": message}

    def _busy(self) -> bool:
        with self._store.lock:
            return any((j.get("builds") or [{}])[-1].get("state") in ACTIVE for j in self._store.data["jobs"].values())

    def _summary(self, j: dict) -> dict:
        b = (j.get("builds") or [{}])[-1]
        key, ago = posted(j, dt.datetime.now())
        locs = [jobs.place(l) for l in j["locations"]]
        return {"id": j["id"], "title": j["title"], "company": j["company"],
                "location": " / ".join(locs[:2]) + (f" +{len(locs) - 2}" if len(locs) > 2 else ""),
                "type": j["category"], "score": j.get("prescore", 0),
                "workplace": "" if j.get("workplace_hint") in (None, "Not stated") else j["workplace_hint"],
                "sources": [j.get("source", "LinkedIn")] + j.get("also_on", []), "posted": key, "ago": ago,
                "status": j.get("status", ""), "new": j.get("first_seen", "") >= self._opened,
                "applied": bool(j.get("applied")), "applied_at": j.get("applied_at") or "",
                "applied_on": dt.datetime.fromisoformat(j["applied_at"]).strftime("%d %b") if j.get("applied_at") else "",
                "hidden": bool(j.get("hidden")), "build": b.get("state")}

    def _check(self, free_only: bool = False):
        try:
            s, started, notes = load_settings(), now(), []
            paid = [n for n in ("indeed", "stepstone", "linkedin") if s[n]] if s["apify_token"] and not free_only else []
            if paid:
                try:
                    used, limit = jobs.apify_credit(s["apify_token"])
                    fits = affordable(paid, s, limit - used)
                    if len(fits) < len(paid):
                        notes.append(f"skipped {', '.join(jobs.SOURCES[n] for n in paid if n not in fits)}: "
                                     f"${used:.2f} of ${limit:.2f} Apify credit used this month")
                    paid = fits
                except Exception:
                    pass  # the runs themselves will report a bad token
            names = list(jobs.FREE_SOURCES) + paid
            # back to the oldest last successful search among these sources, so the automatic free-only checks
            # don't shorten the paid sources' window
            searched = self._store.data.setdefault("source_checks", {})
            last = self._store.data.get("last_check_at") or ""  # before per-source times, every check searched them all
            days = window_days(min(searched.get(n, last) for n in names) or None, dt.datetime.now())
            self._say(f"Searching {len(names)} {'free ' if free_only else ''}sources for jobs posted in the last "
                      f"{days} days…")
            items, counts = jobs.fetch_sources(names, days, s["apify_token"], int(s["linkedin_max"]), progress=self._say)
            notes += [f"{k}: {v}" for k, v in counts.items() if not v[0].isdigit()]
            if not items:
                raise RuntimeError("no source returned any jobs. " + "; ".join(notes))
            old, dropped = self._store.data["jobs"], self._store.data.get("dropped", {})
            pool, _ = jobs.make_pool(items, dt.date.today())
            found = {i: j for i, j in pool["jobs"].items() if i not in dropped}
            fetched = {str(x["jobId"]) for x in items if x.get("jobId")}
            # listed jobs that came back but no longer pass the filters (a rule changed, or he applied) leave too
            newly_dropped = {i: started for i in old if i in fetched and i not in pool["jobs"]}
            self._say(f"{len(found)} jobs after filtering. Checking the best ones on their sources…")
            ids = self._pick_checks(found, int(s["check_top"]))
            jobs.check(found, ids, progress=lambda n, t: self._say(f"Checking jobs on their sources: {n} of {t}"))
            carry_checks(found, old, set(ids))
            words, applied = keywords(), jobs.applied_sets()
            for i in [i for i, j in found.items() if j.get("checked")]:  # the full text is in: score again
                rescore(found[i], words)
                if jobs.drop_reason(found[i], applied):
                    newly_dropped[i] = started
                    del found[i]
            searched.update({n: started for n in names if counts.get(jobs.SOURCES[n], "")[:1].isdigit()})
            self._store.merge(found, started, newly_dropped)
            new = sum(1 for j in found.values() if j["first_seen"] == started)
            label = "Free sources checked" if free_only else "Done"
            self._refresh = {"running": False, "message": f"{label}: {new} new jobs." +
                                                          (f" ({'; '.join(notes)})" if notes else "")}
        except Exception as e:
            self._refresh = {"running": False, "message": f"The check failed: {e}"}
        self._changed()
        if self._queued:
            self._queued = False
            self.check_jobs()

    def _pick_checks(self, found: dict, top: int) -> list:
        """The best N, plus the best few of each job type and source, minus jobs checked in the last 20 hours."""
        fresh = (dt.datetime.now() - dt.timedelta(hours=20)).isoformat()
        old = self._store.data["jobs"]
        todo = [j for j in sorted(found.values(), key=lambda j: -j["prescore"])
                if old.get(j["id"], {}).get("checked", "") < fresh]
        picked = todo[:top]
        for key in ("category", "source"):
            for value in {j[key] for j in todo}:
                picked += [j for j in todo if j[key] == value and j not in picked][:5]
        return [j["id"] for j in picked]

    def _check_one(self, job_id: str):
        """Checks a job he opened that the search didn't check, so its status and full text show up."""
        try:
            j = dict(self._store.data["jobs"][job_id])
            jobs.check({job_id: j}, [job_id])
            rescore(j, keywords())
            with self._store.lock:
                if job_id in self._store.data["jobs"]:
                    self._store.data["jobs"][job_id].update(
                        {k: j[k] for k in CHECK_FIELDS + ("description", "kw", "min_years", "prescore")})
            self._store.save()
            self._checking.pop(job_id, None)
        except Exception:
            self._checking[job_id] = "failed"  # shows as not checked, and isn't retried until the app restarts
        # no _changed(): reloading every card for one job made the app slow; the open job's panel polls instead

    def _translate(self, job_id: str, engine: str):
        j = self._store.data["jobs"][job_id]
        log = self._log(job_id, "translate", engine)
        try:
            ok, reply = run_engine(engine, TRANSLATE.format(title=j["title"], text=j.get("description") or ""), log, 600,
                                   light=True)
            title, text = parse_translation(reply) if ok else ("", "")
            hint = " It may have hit its usage limit: try the other engine." if LIMIT_HINT.search(reply) else ""
            result = {"engine": engine, "title": title, "text": text} if text else \
                {"error": (reply or "No answer.")[-300:] + hint}
        except Exception as e:
            result = {"error": str(e)}
        with self._store.lock:
            if job_id in self._store.data["jobs"]:
                self._store.data["jobs"][job_id]["translation"] = result
        self._store.save()
        self._translating.pop(job_id, None)

    def _update(self, job_id: str, bid: str, **fields):
        with self._store.lock:
            for b in self._store.data["jobs"][job_id].get("builds", []):
                if b["bid"] == bid:
                    b.update(fields)
        self._store.save()
        self._changed()

    def _posting(self, job_id: str) -> Path:
        j = self._store.data["jobs"][job_id]
        path = DATA / "postings" / f"{re.sub(r'[^A-Za-z0-9-]', '_', job_id)[:150]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = ("title", "company", "source", "also_on", "url", "linkedin", "company_url", "apply_url", "published",
                "category", "workplace_hint", "level", "contract", "snippets", "description")
        path.write_text(json.dumps({**{k: j.get(k) for k in keep},
                                    "locations": [jobs.place(l) for l in j["locations"]]}, ensure_ascii=False,
                                   indent=1), encoding="utf-8")
        return path

    def _log(self, job_id: str, step: str, engine: str) -> Path:
        path = DATA / "logs" / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{slug(job_id, 30)}_{step}_{engine}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _fail(self, job_id: str, bid: str, message: str, log: Path):
        message = "Stopped because the app was closed." if CLOSING.is_set() else message[-500:]
        if LIMIT_HINT.search(message):
            message += " It may have hit its usage limit: retry with the other engine."
        self._update(job_id, bid, state="failed", finished=now(), message=message, log=str(log) if log else "")

    def _analyze(self, job_id: str, bid: str):
        engine = next(b for b in self._store.data["jobs"][job_id]["builds"] if b["bid"] == bid)["engine"]
        log = self._log(job_id, "analyze", engine)
        try:
            schema = DATA / "analyze-schema.json"
            schema.write_text(json.dumps(ANALYZE_SCHEMA), encoding="utf-8")
            posting = self._posting(job_id).relative_to(PROJECT).as_posix()
            ok, reply = run_engine(engine, ANALYZE.format(posting=posting), log, 900, schema)
            questions = parse_json(reply) if ok else {}
            if not isinstance(questions.get("to_ask"), list):
                return self._fail(job_id, bid, reply or "no answer", log)
            if not questions["to_ask"] and questions.get("posting_language") != "German":
                self._update(job_id, bid, state="building", questions=questions,
                             answers={"have": [], "lack": [], "language": "English"})
                return self._build(job_id, bid)
            self._update(job_id, bid, state="questions", questions=questions)
        except Exception as e:
            self._fail(job_id, bid, str(e), log)

    def _build(self, job_id: str, bid: str):
        j = self._store.data["jobs"][job_id]
        b = next(b for b in j["builds"] if b["bid"] == bid)
        log = self._log(job_id, "build", b["engine"])
        try:
            base = PROJECT / "applications" / f"{dt.date.today()}_{slug(j['company'], 25)}_{slug(j['title'])}_{b['engine']}"
            folder, n = base, 2
            while folder.exists():
                folder, n = base.with_name(f"{base.name}_{n}"), n + 1
            rel, a = folder.relative_to(PROJECT).as_posix(), b["answers"]
            prompt = BUILD.format(posting=self._posting(job_id).relative_to(PROJECT).as_posix(), today=dt.date.today(),
                                  have=", ".join(a["have"]) or "none", lack=", ".join(a["lack"]) or "none",
                                  language=a["language"], folder=rel)
            ok, reply = run_engine(b["engine"], prompt, log, 2400)
            pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
            cv = [p for p in pdfs if "_CV_" in p.name]
            letter = [p for p in pdfs if "Cover_Letter" in p.name]
            if not (cv and letter):  # the report's opening says why
                return self._fail(job_id, bid, "The CV and cover-letter PDFs weren't produced. " + reply[:400], log)
            (folder / "Report.md").write_text(reply + "\n", encoding="utf-8")
            files = [{"label": "CV (PDF)", "path": str(cv[0])}, {"label": "Cover letter (PDF)", "path": str(letter[0])}]
            files += [{"label": "Prep plan", "path": str(p)} for p in folder.glob("Prep_*.md")]
            files += [{"label": "Report", "path": str(folder / "Report.md")}]
            today = dt.date.today()
            row = (f"| {cell(j['company'])}, {cell(j['title'])} application set | `{rel}/` | Built {today.day} "
                   f"{today:%b %Y} in {a['language']} with {b['engine'].title()} in the desktop app. Confirmed: "
                   f"{cell(', '.join(a['have'])) or 'none'}; not used: {cell(', '.join(a['lack'])) or 'none'}. |\n")
            with self._profile_lock:
                PROFILE.write_text(insert_rows(PROFILE.read_text(encoding="utf-8"), "## 14.", row), encoding="utf-8")
            unconfirmed = unconfirmed_on_cv(folder, [q["skill"] for q in (b.get("questions") or {}).get("to_ask", [])],
                                            a["have"])
            warning = (f"Check the CV before sending it: it names {', '.join(unconfirmed)}, which you didn't confirm. "
                       "Remove it or confirm it." if unconfirmed else "")
            self._update(job_id, bid, state="done", finished=now(), folder=str(folder), files=files, log=str(log),
                         message=warning)
        except Exception as e:
            self._fail(job_id, bid, str(e), log)


def selftest():
    assert slug("Gebr. Heinemann") == "Gebr_Heinemann" and slug("Werkstudent (m/w/d) KI & Daten") == "Werkstudent_KI_Daten"
    assert slug("Müller & Söhne") == "Mueller_Soehne" and cell("a | b\n c") == "a / b c"
    assert slug("Working Student AI Software Engineer, LangChain") == "Working_Student_AI_Software_Engineer"
    t = dt.datetime(2026, 10, 27, 9)
    assert window_days(None, t) == 7 and window_days("2026-10-27T07:00:00", t) == 2 and window_days("2026-10-01T09:00:00", t) == 7
    assert parse_json('Here:\n```json\n{"to_ask": [], "posting_language": "English"}\n```') == {"to_ask": [], "posting_language": "English"}
    loc = lambda s: dt.datetime.fromisoformat(s).astimezone().replace(tzinfo=None)  # noqa: E731  this PC's time
    at = loc("2026-10-27T12:00:00+01:00")
    assert posted({"posted_at": "2026-10-27T09:10:00+01:00"}, at)[1] == "2 hours ago"
    assert posted({"posted_at": "2026-10-27T10:00:00Z"}, at)[1] == "1 hour ago"
    assert posted({"posted_at": "2026-10-27T11:59:30+01:00"}, at)[1] == "just now"
    assert posted({"posted_at": "2026-10-24T11:00:00+01:00"}, at)[1] == "3 days ago"
    assert posted({"published": "2026-10-26"}, dt.datetime(2026, 10, 27, 1))[1] == "yesterday"
    assert posted({"posted_at": "2026-10-27"}, dt.datetime(2026, 10, 27, 1)) == ("2026-10-27T00:00:00", "today")
    assert posted({}, at) == ("", "") and posted({"published": "soon"}, at) == ("", "")
    assert posted({"posted_at": "2026-10-27T09:10:00+01:00"}, at)[0] > posted({"published": "2026-10-26"}, at)[0]
    assert affordable(["linkedin", "indeed", "stepstone"], {"linkedin_max": 400}, 0.2) == ["indeed", "stepstone"]
    assert affordable(["linkedin", "indeed"], {"linkedin_max": 400}, 5) == ["indeed", "linkedin"]

    profile = ("## 7. Skills\n| a | b |\n\n### Skills on your LinkedIn profile\n- x\n\n## 14. Application materials\n"
               "| M | W | N |\n|---|---|---|\n| CV | here | ok |\n\n---\n\n### Another set\n\nProse.\n\n| X | Y |\n|---|---|\n"
               "| p | q |\n\n## 16. Skills to learn\n| S | A | P | St |\n|---|---|---|---|\n| Kafka | X | plan | Not used |")
    assert "| CV | here | ok |\n| New | f/ | built |\n\n---" in insert_rows(profile, "## 14.", "| New | f/ | built |\n")
    assert insert_rows("# P\n", "## 14.", "| r |\n") == "# P\n\n| r |\n"
    tmp = DATA / "selftest-profile.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(profile, encoding="utf-8")
    record_answers(tmp, "Thales, Werkstudent Data", ["Airflow"], ["Rust"], dt.date(2026, 10, 7))
    out = tmp.read_text(encoding="utf-8")
    tmp.unlink()
    assert "**Confirmed by you, 7 October 2026, for the Thales, Werkstudent Data role (desktop app):** Airflow." in out
    assert out.index("Airflow") < out.index("### Skills on your LinkedIn profile")
    assert out.endswith("| Kafka | X | plan | Not used |\n| Rust | Thales, Werkstudent Data | See the prep plan in this "
                        "application's folder | Not used (confirmed 7 Oct 2026) |\n")

    cvdir = DATA / "selftest-cv"
    cvdir.mkdir(parents=True, exist_ok=True)
    (cvdir / "Veer_Pratap_Singh_CV_X.tex").write_text(r"LangChain, tool calling, Structured Outputs, C\#", encoding="utf-8")
    (cvdir / "Veer_Pratap_Singh_Cover_Letter_X.tex").write_text("I am keen to learn MCP.", encoding="utf-8")
    asked = ["tool calling", "structured outputs", "MCP", "LangChain", "C#", "R"]
    assert unconfirmed_on_cv(cvdir, asked, ["LangChain"]) == ["tool calling", "structured outputs", "C#"]
    shutil.rmtree(cvdir)

    found = {"1": {"id": "1", "description": "", "title": "t"}, "2": {"id": "2", "description": "d"},
             "3": {"id": "3", "description": "fresh", "status": "Closed", "checked": "2026-10-27T09:01"}}
    old = {"1": {"status": "Verified open", "checked": "2026-10-26T08:05", "description": "full", "snippets": {"x": 1}},
           "3": {"status": "Verified open", "checked": "2026-10-26T08:05", "description": "old"}}
    carry_checks(found, old, {"3"})
    assert found["1"]["status"] == "Verified open" and found["1"]["description"] == "full" and found["1"]["snippets"]
    assert "status" not in found["2"] and found["3"]["status"] == "Closed" and found["3"]["description"] == "fresh"

    store = Store(DATA / "selftest-db.json")
    store.data["jobs"] = {
        "1": {"id": "1", "applied": True, "applied_at": "2026-10-21T10:00:00", "builds": [{"bid": "b", "state": "done"}],
              "translation": {"title": "T"}, "first_seen": "2026-10-20T08:00:00", "last_seen": "x"},
        "4": {"id": "4", "first_seen": "2026-10-26T08:00:00", "last_seen": "2026-10-26T08:00:00"},
        "5": {"id": "5", "first_seen": "2026-09-01T08:00:00", "last_seen": "2026-09-01T08:00:00"}}
    store.merge({"1": {"id": "1", "title": "t"}, "2": {"id": "2"}}, "2026-10-27T09:00:00", {"4": "2026-10-27T09:00:00"})
    js = store.data["jobs"]
    assert js["1"]["applied"] and js["1"]["builds"] and js["1"]["first_seen"] == "2026-10-20T08:00:00"
    assert js["1"]["applied_at"] == "2026-10-21T10:00:00" and js["1"]["translation"] == {"title": "T"}
    assert js["2"]["first_seen"] == "2026-10-27T09:00:00" and "4" not in js and "5" not in js
    assert store.data["dropped"] == {"4": "2026-10-27T09:00:00"}
    ag = Agent(store)
    ag.toggle("2", "applied")
    assert js["2"]["applied"] and js["2"]["applied_at"] >= ag._opened
    ag.toggle("2", "applied")
    assert not js["2"]["applied"] and not js["2"]["applied_at"]
    ag._refresh = {"running": True, "message": "", "free_only": True}  # the automatic check is running
    ag.check_jobs(True)
    assert not ag._queued
    ag.check_jobs()
    assert ag._queued and ag.state()["refresh"]["queued"]
    store.path.unlink()

    assert parse_translation("# Working student data (m/f/d)\n\nYour tasks:\n- reports") == \
        ("Working student data (m/f/d)", "Your tasks:\n- reports")
    claude, codex = (engine_cmd(e, DEFAULTS, Path("r.txt"), light=True) for e in ("claude", "codex"))
    assert claude[claude.index("--model") + 1] == "sonnet" and claude[claude.index("--tools") + 1] == ""
    assert codex[codex.index("-s") + 1] == "read-only" and codex[codex.index("-C") + 1] == str(LIGHT)
    print("selftest ok")


def main():
    import webview
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        globals()["_mutex"] = k32.CreateMutexW(None, False, "GermanyJobAgent")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS: two copies would overwrite each other's data
            ctypes.windll.user32.MessageBoxW(None, "Germany Job Agent is already open.", "Germany Job Agent", 0x40)
            return
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GermanyJobAgent")  # own taskbar icon, not Python's
    DATA.mkdir(parents=True, exist_ok=True)
    agent = Agent()
    screen = webview.screens[0]  # fit laptop screens, e.g. 1536 x 864 at 125% scaling
    window = webview.create_window("Germany Job Agent", str(Path(__file__).with_name("ui.html")), js_api=agent,
                                   width=min(1360, screen.width - 60), height=min(880, screen.height - 90),
                                   min_size=(960, 600))
    window.events.closing += lambda: setattr(window, "confirm_close", agent._busy())  # ask only while CVs build
    webview.start(icon=str(Path(__file__).with_name("icon.ico")),
                  localization={"global.quitConfirmation": "CVs are still being built. Closing the app stops them, "
                                                           "and you can retry them later. Close anyway?"})
    CLOSING.set()
    for p in list(RUNNING):
        stop(p)


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
