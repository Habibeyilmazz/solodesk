import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Client, type Invoice, type TimeEntry, useAction, useLoad } from "../api.ts";
import { TimePicker, toggled } from "../components/TimePicker.tsx";
import { ErrorNote, Field, PageHeader } from "../components/ui.tsx";
import { formatDuration } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

export default function InvoiceNew() {
  const { version, bump } = useRefresh();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const clients = useLoad(() => api<Client[]>("/clients"), [version]);
  const [picked, setPicked] = useState(params.get("client") ?? "");
  const clientId = picked || String(clients.data?.[0]?.id ?? "");
  const entries = useLoad(
    () =>
      clientId
        ? api<TimeEntry[]>(`/time?unbilled=true&client_id=${clientId}&limit=5000`)
        : Promise.resolve([]),
    [version, clientId],
  );
  // Entries are included unless unticked, so new ones arriving stay selected.
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const { busy, error, run } = useAction();

  const list = entries.data ?? [];
  const included = list.filter((e) => !excluded.has(e.id));
  const minutes = included.reduce((sum, e) => sum + e.minutes, 0);

  function create() {
    run(async () => {
      const invoice = await api<Invoice>("/invoices", {
        method: "POST",
        body: { client_id: Number(clientId), time_entry_ids: included.map((e) => e.id) },
      });
      bump();
      navigate(`/invoices/${invoice.id}`);
    });
  }

  if (clients.data?.length === 0) {
    return (
      <>
        <PageHeader title="New invoice" />
        <p className="empty">
          An invoice needs a client. <Link to="/clients">Add one</Link> first.
        </p>
      </>
    );
  }

  return (
    <>
      <PageHeader title="New invoice" />
      <ErrorNote message={clients.error || entries.error} />
      <div className="panel">
        <Field label="Client" className="narrow">
          <select
            value={clientId}
            onChange={(e) => {
              setPicked(e.target.value);
              setExcluded(new Set());
            }}
          >
            {clients.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.currency})
              </option>
            ))}
          </select>
        </Field>

        <h2>Tracked time to bill</h2>
        {list.length === 0 ? (
          <p className="muted">
            No unbilled time for this client. You can still create the invoice and add fixed-price
            lines.
          </p>
        ) : (
          <TimePicker entries={list} excluded={excluded} onToggle={(id) => setExcluded(toggled(excluded, id))} />
        )}

        <ErrorNote message={error} />
        <div className="form-actions">
          <button type="button" className="btn btn-primary" onClick={create} disabled={!clientId || busy}>
            {included.length > 0 ? `Create draft with ${formatDuration(minutes)}` : "Create empty draft"}
          </button>
          <span className="muted">
            Time becomes one line per project. You can edit everything before sending.
          </span>
        </div>
      </div>
    </>
  );
}
