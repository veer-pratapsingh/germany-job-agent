---
name: job-apply
description: Veer Pratap Singh's job-application agent. Given a job link or a pasted job description, it asks Veer which of the posting's skills he has that aren't in his profile yet, then writes a tailored CV and a matching one-page cover letter (LaTeX, compiled to upload-ready PDFs) plus a study plan for the skills he doesn't have. Use it whenever Veer shares a job link, pastes a job ad or description, gives a job number from his job search (`/job-apply 7`, or a click on the job board), or asks for a CV, resume, cover letter, motivation letter or application for a role or company (working student / Werkstudent, internship or full-time), even if he only pastes the posting. Mirrors the posting's keywords wherever his confirmed experience supports them, compiles and checks every PDF, and reports the gaps.
---

# Job application agent

For one posting, produce these files in the project folder (`D:\Veer-Job-Apply-2026-Oct`), or in the folder the desktop app names:

1. `Veer_Pratap_Singh_CV_<Company>_<Role>.tex` and `.pdf`: at most 2 A4 pages.
2. `Veer_Pratap_Singh_Cover_Letter_<Company>_<Role>.tex` and `.pdf`: 1 page.
3. `Prep_<Company>_<Role>.md`: interview preparation, plus a study plan for skills the posting wants that he doesn't have yet.

Use short ASCII names with underscores, for example `Veer_Pratap_Singh_CV_SAP_Data_Analyst`. The ProSiebenSat.1 set (`*_ProSiebenSat1_Data_Analytics*`) is the reference example of all three.

## Files (paths relative to the project folder)

- `Veer_Pratap_Singh_Complete_Profile.md` is the source of truth: every fact, number, date, skill and bullet pool.
  - Read all of it each time.
  - Section 7 holds his skills, including ones he confirmed when asked.
  - Section 15 (open items) says which version of a conflicting fact the CVs use.
  - Section 16 lists skills he said he doesn't have yet.
- `Veer_Pratap_Singh_CV.tex` is the generic CV. Copy its preamble and macros unchanged and reuse its section order.
- `Veer_Pratap_Singh_Cover_Letter_ProSiebenSat1_Data_Analytics.tex` is the cover-letter base. Copy its preamble, header and closing, and rewrite the body.
- `.claude/skills/job-apply/scripts/build_cv.py` compiles and checks a CV or letter (step 9).
- `jobs/<date>/jobs.json` is written by the `job-search` skill: the ranked jobs, each with the full posting text, links and the search's notes.
- `jobs/app/postings/<id>.json` is written by the desktop app (`app/job_agent.py`): one job, with the same fields.

When Veer shares new facts (a project, award, skill or date change), add them to the profile first and note any conflict in section 15. A stale profile produces CVs that contradict each other.

## Ask before using a skill that isn't in the profile

Veer decides what goes on his CV. Before writing anything, ask him about the posting's important skills, tools and methods that his profile doesn't show. Pick the 3–8 that matter most, must-haves first.

- **How to ask:** use the AskUserQuestion tool when the session has it. Make it multi-select, with up to four skills per question (split longer lists over several questions). Ask whether he has actually used each one, in a job, a course or a project, well enough to answer interview questions on it. Without the tool, ask the same in chat. Either way, wait for his answer before writing.
- **Yes:** add the skill to profile section 7 with today's date ("confirmed by Veer, <date>"). If he mentions where he used it, record that too, because it helps the interview prep and later CVs. From then on it counts as a supported skill: use the posting's exact wording in the Skills section, and in the summary or letter where it fits naturally.
- **No:** leave it off the CV completely. Record it in profile section 16 and cover it in the prep plan. In the cover letter, one honest sentence of willingness to learn a missing must-have is allowed ("I am keen to learn R…"). Point that sentence out in the report so he can remove it.
- **Don't re-ask** about a skill already in section 7 or already declined in section 16, unless he says it has changed.
- **Not skills:** degrees, certifications, years of experience, job titles and language levels stay exactly as the profile says. Don't ask about them as skills; handle those gaps in the prep plan.
- **Unconfirmed means absent:** never write a skill he hasn't confirmed anywhere on the CV.

## Workflow

1. **Get the posting.**
   - **Job number from a job search** (`/job-apply 7`, "job 7", or a job-board button that names `jobs/<date>/jobs.json`):
     - Take the job with that rank from the named file, or else from the newest `jobs/<date>/jobs.json`.
     - Its `description` field holds the full posting. Its other fields hold the links and the search's notes: workplace, language, experience, salary, eligibility and missing skills.
     - Don't fetch the page again unless the description is empty.
     - Start by naming the job (title, company and city) so he can see it's the right one.
   - **Posting file from the desktop app** (`jobs/app/postings/<id>.json`): read it like a jobs.json entry. The app runs this skill headless with Claude Code or Codex. It asks the step-4 questions and records the answers in the profile itself, names the output folder, and saves the step-11 report; its prompt says which steps to do.
   - **URL:** read the page with whatever fetch tool the session has (WebFetch, the web-fetch agent, or the built-in browser's `get_page_text`; LinkedIn job pages need the built-in browser, where Veer may be signed in). If the page fails or needs a login, ask him to paste the text.
   - If the posting is in German, ask once (in the same question round as step 4 when possible) whether he wants the CV and letter in English or German. Default to English, since his German is A2.

2. **Analyse it.** Note:
   - the exact job title, company, contact person, location, start date, duration and hours
   - the must-have and nice-to-have skills, and the tasks
   - the domain and language requirements
   - the words the posting repeats, and its spelling (for example US "modeling" or UK "modelling")

3. **Build the keyword map** of the 15–30 terms an ATS and a recruiter look for, and put each in one group:
   - **Supported:** in the profile. Use the posting's exact wording.
   - **Transferable:** his real work is the same thing under another name, so describe it in the posting's language. Example: ranking satisfaction drivers by feature importance is "driver analysis".
   - **To ask:** an important skill, tool or method that isn't in the profile.
   - **Prep only:** gaps that aren't skills (language level, years of experience, degree), plus minor nice-to-haves.

4. **Ask about the "To ask" items** (see above), wait for the answers, and update the profile: confirmed skills into section 7, declined ones into section 16.

5. **Write the CV.**
   - **Header:** show Veer's name and plain-text contact details only; do not add a job-title/degree tagline below his name.
   - **Summary (5–7 lines):** lead with the strongest evidence for the posting's top three needs. Mention the schubKI Founders' Award when the role values AI or innovation.
   - **Skills:** 4–5 groups in the posting's order of priority and in its terms, with supported and confirmed skills only.
   - **Experience:** Swaja Robotics, then talk2move, then UMUN Tech. Pick and reword bullets from the profile's bullet pool to match the posting's tasks, and keep every number exactly as the profile states it. Confirmed skills only go into a bullet if Veer said he used them in that job.
   - **Projects:** the 2–4 most relevant, each as `\textbf{Title.} One short paragraph. \textit{Tech list.}` Use paragraphs, not bullets; no dates; no team or university labels; only the details that matter for this job.
   - **Education:** modules and coursework chosen for relevance, from the profile's lists.
   - **Certifications, Leadership & Awards, Languages:** keep all three, with certifications reordered by relevance.

6. **Write the cover letter** (one page, about 300–350 words, English unless he chose German):
   - **Header:** the base letter's header; the company, the contact person (or "Hiring Team") and the city; place and today's date; a bold subject line with the exact job title.
   - **Salutation:** "Dear <first name>," when the company says it works on a first-name basis; "Dear Ms./Mr. <surname>," when the full name is known; otherwise "Dear Hiring Team,".
   - **Paragraph 1:** why this role and company, tied to what they actually do.
   - **Paragraph 2:** the two strongest pieces of evidence, mapped to the posting's main tasks, with numbers. University team projects are written as team work ("I worked in a team on…", "we identified…").
   - **Paragraph 3:** industry experience (Swaja Robotics) and why he cares about their domain.
   - **Paragraph 4 (optional):** one honest sentence about a missing must-have ("…and I am keen to learn R"), plus the AI award if relevant.
   - **Closing:** start date and hours if the posting specifies them (he is available immediately, up to 20 hours a week), then "I look forward to discussing…", "Kind regards," and his name.

7. **Write the prep plan** `Prep_<Company>_<Role>.md`:
   - **Opening section, "Your answers":** the skills he confirmed (now on the CV) and the skills he doesn't have (left off the CV).
   - **One section per missing skill, must-haves first.** For each:
     - what the employer wants, and why it matters in this role
     - the fastest credible way to learn it, with a time estimate
     - one mini-project (data source, steps, deliverable: a GitHub repository with a short README and results); reusing data he already knows makes it faster
     - 3–5 likely interview questions
   - **Confirmed skills he hasn't shown on paper yet:** interview questions to prepare.
   - **Other gaps:** language level, degree requirements and similar, each with how to address it honestly.
   - **Questions on his existing CV**, with answer hints taken from the profile.
   - **A 30-second pitch** for this role.
   - **A week-by-week plan** that fits the time until the start date.
   - **Final line:** when he finishes a mini-project, he should say so, and the skill will be added to his profile and future CVs.

8. **Profile:** make sure section 7 and section 16 reflect his answers, and add any new conflict to section 15.

9. **Build and check both PDFs:**
   ```
   python .claude/skills/job-apply/scripts/build_cv.py <cv.tex> --keywords "kw1; kw2; ..."
   python .claude/skills/job-apply/scripts/build_cv.py <letter.tex> --max-pages 1 --keywords "<job title>; <2-3 key terms>"
   ```
   Pass the supported, transferable and confirmed keywords; matching is whole-word, so "R" works. The script fails on compile errors, too many pages, lines running into the margin, active content, missing keywords, or a failed fact check. Fix and rebuild until both pass. If the CV runs to a third page, cut the least relevant material first, never the posting's key terms.
   - **Fact check:** every number in the PDF must also appear in the profile, so a mistyped or invented figure ("40%" where the profile says 30%) fails the build. Scales count as equal ("130k" = "130,000"), and dates, years and the letter's address are skipped.
   - **`--allow "15; 6"`:** for numbers quoted from the posting, such as its hours, duration or a reference number. Never use it for a claim about Veer: correct the claim, or add the fact to the profile first if he has just told you.

10. **Look at the pages.** Render them (for example `pdftoppm -r 70 -png <pdf> <prefix>`) and check for single words wrapped onto their own line, tech names broken by hyphenation (add them to `\hyphenation{...}`) and large empty gaps.

11. **Report briefly in chat:**
    - links to the three files
    - the main keywords mirrored
    - the skills he confirmed and where they appear
    - the skills left off, with the first thing to study
    - any willingness-to-learn sentence in the letter
    - any open item from profile section 15 that matters, such as enrolment end versus duration, or location
    - whether the fit is strong or weak

## Veer's standing preferences (from his past edits)

- Ask before adding any skill that isn't in his profile. Confirmed skills go on the CV normally; declined skills stay off. No "Currently learning" line.
- Projects as paragraphs, not bullets; no dates and no team or university labels in project titles on the CV.
- Only the relevant details: concise beats exhaustive.
- CV header: show the name and contact details only. Do not add a role-title or degree tagline below the name, including on tailored CVs.
- No availability line and no semester count on the CV. The cover letter may state the start date and hours.
- Swaja Robotics location is just "India".
- UMUN Tech: Technology Intern, Jul 2023 – Apr 2024, framed as full-stack web development, without "99% uptime".
- The IIT Kanpur and Pantech internships stay off unless a job clearly calls for them.
- Contact details as plain text, with no links. SAP SuccessFactors and similar portals reject PDFs with "active content".
- Location: Magdeburg, Germany, unless Veer says otherwise.

## Format rules, and why

- Keep the base preambles as they are:
  - `\pdfminorversion=4` and `\pdfobjcompresslevel=0` with no hyperref, so the PDFs are portal-safe.
  - `glyphtounicode`, so an ATS can search the text.
  - the CV's `\experienceitem` macro without `\\[2pt]`, which used to leave a blank line before each list.
  - `\pagestyle{empty}` on the letter, so it has no page number.
- Escape LaTeX specials: `\&`, `\%`, `C\#`, `\textasciitilde`, and `--` for ranges.
- Single column with the standard section names (Summary, Skills, Experience, Projects, Education, Certifications, Leadership & Awards, Languages), because ATS parsers map those.
- Match the posting's spelling of every keyword (US or UK). An ATS treats "modeling" and "modelling" as different words.
