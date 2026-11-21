"""Database tables and the request bodies validated at the API boundary."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from pydantic import Field as PField
from sqlmodel import Field, SQLModel

Currency = Literal["TRY", "USD", "EUR", "GBP"]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------- tables ----------

# AUTOINCREMENT: SQLite would otherwise hand a deleted row's id to the next insert, and a tab
# still showing the deleted draft could then edit an unrelated invoice. Applies to new databases.
NO_ID_REUSE = {"sqlite_autoincrement": True}
MAX_LINES = 200


class Client(SQLModel, table=True):
    __table_args__ = NO_ID_REUSE
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = ""
    address: str = ""
    tax_id: str = ""
    currency: str = "TRY"
    notes: str = ""
    created_at: dt.datetime = Field(default_factory=utcnow)


class Project(SQLModel, table=True):
    __table_args__ = NO_ID_REUSE
    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    name: str
    hourly_rate_minor: int = 0  # in the client's currency
    archived: bool = False
    created_at: dt.datetime = Field(default_factory=utcnow)


class Invoice(SQLModel, table=True):
    __table_args__ = NO_ID_REUSE
    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    number: str | None = Field(default=None, unique=True)  # assigned when sent
    status: str = "draft"  # draft | sent | paid; "overdue" is derived from due_date
    currency: str
    issue_date: dt.date
    due_date: dt.date
    tax_rate_bp: int = 0
    discount_bp: int = 0
    notes: str = ""
    subtotal_minor: int = 0
    discount_minor: int = 0
    tax_minor: int = 0
    total_minor: int = 0
    paid_on: dt.date | None = None
    created_at: dt.datetime = Field(default_factory=utcnow)


class InvoiceLine(SQLModel, table=True):
    __table_args__ = NO_ID_REUSE
    id: int | None = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.id", index=True)
    position: int = 0
    description: str
    quantity_hundredths: int  # 150 = 1.50
    unit_price_minor: int
    amount_minor: int
    project_id: int | None = Field(default=None, foreign_key="project.id")  # set on time lines


class IssuedCopy(SQLModel, table=True):
    """The client and business details as they were when an invoice was sent.

    The PDF of a sent invoice prints these, so editing a client or the settings later does
    not rewrite invoices that are already with the customer.
    """

    invoice_id: int = Field(primary_key=True, foreign_key="invoice.id")
    client: str  # the Client row as JSON
    business: str  # the Settings row as JSON


class TimeEntry(SQLModel, table=True):
    __table_args__ = NO_ID_REUSE
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    date: dt.date = Field(index=True)
    minutes: int = 0
    description: str = ""
    billable: bool = True
    invoice_id: int | None = Field(default=None, foreign_key="invoice.id", index=True)
    started_at: dt.datetime | None = None  # set only while the timer is running


class Settings(SQLModel, table=True):
    id: int | None = Field(default=1, primary_key=True)
    business_name: str = "My Studio"
    business_address: str = ""
    business_email: str = ""
    tax_id: str = ""
    invoice_prefix: str = "INV-"
    next_invoice_number: int = 1
    default_tax_rate_bp: int = 2000
    payment_terms_days: int = 14
    invoice_footer: str = ""


class AuthSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    csrf_token: str
    expires_at: dt.datetime


# ---------- request bodies ----------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
BasisPoints = Annotated[int, PField(ge=0, le=10_000)]
# Limits keep any invoice total far below SQLite's 64-bit integers and JavaScript's 2**53.
Minor = Annotated[int, PField(ge=0, le=10**9)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Body):
    password: Annotated[str, StringConstraints(max_length=1024)]


class ClientIn(Body):
    name: Name
    email: Short = ""
    address: Text = ""
    tax_id: Short = ""
    currency: Currency = "TRY"
    notes: Text = ""


class ProjectIn(Body):
    client_id: int
    name: Name
    hourly_rate_minor: Minor = 0
    archived: bool = False


class ProjectUpdate(Body):
    name: Name
    hourly_rate_minor: Minor = 0
    archived: bool = False


class TimeEntryIn(Body):
    project_id: int
    date: dt.date
    minutes: Annotated[int, PField(ge=1, le=24 * 60)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    billable: bool = True


class TimerStartIn(Body):
    project_id: int
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class LineIn(Body):
    id: int | None = None  # an existing line being kept; omitted for new lines
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    quantity_hundredths: Annotated[int, PField(ge=1, le=10**6)]
    unit_price_minor: Minor


class InvoiceFields(Body):
    issue_date: dt.date | None = None  # default: today
    due_date: dt.date | None = None  # default: issue date + payment terms
    tax_rate_bp: BasisPoints | None = None  # default: from settings
    discount_bp: BasisPoints = 0
    notes: Text = ""
    lines: Annotated[list[LineIn], PField(max_length=MAX_LINES)] = []

    @model_validator(mode="after")
    def due_not_before_issue(self):
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValueError("due_date cannot be before issue_date")
        return self


class InvoiceCreate(InvoiceFields):
    client_id: int
    time_entry_ids: Annotated[list[int], PField(max_length=5000)] = []


class StatusIn(Body):
    status: Literal["sent", "paid"]
    paid_on: dt.date | None = None


class SettingsIn(Body):
    business_name: Name
    business_address: Text = ""
    business_email: Short = ""
    tax_id: Short = ""
    invoice_prefix: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=20, pattern=r"^[A-Za-z0-9/_-]*$")
    ] = "INV-"
    next_invoice_number: Annotated[int, PField(ge=1, le=10**9)] = 1
    default_tax_rate_bp: BasisPoints = 2000
    payment_terms_days: Annotated[int, PField(ge=0, le=365)] = 14
    invoice_footer: Text = ""
