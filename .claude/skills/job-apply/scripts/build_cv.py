"""Compile a tailored CV (.tex) to PDF and check that it is ready to upload.

usage: python build_cv.py CV.tex [--keywords "kw1; kw2; ..."] [--max-pages 2] [--allow "n1; n2"]
       python build_cv.py --selftest

Checks: it compiles (two pdflatex passes), page count, lines running into the margin,
PDF "active content" (links and actions that portals such as SAP SuccessFactors reject),
a fact check (every number in the PDF must also appear in Veer's profile; --allow lists numbers
quoted from the posting, such as its hours) and, optionally, which keywords appear in the PDF text
an ATS reads. Exits 1 if any check fails.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ACTIVE_KEYS = [b"/URI", b"/Link", b"/Annots", b"/OpenAction", b"/AA", b"/JavaScript", b"/JS",
               b"/Launch", b"/EmbeddedFile", b"/AcroForm", b"/XFA", b"/RichMedia", b"/SubmitForm",
               b"/GoToR", b"/ImportData"]
PROFILE = Path(__file__).resolve().parents[4] / "Veer_Pratap_Singh_Complete_Profile.md"
MONTHS = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?|januar|februar|märz|mai|juni|juli|"
          r"oktober|dezember")
# dates, and the postcode and house number of a letter's address, are copied from the posting, not claims
NOT_CLAIMS = re.compile(rf"\b\d{{1,2}}\.?\s+(?:{MONTHS})\s+\d{{4}}\b|\b\d{{1,2}}\.\d{{1,2}}\.\d{{2,4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b|"
                        r"\b\d{5}(?=\s+[A-ZÄÖÜ])|(?:stra(?:ß|ss)e|str\.|weg|allee|platz|ring|damm|gasse)\s+\d+[a-z]?\b",
                        re.I)
SCALE = {"k": 1e3, "tsd": 1e3, "thousand": 1e3, "m": 1e6, "mio": 1e6, "million": 1e6, "millionen": 1e6,
         "bn": 1e9, "billion": 1e9, "mrd": 1e9}


def pdf_text_bytes(pdf: bytes) -> bytes:
    """Raw PDF plus every decompressed stream, so keys inside object streams are visible too."""
    text = pdf
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            text += zlib.decompress(m.group(1))
        except zlib.error:
            pass
    return text


def active_content(pdf: bytes) -> dict:
    text = pdf_text_bytes(pdf)
    hits = {k.decode(): len(re.findall(re.escape(k) + rb"(?![A-Za-z])", text)) for k in ACTIVE_KEYS}
    return {k: v for k, v in hits.items() if v}


def page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", pdf_text_bytes(pdf)))


def norm(s: str) -> str:
    """Lowercase, unify dashes and quotes, collapse whitespace."""
    for a, b in (("–", "-"), ("—", "-"), ("−", "-"), ("’", "'"), ("­", "")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def pdf_text(pdf_path: Path) -> str:
    return subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf_path), "-"], capture_output=True,
                          encoding="utf-8", errors="replace").stdout


def keyword_check(out: str, keywords: list) -> tuple:
    # TeX hyphenates at line ends: test the text with the break removed and with the hyphen kept
    variants = [norm(re.sub(r"-\s*\n\s*", "", out)), norm(re.sub(r"-\s*\n\s*", "-", out))]
    found = [k for k in keywords if any(has_term(v, k) for v in variants)]
    return found, [k for k in keywords if k not in found]


def numbers(text: str) -> set:
    """Each number as a value, so "130k" and "130,000" compare equal, as do "10.6 million" and "10.6M".
    Dates, years and letter addresses are skipped."""
    found = set()
    for m in re.finditer(r"(?<![\w.])(\d+(?:[.,]\d+)*)(?:\s?([a-z]+)\b)?", NOT_CLAIMS.sub(" ", text), re.I):
        s, unit = m.group(1), (m.group(2) or "").lower().rstrip(".")
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s) else s.replace(",", ".")
        if re.fullmatch(r"(?:19|20)\d\d", s) or s.count(".") > 1:
            continue
        value = float(s) * SCALE.get(unit, 1)
        found.add(f"{value:.6f}".rstrip("0").rstrip("."))
    return found


def fact_check(text: str, profile: str, allow: str = "") -> list:
    """Numbers in the PDF that the profile never mentions: an invented or mistyped figure, or one taken
    from the posting (pass those in allow)."""
    return sorted(numbers(text) - numbers(profile) - numbers(allow), key=lambda s: (len(s), s))


def has_term(text: str, term: str) -> bool:
    """Whole-word match, so a short term like "R" or "SQL" isn't found inside other words."""
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(term)) + r"(?![a-z0-9])", text) is not None


def build(tex: Path, max_pages: int, keywords: list, allow: str = "", profile: Path = PROFILE) -> bool:
    if not shutil.which("pdflatex"):
        print("pdflatex not found (install MiKTeX or TeX Live)")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        for _ in range(2):  # second pass settles anything the first pass wrote to .aux/.out
            r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                                f"-output-directory={tmp}", tex.name],
                               cwd=tex.parent, capture_output=True, encoding="utf-8", errors="replace")
            log = Path(tmp, tex.stem + ".log")
            log_text = log.read_text(encoding="latin-1") if log.exists() else r.stdout
            if r.returncode != 0:
                print("COMPILE FAILED")
                print("\n".join(l for l in log_text.splitlines() if l.startswith("!") or l.startswith("l."))[:2000])
                return False
        pdf_path = tex.with_suffix(".pdf")
        shutil.copyfile(Path(tmp, tex.stem + ".pdf"), pdf_path)

    pdf = pdf_path.read_bytes()
    ok = True
    pages = page_count(pdf)
    print(f"PDF: {pdf_path}")
    print(f"Pages: {pages} (max {max_pages})" + ("" if pages <= max_pages else "  <-- TOO LONG"))
    ok &= pages <= max_pages

    overfull = re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\) in paragraph at lines (\d+)--(\d+)", log_text)
    overfull = [o for o in overfull if float(o[0]) > 0.5]
    print("Lines into the margin: " + ("none" if not overfull else
          ", ".join(f"tex lines {a}-{b} ({w}pt)" for w, a, b in overfull)))
    ok &= not overfull

    active = active_content(pdf)
    print("Active content: " + ("none" if not active else f"{active}  <-- portals will reject this"))
    ok &= not active

    text = pdf_text(pdf_path) if shutil.which("pdftotext") else None
    if text is None or not profile.exists():
        print("Fact check: skipped (" + ("pdftotext not found" if text is None else f"no profile at {profile}") + ")")
    else:
        unknown = fact_check(text, profile.read_text(encoding="utf-8"), allow)
        print("Numbers not in the profile: " + ("none" if not unknown else ", ".join(unknown) +
              "  <-- fix them, or pass --allow for numbers quoted from the posting"))
        ok &= not unknown

    if keywords:
        if text is None:
            print("Keywords: skipped (pdftotext not found)")
        else:
            found, missing = keyword_check(text, keywords)
            print(f"Keywords found: {len(found)}/{len(keywords)}")
            if missing:
                print("Missing: " + "; ".join(missing))
            ok &= not missing
    print("RESULT: " + ("PASS" if ok else "FIX AND REBUILD"))
    return ok


def selftest():
    assert active_content(b"<< /Type /Annot /Subtype /Link /A << /S /URI /URI (x) >> >>") == {"/URI": 2, "/Link": 1}
    assert active_content(b"<< /Type /Page /Annot >>") == {}
    assert page_count(b"<< /Type /Pages /Kids [1 0 R 2 0 R] >> << /Type /Page >> << /Type/Page >>") == 2
    assert norm("Driver–Analysis\n   TOOL ") == "driver-analysis tool"
    assert has_term("currently learning: r, regression", "R")
    assert not has_term("python and sql for reporting", "R")
    assert has_term("python, c#, sql", "C#")
    assert numbers("about 130,000 responses (99.7%), 10.6 million records, 2–4 minutes, 100+ devices, PL-300; "
                   "Magdeburg, 23 October 2026; Jul 2024 - Sep 2025; ab 01.01.2027; Note 1,7") == \
        {"130000", "99.7", "10600000", "2", "4", "100", "300", "1.7"}
    assert numbers("~130k rows") == numbers("130,000 rows") == {"130000"}
    assert numbers("Potsdamer Straße 58, 10785 Berlin; 5 Monate") == {"5"}
    assert fact_check("monitoring efficiency up 40% across 100+ devices", "improved it by 30% on 100+ devices") == ["40"]
    assert fact_check("available 15–20 hours a week", "up to 20 hours", allow="15") == []
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compile and check a tailored CV.")
    ap.add_argument("tex", nargs="?", type=Path)
    ap.add_argument("--keywords", default="", help='keywords separated by ";"')
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--allow", default="", help='numbers quoted from the posting, separated by ";"')
    ap.add_argument("--profile", type=Path, default=PROFILE, help="profile the fact check compares against")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit(0)
    if not a.tex or not a.tex.exists():
        ap.error("give the path to an existing .tex file")
    kws = [k.strip() for k in a.keywords.split(";") if k.strip()]
    sys.exit(0 if build(a.tex.resolve(), a.max_pages, kws, a.allow, a.profile) else 1)
