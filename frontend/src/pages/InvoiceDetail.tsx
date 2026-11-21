import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Invoice, useAction, useLoad } from "../api.ts";
import { ErrorNote, Field, Stamp } from "../components/ui.tsx";
import {
  formatMoney,
  hundredthsToInput,
  lineAmount,
  parseHundredths,
  totals,
  trimHundredths,
} from "../lib/money.ts";
import { formatDate, isoDate } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

export default function InvoiceDetail() {
  const { id } = useParams();
  const { version } = useRefresh();
  const { data: invoice, error } = useLoad(() => api<Invoice>(`/invoices/${id}`), [id, version]);

  if (error) {
    return (
      <>
        <ErrorNote message={error} />
        <Link to="/invoices">Back to invoices</Link>
      </>
    );
  }
  if (!invoice) return null;
  // keyed so the editor keeps unsaved edits when other data on the page refreshes
  return invoice.status === "draft" ? (
    <DraftEditor key={invoice.id} invoice={invoice} />
  ) : (
    <IssuedInvoice invoice={invoice} />
  );
}

function BackLink() {
  return (
    <p className="back">
      <Link to="/invoices">All invoices</Link>
    </p>
  );
}

// ---------- sent, overdue, paid and void invoices: read-only ----------

function IssuedInvoice({ invoice }: { invoice: Invoice }) {
  const { bump } = useRefresh();
  const [paidOn, setPaidOn] = useState(isoDate());
  const { busy, error, run } = useAction();
  const money = (minor: number) => formatMoney(minor, invoice.currency);

  function mark(status: "sent" | "paid" | "void") {
    if (
      status === "void" &&
      !confirm(
        `Void ${invoice.number}? It keeps its number and stays in your records, but is no longer ` +
          "owed. Its tracked time becomes billable again. This cannot be undone.",
      )
    ) {
      return;
    }
    run(async () => {
      await api(`/invoices/${invoice.id}/status`, {
        method: "POST",
        body: status === "paid" ? { status, paid_on: paidOn } : { status },
      });
      bump();
    });
  }

  return (
    <>
      <BackLink />
      <article className="sheet">
        <header className="sheet-head">
          <div>
            <h1>Invoice {invoice.number}</h1>
            <p className="sheet-client">{invoice.client_name}</p>
          </div>
          <Stamp status={invoice.status} />
        </header>
        <dl className="sheet-dates">
          <div>
            <dt>Issued</dt>
            <dd>{formatDate(invoice.issue_date)}</dd>
          </div>
          <div>
            <dt>Due</dt>
            <dd>{formatDate(invoice.due_date)}</dd>
          </div>
          {invoice.paid_on && (
            <div>
              <dt>Paid</dt>
              <dd>{formatDate(invoice.paid_on)}</dd>
            </div>
          )}
        </dl>

        <table className="ledger lines">
          <thead>
            <tr>
              <th scope="col">Description</th>
              <th scope="col" className="num">Qty</th>
              <th scope="col" className="num">Unit price</th>
              <th scope="col" className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines?.map((line) => (
              <tr key={line.id}>
                <td>{line.description}</td>
                <td className="num">{trimHundredths(line.quantity_hundredths)}</td>
                <td className="num">{money(line.unit_price_minor)}</td>
                <td className="num">{money(line.amount_minor)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="totals">
          <div>
            <dt>Subtotal</dt>
            <dd>{money(invoice.subtotal_minor)}</dd>
          </div>
          {invoice.discount_minor > 0 && (
            <div>
              <dt>Discount ({trimHundredths(invoice.discount_bp)}%)</dt>
              <dd>-{money(invoice.discount_minor)}</dd>
            </div>
          )}
          {invoice.tax_rate_bp > 0 && (
            <div>
              <dt>Tax ({trimHundredths(invoice.tax_rate_bp)}%)</dt>
              <dd>{money(invoice.tax_minor)}</dd>
            </div>
          )}
          <div className="grand">
            <dt>Total</dt>
            <dd>{money(invoice.total_minor)}</dd>
          </div>
        </dl>
        {invoice.notes && <p className="sheet-notes">{invoice.notes}</p>}
      </article>

      <ErrorNote message={error} />
      <div className="sheet-actions">
        <a className="btn" href={`/api/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">
          Open PDF
        </a>
        {invoice.status === "void" ? (
          <span className="muted">Voided: no longer owed. Any tracked time on it can be invoiced again.</span>
        ) : invoice.status === "paid" ? (
          <button type="button" className="btn" onClick={() => mark("sent")} disabled={busy}>
            Mark as unpaid
          </button>
        ) : (
          <>
            <Field label="Paid on" className="inline">
              <input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} required />
            </Field>
            <button type="button" className="btn btn-primary" onClick={() => mark("paid")} disabled={!paidOn || busy}>
              Mark as paid
            </button>
            <button type="button" className="btn btn-danger" onClick={() => mark("void")} disabled={busy}>
              Void invoice
            </button>
          </>
        )}
      </div>
    </>
  );
}

// ---------- drafts: editable ----------

type Row = { key: number; id?: number; description: string; quantity: string; price: string };
type Form = {
  issue_date: string;
  due_date: string;
  tax: string;
  discount: string;
  notes: string;
  rows: Row[];
};

let nextKey = 1;

function toForm(invoice: Invoice): Form {
  return {
    issue_date: invoice.issue_date,
    due_date: invoice.due_date,
    tax: trimHundredths(invoice.tax_rate_bp),
    discount: trimHundredths(invoice.discount_bp),
    notes: invoice.notes,
    rows: (invoice.lines ?? []).map((line) => ({
      key: nextKey++,
      id: line.id,
      description: line.description,
      quantity: trimHundredths(line.quantity_hundredths),
      price: hundredthsToInput(line.unit_price_minor),
    })),
  };
}

/** A percentage typed as "20" or "18.5", as basis points; null if it is not between 0 and 100. */
function parsePercent(text: string): number | null {
  const bp = parseHundredths(text || "0");
  return bp !== null && bp <= 10_000 ? bp : null;
}

function DraftEditor({ invoice }: { invoice: Invoice }) {
  const { bump } = useRefresh();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => toForm(invoice));
  const [dirty, setDirty] = useState(false);
  const { busy, error, setError, run } = useAction();
  const money = (minor: number) => formatMoney(minor, invoice.currency);

  function change(patch: Partial<Form>) {
    setForm({ ...form, ...patch });
    setDirty(true);
  }
  function changeRow(key: number, patch: Partial<Row>) {
    change({ rows: form.rows.map((row) => (row.key === key ? { ...row, ...patch } : row)) });
  }

  const parsed = form.rows.map((row) => {
    const quantity = parseHundredths(row.quantity);
    const price = parseHundredths(row.price);
    const ok = quantity !== null && quantity >= 1 && price !== null;
    return { quantity, price, amount: ok ? lineAmount(quantity, price) : null };
  });
  const taxBp = parsePercent(form.tax);
  const discountBp = parsePercent(form.discount);
  const sum = totals(parsed.map((p) => p.amount ?? 0), discountBp ?? 0, taxBp ?? 0);

  async function save(): Promise<boolean> {
    if (parsed.some((p) => p.amount === null) || form.rows.some((r) => !r.description.trim())) {
      setError("Every line needs a description, a quantity above zero and a price, like 2.5 and 1500.00.");
      return false;
    }
    if (taxBp === null || discountBp === null) {
      setError("Tax and discount are percentages between 0 and 100.");
      return false;
    }
    return run(async () => {
      const saved = await api<Invoice>(`/invoices/${invoice.id}`, {
        method: "PUT",
        body: {
          issue_date: form.issue_date,
          due_date: form.due_date,
          tax_rate_bp: taxBp,
          discount_bp: discountBp,
          notes: form.notes,
          lines: form.rows.map((row, i) => ({
            ...(row.id ? { id: row.id } : {}),
            description: row.description,
            quantity_hundredths: parsed[i].quantity,
            unit_price_minor: parsed[i].price,
          })),
        },
      });
      setForm(toForm(saved));
      setDirty(false);
      bump();
    });
  }

  async function send() {
    if (form.rows.length === 0) {
      setError("Add at least one line before sending.");
      return;
    }
    if (!confirm("Mark this invoice as sent? It gets the next invoice number and can no longer be edited.")) {
      return;
    }
    if (!(await save())) return;
    await run(async () => {
      await api(`/invoices/${invoice.id}/status`, { method: "POST", body: { status: "sent" } });
      bump();
    });
  }

  async function remove() {
    if (!confirm("Delete this draft? Its tracked time becomes billable again.")) return;
    await run(async () => {
      await api(`/invoices/${invoice.id}`, { method: "DELETE" });
      bump();
      navigate("/invoices");
    });
  }

  return (
    <>
      <BackLink />
      <article className="sheet">
        <header className="sheet-head">
          <div>
            <h1>Draft invoice</h1>
            <p className="sheet-client">{invoice.client_name}</p>
          </div>
          <Stamp status="draft" />
        </header>
        {/* locked while a request is in flight, so edits made meanwhile cannot be lost */}
        <fieldset disabled={busy}>
          <div className="sheet-dates">
            <Field label="Issue date">
              <input
                type="date"
                value={form.issue_date}
                onChange={(e) => change({ issue_date: e.target.value })}
                required
              />
            </Field>
            <Field label="Due date">
              <input
                type="date"
                value={form.due_date}
                min={form.issue_date}
                onChange={(e) => change({ due_date: e.target.value })}
                required
              />
            </Field>
          </div>

          <table className="ledger lines editing stacks">
            <thead>
              <tr>
                <th scope="col">Description</th>
                <th scope="col" className="num">Qty</th>
                <th scope="col" className="num">Unit price</th>
                <th scope="col" className="num">Amount</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {form.rows.map((row, i) => (
                <tr key={row.key}>
                  <td>
                    <input
                      aria-label={`Line ${i + 1} description`}
                      value={row.description}
                      maxLength={500}
                      onChange={(e) => changeRow(row.key, { description: e.target.value })}
                    />
                  </td>
                  <td className="num">
                    <input
                      aria-label={`Line ${i + 1} quantity`}
                      className="num"
                      inputMode="decimal"
                      value={row.quantity}
                      onChange={(e) => changeRow(row.key, { quantity: e.target.value })}
                    />
                  </td>
                  <td className="num">
                    <input
                      aria-label={`Line ${i + 1} unit price`}
                      className="num"
                      inputMode="decimal"
                      value={row.price}
                      onChange={(e) => changeRow(row.key, { price: e.target.value })}
                    />
                  </td>
                  <td className="num">{parsed[i].amount === null ? "?" : money(parsed[i].amount!)}</td>
                  <td className="row-actions">
                    <button
                      type="button"
                      className="link"
                      onClick={() => change({ rows: form.rows.filter((r) => r.key !== row.key) })}
                    >
                      Remove<span className="sr-only"> line {i + 1}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button
              type="button"
              className="btn"
              onClick={() =>
                change({
                  rows: [...form.rows, { key: nextKey++, description: "", quantity: "1", price: "" }],
                })
              }
            >
              Add line
            </button>
          </p>

          <dl className="totals">
            <div>
              <dt>Subtotal</dt>
              <dd>{money(sum.subtotal)}</dd>
            </div>
            <div>
              <dt>
                <label htmlFor="discount">Discount %</label>
                <input
                  id="discount"
                  className="num pct"
                  inputMode="decimal"
                  value={form.discount}
                  onChange={(e) => change({ discount: e.target.value })}
                />
              </dt>
              <dd>{sum.discount > 0 ? "-" : ""}{money(sum.discount)}</dd>
            </div>
            <div>
              <dt>
                <label htmlFor="tax">Tax %</label>
                <input
                  id="tax"
                  className="num pct"
                  inputMode="decimal"
                  value={form.tax}
                  onChange={(e) => change({ tax: e.target.value })}
                />
              </dt>
              <dd>{money(sum.tax)}</dd>
            </div>
            <div className="grand">
              <dt>Total</dt>
              <dd>{money(sum.total)}</dd>
            </div>
          </dl>

          <Field label="Notes on the invoice">
            <textarea
              rows={2}
              maxLength={2000}
              value={form.notes}
              onChange={(e) => change({ notes: e.target.value })}
            />
          </Field>
        </fieldset>
      </article>

      <ErrorNote message={error} />
      <div className="sheet-actions">
        <button type="button" className="btn btn-primary" onClick={save} disabled={!dirty || busy}>
          {dirty ? "Save draft" : "Saved"}
        </button>
        <button type="button" className="btn" onClick={send} disabled={busy}>
          Mark as sent
        </button>
        {dirty ? (
          <span className="muted">Save to preview the PDF.</span>
        ) : (
          <a className="btn" href={`/api/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">
            Preview PDF
          </a>
        )}
        <button type="button" className="btn btn-danger" onClick={remove} disabled={busy}>
          Delete draft
        </button>
      </div>
    </>
  );
}
