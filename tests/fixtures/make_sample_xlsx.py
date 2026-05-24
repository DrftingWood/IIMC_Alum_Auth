"""Generate a 50-row synthetic alumni Excel file for tests and local dev.

Run: python -m tests.fixtures.make_sample_xlsx [output_path]
"""

import sys
from pathlib import Path

import openpyxl

HEADERS = [
    "User ID",
    "Name",
    "Email",
    "Personal Email",
    "Status",
    "Batch Year",
    "Program",
    "Joining Year",
    "Passing Year",
    "Reg Number",
    "Gender",
    "Mobile",
    "Home City",
    "Home Country",
    "Company",
    "Designation",
    "Office City",
    "Hostel",
    "Room Number",
    "UG Degree",
    "UG Institute",
    "Summer Internship Firm",
    "Summer Internship Domain",
    "Finals Firm",
    "Finals Domain",
    "LinkedIn URL",
    "Hobbies",
]

PROGRAMS = ["PGP", "PGDM", "LDP", "FP", "PGPEX"]


def make_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(1, 51):
        program = PROGRAMS[i % len(PROGRAMS)]
        batch = 2000 + (i % 25)
        rows.append(
            {
                "User ID": f"sample{i:03d}",
                "Name": f"Test Alum {i:03d}",
                "Email": f"alum{i:03d}@example.com",
                "Personal Email": f"alum{i:03d}.personal@example.org" if i % 3 == 0 else None,
                "Status": "Alumni" if i % 4 != 0 else None,
                "Batch Year": batch,
                "Program": program,
                "Joining Year": batch - 2,
                "Passing Year": batch,
                "Reg Number": f"{program}/{batch}/{i:04d}",
                "Gender": "M" if i % 2 == 0 else "F",
                "Mobile": f"99999{i:05d}" if i % 4 == 0 else None,
                "Home City": "TestCity",
                "Home Country": "TestCountry",
                "Company": "TestCo" if i % 2 == 0 else None,
                "Designation": "Engineer" if i % 2 == 0 else None,
                "Office City": "TestOfficeCity",
                "Hostel": "OH",
                "Room Number": f"H{i % 4 + 1}-{i:03d}",
                "UG Degree": "B.Tech",
                "UG Institute": "TestUG",
                "Summer Internship Firm": None,
                "Summer Internship Domain": None,
                "Finals Firm": None,
                "Finals Domain": None,
                "LinkedIn URL": f"https://linkedin.com/in/alum-{i:03d}" if i % 12 == 0 else None,
                "Hobbies": None,
            }
        )
    # Inject a name-collision pair for testing display-name disambiguation
    rows.append(
        {
            **rows[0],
            "User ID": "sample001b",
            "Reg Number": "PGP/2001/0099",
            "Email": "alum001b@example.com",
            "Personal Email": None,
            "Mobile": None,
        }
    )
    return rows


def write(out: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Students"
    ws.append(HEADERS)
    for r in make_rows():
        ws.append([r.get(h) for h in HEADERS])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/alumni_sample.xlsx")
    write(out)
    print(f"Wrote {out}")  # noqa: T201
