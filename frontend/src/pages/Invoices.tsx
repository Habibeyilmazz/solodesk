import { Link, useSearchParams } from "react-router-dom";
import { api, type Invoice, type InvoiceStatus, useLoad } from "../api.ts";
import { ErrorNote, PageHeader, StatusMark } from "../components/ui.tsx";
import { formatMoney } from "../lib/money.ts";
import { formatDate } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

const FILTERS: [InvoiceStatus | "", string][] = [
  ["", "All"],
  ["draft", "Drafts"],
  ["sent", "Sent"],
  ["overdue", "Overdue"],
  ["paid", "Paid"],
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
        <table className="ledger invoices">
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
                <td>{formatDate(invoice.issue_date)}</td>
                <td>{formatDate(invoice.due_date)}</td>
                <td>
                  <StatusMark status={invoice.status} />
                </td>
                <td className="num">{formatMoney(invoice.total_minor, invoice.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
