import { Link, useSearchParams } from "react-router-dom";
import { api, type Invoice, type InvoiceStatus, type Recurring, useAction, useLoad } from "../api.ts";
import { ErrorNote, PageHeader, StatusMark } from "../components/ui.tsx";
import { formatMoney } from "../lib/money.ts";
import { everyLabel, formatDate } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

const FILTERS: [InvoiceStatus | "", string][] = [
  ["", "All"],
  ["draft", "Drafts"],
  ["sent", "Sent"],
  ["overdue", "Overdue"],
  ["paid", "Paid"],
  ["void", "Void"],
];

export default function Invoices() {
  const { version } = useRefresh();
  const [params, setParams] = useSearchParams();
  const filter = params.get("status") ?? "";
  const { data, error } = useLoad(() => api<Invoice[]>("/invoices"), [version]);
  const shown = (data ?? []).filter((i) => !filter || i.status === filter);

  return (
    <>
      <PageHeader title="Invoices">
        <a className="btn" href="/api/export/invoices.csv" download>
          Export CSV
        </a>
        <Link className="btn btn-primary" to="/invoices/new">
          New invoice
        </Link>
      </PageHeader>
      <ErrorNote message={error} />

      <div className="segmented" role="group" aria-label="Filter by status">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setParams(value ? { status: value } : {}, { replace: true })}
          >
            {label}
            {data && <span className="count">{data.filter((i) => !value || i.status === value).length}</span>}
          </button>
        ))}
      </div>

      {data && shown.length === 0 ? (
        <p className="empty">
          {data.length === 0 ? (
            <>
              No invoices yet. <Link to="/invoices/new">Create one</Link> from tracked time or fixed
              prices.
            </>
          ) : (
            "No invoices with this status."
          )}
        </p>
      ) : (
        <table className="ledger invoices stacks">
          <thead>
            <tr>
              <th scope="col">Number</th>
              <th scope="col">Client</th>
              <th scope="col">Issued</th>
              <th scope="col">Due</th>
              <th scope="col">Status</th>
              <th scope="col" className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((invoice) => (
              <tr key={invoice.id}>
                <th scope="row">
                  <Link to={`/invoices/${invoice.id}`}>{invoice.number ?? "Draft"}</Link>
                </th>
                <td>{invoice.client_name}</td>
                <td className="small">{formatDate(invoice.issue_date)}</td>
                <td className="small">{formatDate(invoice.due_date)}</td>
                <td>
                  <StatusMark status={invoice.status} />
                </td>
                <td className="num">{formatMoney(invoice.total_minor, invoice.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RecurringList version={version} />
    </>
  );
}

/** Schedules that copy a sent invoice to a new draft; hidden until there is one. */
function RecurringList({ version }: { version: number }) {
  const { data, error, reload } = useLoad(() => api<Recurring[]>("/recurring"), [version]);
  const action = useAction();
  if (!data?.length && !error) return null;

  function stop(schedule: Recurring) {
    if (!confirm(`Stop repeating ${schedule.source_number}? Drafts already made stay.`)) return;
    action.run(async () => {
      await api(`/recurring/${schedule.id}`, { method: "DELETE" });
      reload();
    });
  }

  return (
    <section className="recurring" aria-labelledby="recurring-title">
      <h2 id="recurring-title">Recurring</h2>
      <p className="muted small">A draft copy is made on each date for you to check and send.</p>
      <ErrorNote message={error || action.error} />
      <table className="ledger recurring-list stacks">
        <thead>
          <tr>
            <th scope="col">Copy of</th>
            <th scope="col">Client</th>
            <th scope="col">How often</th>
            <th scope="col">Next draft</th>
            <th scope="col" className="num">Total</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data?.map((schedule) => (
            <tr key={schedule.id}>
              <th scope="row">
                <Link to={`/invoices/${schedule.source_invoice_id}`}>{schedule.source_number}</Link>
              </th>
              <td>{schedule.client_name}</td>
              <td className="small">{everyLabel(schedule.every_months)}</td>
              <td className="small">{formatDate(schedule.next_date)}</td>
              <td className="num">{formatMoney(schedule.total_minor, schedule.currency)}</td>
              <td className="row-actions">
                <button
                  type="button"
                  className="link"
                  onClick={() => stop(schedule)}
                  disabled={action.busy}
                  aria-label={`Stop repeating ${schedule.source_number}`}
                >
                  Stop
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
