# Germany Job Agent

A Windows desktop app that finds new tech jobs in Germany each time you press "Check for new jobs". With one click, it also writes a tailored CV, cover letter and interview-prep plan for any of them, using Claude Code or Codex. You pick the engine per job.

It covers working-student (Werkstudent), internship, master's-thesis, research-assistant (HiWi), trainee and junior roles in every tech domain, in English and German postings.

## What it does

- **Searches six sources** in parallel:

  | Source | What it covers | Cost |
  |---|---|---|
  | Bundesagentur für Arbeit | Germany's largest job database | Free |
  | freehire | Company career sites on Personio, JOIN, Greenhouse, Softgarden and others | Free (personal use) |
  | Arbeitnow | A German job board | Free |
  | LinkedIn | Through Apify | About $0.28 per check (400 jobs) |
  | Indeed | Through Apify | About $0.04 per check |
  | StepStone | Through Apify | About $0.15 per check |

  Each source is searched back to its own last search (plus a day of overlap), up to 7 days.

- **Checks the free sources by itself** each time the app opens. LinkedIn, Indeed and StepStone cost Apify credit, so they run only when you press **Check for new jobs**.

- **Keeps only real, suitable vacancies.** It drops:
  - recruiting agencies and inactive company pages
  - senior roles and roles needing 3+ years of experience
  - non-tech roles
  - closed postings
  - duplicates across sources (merged into one entry)
  - jobs you already have a tailored CV for

- **Checks the best jobs on their source.** It confirms they're still open and finds the company's own apply page. Any other job is checked the moment you open it.

- **Shows each job in full:**
  - the posting link and the company apply link
  - what they want and what you'd do
  - hours, language, salary and start date
  - the full text

- **Builds the application** with the engine you pick (Claude Code or Codex):
  1. The engine reads the posting and your profile, then lists the skills the posting wants that your profile doesn't show.
  2. You tick the ones you've really used. Unticked skills stay off the CV and go into the prep plan.
  3. It writes the CV, the cover letter and the prep plan into `applications/<date>_<Company>_<Role>_<engine>/`.
  4. It compiles and checks the PDFs.

  Several builds can run at the same time. If one fails, for example because the engine hit its usage limit, the app offers "Retry with" the other engine.

- **Checks every PDF before you upload it:**
  - the page count
  - no links or other active content (SAP SuccessFactors-style portals reject them)
  - the posting's keywords are present
  - every number on the CV appears in your profile

## Requirements

- Windows 10 or 11. The WebView2 runtime is built into Windows 11.
- Python 3.10 or later.
- MiKTeX or TeX Live, for `pdflatex`.
- Poppler, for `pdftotext` and `pdftoppm`.
- [Claude Code](https://docs.claude.com/en/docs/claude-code) and/or the [Codex CLI](https://github.com/openai/codex), installed and signed in.
- Optional: an [Apify](https://apify.com) account for LinkedIn, Indeed and StepStone. The free plan includes $5 of credit a month.

## Setup

```
python app/install.py
```

This installs `pywebview` and creates a "Germany Job Agent" shortcut on the desktop and in the Start menu.

The app needs these files in the project folder. They're personal, so they aren't in this repository:

- a profile in Markdown (`Veer_Pratap_Singh_Complete_Profile.md`): section 7 holds skills, section 14 application materials, section 16 skills to learn
- a base CV (`Veer_Pratap_Singh_CV.tex`)
- a cover-letter base (`Veer_Pratap_Singh_Cover_Letter_ProSiebenSat1_Data_Analytics.tex`)

To use the app for someone else, change those names in `app/job_agent.py` and `.claude/skills/job-apply/SKILL.md`.

## Using it

1. Open the app. It checks the free sources by itself. Press **Check for new jobs** to add LinkedIn, Indeed and StepStone; if you press it during the automatic check, the full check starts right after. "NEW" marks jobs found since you opened the app.
2. Optional: under **Settings**, paste your Apify API token and press **Test**. It shows how much of the month's credit is left.
   - Before each check, the app reads the remaining credit and skips any paid source whose run wouldn't fit.
3. Filter by job type, source, "New only" or "Verified open", or search by title, company or city.
   - Sort by **Best match first** or **Newest first**. The app remembers the choice.
   - Each job shows how long ago it was posted: to the minute where the source gives a time (freehire, Arbeitnow, StepStone, Indeed and fresh LinkedIn jobs), otherwise to the day.
   - The list shows 200 jobs at a time; **Show more** adds the next 200.
4. Open a job, pick **Claude** or **Codex**, and press **Create CV + cover letter**.
   - For a German posting, **Translate to English** translates it with the engine you picked: about 15 seconds with Codex, under a minute with Claude. The translation is kept with the job.
5. Answer the skill questions. The finished files open from the job's panel.
6. After applying, press **Mark as applied**. The job moves to the **Applied** tab, which lists your applications with the date, newest first.

Settings also hold the engine models and effort levels, the number of builds that run at once, and how many jobs each check verifies.

## How it's built

| Part | What it does |
|---|---|
| `app/job_agent.py` | The window (pywebview), the job database (`jobs/app/db.json`), the background checks, and the headless Claude Code and Codex runs |
| `app/ui.html` | The interface |
| `.claude/skills/job-search/scripts/jobs.py` | Sources, filtering, de-duplication, scoring, open/closed checks and the Excel export |
| `.claude/skills/job-apply/SKILL.md` | The CV and cover-letter workflow the engines follow |
| `.claude/skills/job-apply/scripts/build_cv.py` | Compiles and checks a CV or letter |

The same pipeline runs from the command line, without the app:

```
python .claude/skills/job-search/scripts/jobs.py fetch
python .claude/skills/job-search/scripts/jobs.py pool jobs/<date>/free_sources.json
```

Each script has a self-test: `python app/job_agent.py --selftest`, and the same flag on `jobs.py` and `build_cv.py`.

## Privacy

- **Personal files stay local.** The profile, CVs, letters, prep plans and job data are excluded by `.gitignore`.
- **The Apify token stays on your PC.** It's saved in `%APPDATA%\GermanyJobAgent\settings.json`, outside the project folder. It's sent only to `api.apify.com`, in a request header.
- **freehire's free API is for personal, non-commercial use.**

## Limits

- XING isn't searched.
- LinkedIn hides company apply links from visitors who aren't logged in. A LinkedIn job gets a company link only when another source has the same job.
- Indeed and StepStone pages block scripts. Their jobs show as "Listed today" (found in that day's live search), not "Verified open".
- The match score is a quick keyword-based estimate to sort the list, not an assessment of your fit.
