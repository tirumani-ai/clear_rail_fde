"""Who must look at a case. Plain code, and it only ever makes a route stricter.

  no codes                      AUTO_CLEAR (a person still never needs to; code releases it later)
  any compliance code           COMPLIANCE_OFFICER
  ops codes, up to USD 100,000  PAYMENTS_OPS_ANALYST
  ops codes, up to USD 1M       PAYMENTS_OPS_TEAM_LEAD
  ops codes, above that         COMPLIANCE_OFFICER (the only role with no limit)
BANK_DETAILS_CHANGED also needs a callback, which only a person can do.
"""
from decimal import Decimal

from app.master import Master

COMPLIANCE_CODES = {
    "BENEFICIARY_COUNTRY_MISMATCH",
    "INVOICE_BANK_MISMATCH",
    "BUYER_MISMATCH",
    "SCREENING_HIT",
    "SUSPICIOUS_CONTENT",
}
CALLBACK_CODES = {"BANK_DETAILS_CHANGED"}


def route(codes: set[str], amount_usd: Decimal, master: Master) -> str:
    if not codes:
        return "AUTO_CLEAR"
    if codes & COMPLIANCE_CODES:
        return "COMPLIANCE_OFFICER"
    limits = master.approval_limits_usd
    if amount_usd <= Decimal(str(limits["payments_ops_analyst"])):
        return "PAYMENTS_OPS_ANALYST"
    if amount_usd <= Decimal(str(limits["payments_ops_team_lead"])):
        return "PAYMENTS_OPS_TEAM_LEAD"
    return "COMPLIANCE_OFFICER"


def held_actions(codes: set[str]) -> list[str]:
    """What a person must do before release. Proposed, never done, by code or by an agent."""
    actions = []
    if codes & CALLBACK_CODES:
        actions.append("callback to the supplier on contact details already on file, never ones from the papers")
    if "MISSING_SUPPORTING_DOC" in codes:
        actions.append("request the missing papers from the client")
    if codes & COMPLIANCE_CODES:
        actions.append("escalate to compliance")
    return actions
