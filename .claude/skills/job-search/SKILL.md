---
name: job-search
description: Veer Pratap Singh's job-search agent for Germany. Searches LinkedIn (through Apify), the Bundesagentur für Arbeit, freehire and Arbeitnow for working-student (Werkstudent), internship, master's-thesis, research-assistant (HiWi), trainee and junior roles across all of Germany and every tech domain, in English and German. It verifies, scores and ranks the 30 best matches against his profile, writes an Excel workbook, and shows a job board where one click builds the CV and cover letter for a job. Use it whenever Veer asks to find, search for or recommend jobs, openings, Werkstudent positions, internships, theses or HiWi jobs, or asks which jobs to apply for, even if he doesn't name the skill.
---

# Job search agent (Germany)

Find the best open jobs for Veer, rank them honestly against his profile, and put each one a click away from a tailored application (the `job-apply` skill).

The desktop app (`app/job_agent.py`) runs the same fetch, pool and check steps whenever he presses "Check for new jobs", keeps its job list in `jobs/app/`, and builds applications headless with Claude Code or Codex. This skill is the chat version, with the agent's own scoring and the Excel workbook.

## Standing brief (don't ask about these)

- **Where:** all of Germany, every federal state. On-site, hybrid or remote; remote only if residents of Germany can apply. He is open to relocating.
- **Role types:** working student (Werkstudent), internship (Praktikum), master's thesis (Masterarbeit), research assistant (HiWi, SHK, WHK), graduate programme or trainee, and junior or entry-level full-time jobs needing 0–2 years.
- **Domains:** every tech domain, including software, AI/ML, data, cloud and DevOps, security, IoT, embedded and robotics, IT consulting and enterprise IT (SAP, ERP), QA, and research or scientific computing.
- **Languages:** search German and English postings equally.
  - A language requirement never removes a job and never changes its score.
  - Record each requirement as the posting states it, and never say he meets it. His profile says German A2 and English C1.
- **Freshness:** prefer the last 48 hours. The search covers 7 days; include older jobs only if they are verifiably open and a strong match.
- **Result:** the 30 best verified matches. If fewer qualify, say how many and why. Never pad the list with invented or unchecked data.
- **Exclude:**
  - closed or expired jobs, and duplicates
  - recruiting agencies and staffing ads without a concrete vacancy, and inactive company pages
  - senior roles, roles needing 3+ years, and roles needing a degree or PhD he doesn't have
  - non-tech roles, and remote roles closed to residents of Germany
  - jobs he already applied to (the script finds them from his tailored CV file names)
- Ask a question only if something essential is missing.

## Source of truth

`Veer_Pratap_Singh_Complete_Profile.md`:
- Read sections 2–7, 11 and 16. Section 7 lists his confirmed skills; section 16 lists the skills he said he lacks.
- Constraints that affect eligibility:
  - M.Sc. Data and Knowledge Engineering at OVGU Magdeburg, expected March 2027.
  - Up to 20 hours a week during the semester; available immediately.
  - A full-time job after graduation needs a change from a student to a work residence permit, so mark those jobs "Conditional".

## Workflow (OUT = `jobs/<today>`)

1. **Profile summary (Output A):** five bullets covering his strongest skills, best pathways, suitable job families, most marketable experience and constraints.
2. **Search.**
   - Call the Apify actor `cheap_scraper/linkedin-job-scraper` with `.claude/skills/job-search/search_input.json` as the input. Edit the keyword list only if Veer asks for something narrower.
   - Use `callOptions: {"maxTotalChargeUsd": 1.2, "timeout": 3600}` and `waitSecs: 0`, then call get-actor-run with `waitSecs: 45` until the status is SUCCEEDED (about 10 minutes).
   - Cost: about $0.0007 per job on Apify's free tier, so a full run of 1,500 jobs costs about $1.05.
   - While it runs, search the free sources: `python .claude/skills/job-search/scripts/jobs.py fetch`. It takes about a minute and costs nothing.
     - **Bundesagentur für Arbeit:** Germany's largest job database, searched with the same keywords.
     - **freehire:** company career sites such as JOIN, Personio, Softgarden and Greenhouse.
     - **Arbeitnow:** a German job board.
     - It keeps tech jobs only and writes `OUT/free_sources.json`. Without Apify (Codex, or no credit left), run only this step and pool its file alone.
     - With an Apify token in the `APIFY_TOKEN` environment variable, `--sources ba,freehire,arbeitnow,indeed,stepstone` adds Indeed (about $0.04 a run) and StepStone (about $0.15).
     - `jobspy_indeed` and `jobspy_linkedin` add Indeed and LinkedIn for free through the JobSpy library, run from this PC. LinkedIn refuses after a few hundred jobs, so keep those runs small; the script then pauses LinkedIn for 30 minutes.
3. **Download.**
   - Call get-dataset-items with the datasetId, `limit` set to the item count, and `fields: "jobId,jobTitle,companyName,location,publishedAt,postedTime,experienceLevel,contractType,applicationsCount,applyType,keywordMatchScorePercentage,dynamicFilterMatch,salaryInfo,sector,searchString,yearsOfExperience,jobDescription"`.
   - The result is too large for the chat, so Claude Code saves it to a file and prints the path. Don't read the file.
   - If it comes back inline (a tiny search), save the items to a JSON file with Write.
4. **Pool.**
   - Run `python .claude/skills/job-search/scripts/jobs.py pool "<saved file>" jobs/<today>/free_sources.json`.
   - It prints the counts, how many jobs each filter removed, the jobs skipped because he already applied, and the top candidates with a rough pre-score, plus the best of each role type and of each free source.
   - IDs starting `ba-`, `fh-` and `an-` come from the Bundesagentur, freehire and Arbeitnow; plain numbers are LinkedIn IDs.
   - The same job on several sources becomes one entry: the LinkedIn copy is kept, and a company apply link found on another source is carried over.
   - A run stops at its maxItems cap, and each job counts only for the first search that found it. If the output lists "Searches that added no jobs", run a second pass with only those keywords (and any regional URLs that returned nothing), with `maxItems` 800 and `maxTotalChargeUsd` 0.6.
   - Download the second pass too, then rerun pool with both files. A rerun keeps everything details has already checked.
   - "[applied here]" marks a company he has applied to before. Check those against profile section 14: a German repost of a job he applied to in English isn't caught automatically.
5. **Read the best candidates.**
   - Pick 40–50 jobs: the strongest pre-scores, plus the best few from each group (Werkstudent and internship, thesis and research, junior and trainee), from smaller cities and from less common domains. This stops the shortlist from collapsing into one category.
   - Skip obvious non-matches, such as sales, marketing or HR roles that only mention data.
   - Run `python .claude/skills/job-search/scripts/jobs.py details <id> <id> ...`. For each job it prints whether it's open or closed on its source, the apply route, and the posting's tasks, requirements, language, experience, hours, start and salary lines.
   - Bundesagentur search results carry no description, so details fetches it. Until then those jobs pre-score low; judge them by title.
   - LinkedIn hides company apply links from visitors who aren't logged in. A LinkedIn job gets a company link only when the same job was found on freehire; otherwise its Apply link is the LinkedIn posting.
   - When a job's requirements aren't printed, find its requirements passage in `pool.json` (`description` field) rather than guessing.
6. **Score and export.**
   - Score every job you read (scoring below), then write `OUT/picks.json` with the best 35–40 (format below).
   - Run `python .claude/skills/job-search/scripts/jobs.py export`. It drops closed jobs, ranks the rest and keeps the top 30.
   - It writes `jobs.json` (the full postings, read by `/job-apply`), `Veer_Job_Search_<date>.xlsx` and `job_board.html`, and prints the chat table.
7. **Job board.**
   - If the session has the show_widget tool, read `OUT/job_board.html` and pass its contents unchanged as the widget code.
   - Each "Build CV and cover letter" button sends `/job-apply job N from jobs/<date>/jobs.json (…)`, which starts the CV, cover letter and prep plan for that job.
   - Without the widget (VS Code, Codex), tell Veer to type `/job-apply N`.
8. **Report** in chat (see the end of this file).

## Scoring (0–100)

| Factor | Max | How to score |
|---|---|---|
| Technical skills and stack | 30 | Share of the must-have requirements covered by his section-7 skills. Transferable work counts partly, nice-to-haves add little, and keyword overlap alone never counts |
| Experience and seniority | 25 | About 25 for a student or entry role he exceeds, about 20 for "up to 1 year", about 12 for 2 years. Score lower if the tasks need more than his 14 months as a software engineer plus internships |
| Education and academic fit | 15 | Subject and level against his M.Sc. (expected March 2027) and B.Tech in CS (AI and ML). Full-time jobs that need a finished master's get partial credit |
| Career-development value | 15 | Learning value and fit with his AI, data and cloud path, judged within the role type. A HiWi job isn't worth less just because it is a HiWi job |
| Employment type and eligibility | 10 | Fit with his student status, 20 hours a week and graduation in March 2027. Score lower for long minimum durations, full-time starts before graduation, and full-time internships, which count toward the student work-day limit unless mandatory |
| Freshness | 5 | Up to 2 days: 5. Up to 3 days: 4. Up to 5 days: 3. Up to 7 days: 2. Older: 0 |

Language requirements are never scored. For eligibility, write "Eligible", "Conditional: <the condition>" or "Needs verification".

## picks.json

```json
{"summary": {"searches": 69, "window": "Posted in the last 7 days", "cost": "$1.05",
             "tools": "LinkedIn through Apify; Bundesagentur für Arbeit, freehire and Arbeitnow APIs; source and company pages for verification",
             "limitations": "No XING; about 20 LinkedIn results per search; 7-day window"},
 "picks": [{"id": "4480079459",
            "scores": {"tech": 24, "experience": 22, "education": 13, "career": 13, "eligibility": 9, "freshness": 4},
            "employment_type": "Werkstudent", "domain": "AI/ML", "workplace": "Hybrid",
            "experience": "No professional experience required", "language": "German C1 required; English good",
            "salary": "Not stated", "why": "…", "missing": "…", "eligibility": "Eligible"}]}
```

- `employment_type` is one of Werkstudent, Internship, Thesis, Research, Trainee or Full-time. It decides which sheet the job lands on.
- `why`: one or two sentences with specific evidence from his profile (project, job, number).
- `missing`: real gaps from the posting's must-haves, or "None".
- `experience`, `language` and `salary`: as the posting states them, otherwise "Not stated".

## Report in chat

- **Output A:** the profile summary.
- **Output B:** the table that export prints. The full fields are in the workbook and on the job board.
- **Output C:** a link to the workbook.
- **Output D:**
  1. the five jobs to apply to first, with one reason each
  2. his strongest category right now
  3. where he has a real competitive edge
  4. skill gaps that repeat across the postings
  5. concrete CV changes for these vacancies
- **Coverage:** searches run, jobs retrieved per source, unique, read and verified, the Apify cost, and the limits.
  - Searched: LinkedIn's public search (about 20 results per search), the Bundesagentur für Arbeit, freehire and Arbeitnow, over a 7-day window.
  - Not searched directly: XING, and Indeed and StepStone unless the fetch ran with an Apify token.
- Never promise interviews, ATS scores or outcomes.
