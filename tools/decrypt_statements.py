"""
Decrypt Emirates NBD e-statements and copy them to the ingest directories.

Usage:
    python decrypt_statements.py

You will be prompted for the PDF password (typically your DOB in DDMMYYYY format).
Decrypted files are written to data/chequing/ and data/savings/ with the same
filename but spaces replaced by underscores and lowercased.
"""
import subprocess
import sys
from pathlib import Path

QPDF = r"C:\Program Files\qpdf 12.3.2\bin\qpdf.exe"

JOBS = [
    # {
    #     "src_dir": Path(r"C:\Users\Shiko\Documents\CEQUING"),
    #     "dst_dir": Path(r"C:\Users\Shiko\Documents\budget-exporter\data\chequing"),
    # },
    # {
    #     "src_dir": Path(r"C:\Users\Shiko\Documents\SAVINGS"),
    #     "dst_dir": Path(r"C:\Users\Shiko\Documents\budget-exporter\data\savings"),
    # },
    {
        "src_dir": Path(r"C:\Users\Shiko\Documents\LOANS"),
        "dst_dir": Path(r"C:\Users\Shiko\Documents\budget-exporter\data\loans"),
    },
]


def decrypt_pdf(qpdf: str, password: str, src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [qpdf, f"--password={password}", "--decrypt", str(src), str(dst)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  OK  {src.name} -> {dst.name}")
        return True
    else:
        print(f"  FAIL {src.name}: {result.stderr.strip() or result.stdout.strip()}")
        return False


def main():
    password = input("PDF password: ")

    ok = fail = 0
    for job in JOBS:
        pdfs = sorted(job["src_dir"].glob("*.pdf"))
        if not pdfs:
            print(f"No PDFs found in {job['src_dir']}")
            continue
        print(f"\n{job['src_dir'].name}:")
        for src in pdfs:
            # e.g. "E-STATEMENT_08 AUG 2024_3801.pdf" -> "e-statement_08_aug_2024_3801.pdf"
            dst_name = src.name.replace(" ", "_").lower()
            dst = job["dst_dir"] / dst_name
            if decrypt_pdf(QPDF, password, src, dst):
                ok += 1
            else:
                fail += 1

    print(f"\nDone: {ok} decrypted, {fail} failed.")
    if fail:
        print("Check the password and try again for any failures.")


if __name__ == "__main__":
    main()
