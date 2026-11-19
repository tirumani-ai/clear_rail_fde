"""The forms: one per kind of paper in a UC1 case (spec, "Use case 1: Documents per payment").

Where a field feeds a UC1 check, its name follows expected_fields in
data/uc1_supplier_payments/ground_truth.json, so the ladder can score it.
"""
from typing import Literal

from pydantic import BaseModel, Field

DATE = "YYYY-MM-DD"

# The labels are the doc_type values in the answer key.
PAPER_KINDS = (
    "PAYMENT_INSTRUCTION",
    "COMMERCIAL_INVOICE",
    "PROFORMA_INVOICE",
    "PURCHASE_ORDER",
    "SERVICES_CONTRACT",
    "BANK_DETAILS_LETTER",
)
INVOICE_KINDS = ("COMMERCIAL_INVOICE", "PROFORMA_INVOICE")


class Bank(BaseModel):
    bank_name: str = ""
    bank_country: str = ""
    swift: str = ""
    account_number: str | None = None
    iban: str | None = None
    clabe: str | None = None  # Mexico
    ifsc: str | None = None   # India
    cnaps: str | None = None  # China


class Beneficiary(BaseModel):
    beneficiary_id: str
    name: str
    address: str = ""
    country: str
    bank: Bank


class PaymentInstruction(BaseModel):
    """From the client portal, as JSON. Read by plain code, never by a model."""
    payment_id: str
    submitted_at: str
    client_id: str
    client_name: str
    beneficiary: Beneficiary
    amount: float
    currency: str
    purpose_code: str = Field(description="GDI goods, ADV advance, SVC services")
    invoice_references: list[str] = []
    remittance_info: str = ""
    requested_value_date: str = ""


class LineItem(BaseModel):
    description: str = ""
    quantity: float = 0
    unit_price: float = 0
    amount: float = 0


class Invoice(BaseModel):
    """Supplier invoice (commercial or service) or proforma invoice."""
    invoice_number: str = ""
    invoice_date: str = Field("", description="the date printed as 'Invoice Date', " + DATE)
    due_date: str = Field("", description="the date printed as 'Due Date', " + DATE)
    seller: str = Field("", description="the supplier issuing the invoice")
    buyer: str = Field("", description="the company the invoice is addressed to")
    # One reference, copied as printed. Code decides whether it is a PO or a contract (app/rules/linking.py).
    reference: str = Field("", description="the buyer's reference exactly as printed ('Your Ref', 'PO No', 'Contract No')")
    lines: list[LineItem] = Field([], description="every line item, in order")
    invoice_total: float = 0
    invoice_currency: str = Field("", description="ISO code, e.g. USD")
    invoice_bank_name: str = Field("", description="the bank named after 'Pay to'")
    invoice_swift: str = Field("", description="the SWIFT / BIC code after 'Pay to'")
    invoice_bank_account: str = Field(
        "", description="ONLY the account number, IBAN or CLABE after 'Pay to': no bank name, no SWIFT, no label")
    invoice_signatory: str = Field("", description="the person's name only, without a job title")
    is_proforma: bool = Field(False, description="true if marked proforma (advance payment)")


class PurchaseOrder(BaseModel):
    po_number: str = ""
    po_date: str = Field("", description=DATE)
    buyer: str = ""
    supplier: str = ""
    lines: list[LineItem] = Field([], description="every line item, in order")
    po_currency: str = Field("", description="ISO code")
    po_total: float = 0
    approved_by: str = Field("", description="the person's name only, without a job title")


class ServicesContract(BaseModel):
    contract_number: str = Field("", description="agreement / contract number")
    effective_date: str = Field("", description=DATE)
    provider: str = Field("", description="the supplier providing the services")
    client: str = Field("", description="the company receiving the services")
    scope: str = ""
    contract_value: float = 0
    contract_currency: str = Field("", description="ISO code")
    term: str = ""
    billing: str = ""
    provider_signatory: str = Field("", description="the person's name only")
    client_signatory: str = Field("", description="the person's name only")


class BankDetailsLetter(BaseModel):
    letter_type: str = Field("", description="CHANGE if it announces new details, CONFIRMATION if it re-confirms them")
    letter_date: str = Field("", description=DATE)
    supplier: str = Field("", description="the company sending the letter")
    addressed_to: str = ""
    account_holder: str = ""
    bank_name: str = ""
    bank_country: str = Field("", description="ISO 2-letter code")
    bank_letter_account: str = Field("", description="account number / IBAN / CLABE in the letter")
    swift: str = ""
    local_code: str = Field("", description="IFSC, CNAPS or other local bank code, if printed")
    effective_date: str = Field("", description=DATE)
    signatory: str = Field("", description="the person's name only, without a job title")


class Kind(BaseModel):
    """The classifier's form: used only when a paper has no title code can recognise."""
    kind: Literal[
        "COMMERCIAL_INVOICE",   # an invoice for goods or services, asking to be paid
        "PROFORMA_INVOICE",     # marked proforma: a quote asking for an advance payment
        "PURCHASE_ORDER",       # issued by the buyer, ordering goods
        "SERVICES_CONTRACT",    # an agreement for services: parties, scope, value, term
        "BANK_DETAILS_LETTER",  # a supplier letter changing or confirming its bank account
        "OTHER",
    ] = Field(description="What kind of paper this is.")


# The form the model fills for each kind of paper. The payment instruction is not here: code reads it.
FORMS: dict[str, type[BaseModel]] = {
    "COMMERCIAL_INVOICE": Invoice,
    "PROFORMA_INVOICE": Invoice,
    "PURCHASE_ORDER": PurchaseOrder,
    "SERVICES_CONTRACT": ServicesContract,
    "BANK_DETAILS_LETTER": BankDetailsLetter,
}
