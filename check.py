"""Step 0: is everything in place? Prints what it finds. Calls no model."""
import json
import os
import pathlib
import platform

DATA = pathlib.Path("data")
USE_CASES = [
    ("UC1 supplier payments", "uc1_supplier_payments"),
    ("UC2 KYB onboarding", "uc2_kyb_onboarding"),
    ("UC3 incoming funds", "uc3_incoming_funds"),
    ("UC4 bulk payees", "uc4_bulk_payee_files"),
    ("UC5 corridor payments", "uc5_corridor_payments"),
    ("UC6 FX drawdowns", "uc6_fx_drawdowns"),
    ("UC7 tuition payments", "uc7_tuition_payments"),
]
MASTER = ["master_data.json", "payment_history.json", "booked_deals.json", "saved_payees.json",
          "fx_contracts.json", "tuition_payment_history.json"]


def files_in(folder: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in folder.rglob("*") if p.is_file() and p.name != ".DS_Store"]


print(f"Python                 {platform.python_version()} (inside the lab image)")

total = len(files_in(DATA)) if DATA.is_dir() else 0
print(f"Sample data            {total} files in data/")

for label, folder in USE_CASES:
    gt = DATA / folder / "ground_truth.json"
    if not gt.exists():
        print(f"{label:<23}MISSING ({gt})")
        continue
    cases = json.loads(gt.read_text())
    # AUTO_CLEAR / AUTO_MATCH / AUTO_RELEASE: the case should clear with no person.
    auto = sum(1 for c in cases if c["expected_route"].startswith("AUTO_"))
    print(f"{label:<23}{len(cases)} cases ({auto} clear automatically), "
          f"{len(files_in(DATA / folder))} files, answer key found")

missing = [m for m in MASTER if not (DATA / "master" / m).exists()]
print(f"Master data            {'found (' + ', '.join(MASTER) + ')' if not missing else 'MISSING ' + ', '.join(missing)}")

key = os.environ.get("GOOGLE_API_KEY", "")
print(f"Gemini key             {'set' if key and key != 'your-gemini-api-key' else 'not set (needed from step 1)'}")

import langchain, pypdf  # noqa: E402,F401  (proves the libraries are installed)
print(f"Libraries              langchain {langchain.__version__}, pypdf {pypdf.__version__}")
