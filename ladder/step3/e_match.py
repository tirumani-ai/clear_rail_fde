"""STEP 3e: run the 11 UC1 checks and route each payment. Plain code, no model.

For each payment, code compares the instruction with the invoice, the PO or contract, any bank letter and
master data: the unpaid balance after earlier payments, currencies, names, countries, the saved bank details,
the purpose code, the buyer, the PO total, the invoice's age, the watchlist, duplicates and hidden instructions
(app/rules/uc1_checks.py). Each failed check is a mismatch code; the codes and the amount in USD decide who
must look (app/rules/routing.py). A model never decides any of it, and nothing here releases a payment.

Run:  ./run.sh ladder/step3/e_match.py                 (all 32 payments, scored against the answer key)
      ./run.sh ladder/step3/e_match.py PAY-202611032   (the balance after an earlier payment)
      ./run.sh ladder/step3/e_match.py --misread       (a misread total must never clear a payment)
"""
import collections

from common import answer_key, case_dirs, flags, pretend

from app.ingestion.papers import read_case
from app.master import load, to_usd
from app.rules.linking import link_case
from app.rules.routing import held_actions, route
from app.rules.uc1_checks import run_checks


def main():
    master, key, score = load(), answer_key(), collections.Counter()
    unsafe = []
    for case in case_dirs():
        papers = pretend(read_case(case), flags())
        links = link_case(case.name, papers, master)
        issues = run_checks(links, papers, master)
        codes = {i.code for i in issues}
        pi = links.instruction.form
        usd = to_usd(pi["amount"], pi["currency"], master)
        where = route(codes, usd, master)
        want = key[case.name]
        codes_ok, route_ok = sorted(codes) == sorted(want["expected_codes"]), where == want["expected_route"]
        score["codes"] += codes_ok
        score["route"] += route_ok
        score["cases"] += 1
        if where == "AUTO_CLEAR" and want["expected_route"] != "AUTO_CLEAR":
            unsafe.append(case.name)
        print(f"{case.name}: {where:22} {sorted(codes) or 'no codes'}   pay {pi['amount']:,} {pi['currency']} (USD {usd:,})")
        for i in issues:
            print(f"    - {i.code}: {i.message}")
        for action in held_actions(codes):
            print(f"    held for a person: {action}")
        if not (codes_ok and route_ok):
            print(f"    answer key: {want['expected_route']} {want['expected_codes']}   <- DIFFERENT")
    n = score["cases"]
    print(f"\nCodes as the answer key: {score['codes']}/{n}. Route as the answer key: {score['route']}/{n}.")
    print(f"Payments with a problem that were cleared anyway: {len(unsafe)}" + (f" {unsafe}" if unsafe else "."))


if __name__ == "__main__":
    main()
