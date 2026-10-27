# Veer's job-application workspace (instructions for Codex and other coding agents)

- `Veer_Pratap_Singh_Complete_Profile.md` is the single source of truth about Veer: facts, numbers, dates, skills and open items. Update it whenever he shares new information.
- When Veer shares a job link, pastes a job description, or asks for a CV, resume or cover letter, read `.claude/skills/job-apply/SKILL.md` and follow it step by step. It is the full workflow: tailored CV, one-page cover letter and prep plan, built and checked as PDFs. It is written for any agent:
  - Where it mentions a question tool, ask in chat and wait for his answer.
  - If you can't open the job link, ask him to paste the posting.
- To find jobs, follow `.claude/skills/job-search/SKILL.md`. Its LinkedIn search needs the Apify MCP server. Without it, use the free sources alone: `python .claude/skills/job-search/scripts/jobs.py fetch`, then `pool jobs/<date>/free_sources.json`, and continue with details and export. When Veer gives a job number, read that job from the newest `jobs/<date>/jobs.json`, which holds the full posting.
- The desktop app (`app/job_agent.py`) runs `codex exec` (or Claude Code) headless with a prompt that names a posting file in `jobs/app/postings/` and an output folder in `applications/`. In those runs, follow the prompt: it has already asked Veer the skill questions, and the app edits the profile itself.
- Before putting any skill that isn't in his profile on a CV, ask Veer whether he has it. If yes, add it to profile section 7 and use it. If no, leave it off the CV and record it in profile section 16 and the prep plan.
- PDFs must contain no links or other active content, because SAP SuccessFactors-style portals reject them. Build and check with `python .claude/skills/job-apply/scripts/build_cv.py <file.tex>`. Add `--max-pages 1` for the cover letter.
- Requirements on PATH: Python 3, `pdflatex` (MiKTeX or TeX Live) and `pdftotext` (Poppler).
