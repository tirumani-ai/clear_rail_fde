"""STEP 3d: link the papers of a payment by strong keys. Plain code, no model.

A UC1 case arrives as one folder, so the question is not "which files go together" but "do they point at each
other": the instruction quotes the invoice number, the invoice quotes its PO or contract, and the instruction
names a supplier and a client we already know. Those are STRONG keys, compared after normalising
('2006/2026/4245' = '2006 2026 4245'). Names and bank names are WEAK keys: shown as hints, never used to link.
(app/rules/linking.py)

Run:  ./run.sh ladder/step3/d_link.py                  (all 32 cases)
      ./run.sh ladder/step3/d_link.py PAY-202611021    (the same invoice uploaded twice)
      ./run.sh ladder/step3/d_link.py --bad-ref        (3c could not see a misread PO number; linking can)
"""
from common import case_dirs, flags, pretend

from app.ingestion.papers import read_case
from app.master import load
from app.rules.linking import link_case, strong_keys


def main():
    master = load()
    broken = 0
    for case in case_dirs():
        papers = pretend(read_case(case), flags())
        links = link_case(case.name, papers, master)
        bad = [l for l in links.links if not l.ok]
        broken += bool(bad)
        print(f"{case.name}: {len(papers)} papers, " + ("all links hold" if not bad else f"{len(bad)} link(s) broken"))
        for p in papers:
            print(f"    {p.kind:20} {p.file.split('/')[-1]:28} strong keys: {sorted(strong_keys(p))}")
        for l in links.links:
            print(f"    {'ok  ' if l.ok else 'NO  '} {l.name:30} {l.detail}")
        if links.duplicates:
            print(f"    same invoice again as: {[p.file.split('/')[-1] for p in links.duplicates]}")
        for h in links.hints:
            print(f"    hint: {h}")
    print(f"\nCases with a broken link: {broken}.")


if __name__ == "__main__":
    main()
