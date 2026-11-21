import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project, type TimeEntry, useAction, useLoad } from "../api.ts";
import { ProjectOptions } from "../components/ProjectOptions.tsx";
import { Dialog, ErrorNote, Field, PageHeader } from "../components/ui.tsx";
import { CURRENCIES } from "../lib/money.ts";
import {
  addDays,
  daysToCover,
  durationToInput,
  formatDuration,
  formatWeekday,
  isoDate,
  parseDuration,
} from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

const PAGE_DAYS = 30;

export default function Time() {
  const { version, bump } = useRefresh();
  const [days, setDays] = useState(PAGE_DAYS);
  const [editing, setEditing] = useState<TimeEntry | null>(null);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState("");
  const from = addDays(isoDate(), -days);
  const entries = useLoad(() => api<TimeEntry[]>(`/time?date_from=${from}&limit=5000`), [version, from]);
  const projects = useLoad(() => api<Project[]>("/projects"), [version]);
  const active = (projects.data ?? []).filter((p) => !p.archived);
  const byDay = Map.groupBy(entries.data ?? [], (e) => e.date);

  return (
    <>
      <PageHeader title="Time">
        <button type="button" className="btn" onClick={() => setImporting(true)}>
          Import from Toggl
        </button>
        <a className="btn" href="/api/export/time.csv" download>
          Export CSV
        </a>
      </PageHeader>
      {imported && (
        <p className="muted" role="status">
          {imported}
        </p>
      )}

      {projects.data && active.length === 0 ? (
        <p className="empty">
          Time is logged against a project. <Link to="/clients">Add a client and a project</Link> to
          get started.
        </p>
      ) : (
        <section className="panel" aria-labelledby="add-title">
          <h2 id="add-title">Add time by hand</h2>
          <EntryForm projects={active} submitLabel="Add entry" onSaved={bump} />
        </section>
      )}

      <ErrorNote message={entries.error} />
      {entries.data?.length === 0 && (
        <p className="empty">No time logged in the last {days} days.</p>
      )}

      {[...byDay].map(([date, list]) => (
        <section key={date} className="day" aria-label={formatWeekday(date)}>
          <header>
            <h2>{formatWeekday(date)}</h2>
            <span className="num">{formatDuration(list.reduce((sum, e) => sum + e.minutes, 0))}</span>
          </header>
          <table className="ledger stacks">
            <tbody>
              {list.map((entry) => (
                <tr key={entry.id}>
                  <th scope="row">
                    {entry.project_name}
                    <span className="sub">{entry.client_name}</span>
                  </th>
                  <td className="grow">{entry.description}</td>
                  <td className="tag-cell">
                    {entry.invoice_id ? (
                      <Link to={`/invoices/${entry.invoice_id}`} className="tag">
                        {entry.invoice_number ?? "On a draft"}
                      </Link>
                    ) : (
                      !entry.billable && <span className="tag">Not billable</span>
                    )}
                  </td>
                  <td className="num">{formatDuration(entry.minutes)}</td>
                  <td className="row-actions">
                    {!entry.invoice_id && (
                      <button type="button" className="link" onClick={() => setEditing(entry)}>
                        Edit<span className="sr-only"> {entry.project_name} entry</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      {entries.data && (
        <p className="more">
          <button type="button" className="btn" onClick={() => setDays(days + PAGE_DAYS)}>
            Show {PAGE_DAYS} more days
          </button>
        </p>
      )}

      {importing && (
        <Dialog title="Import from Toggl Track" onClose={() => setImporting(false)}>
          <ImportForm
            onCancel={() => setImporting(false)}
            onImported={(message, earliest) => {
              setImporting(false);
              setImported(message);
              // imported history is usually older than the listed range: widen it to show it all
              if (earliest) setDays(Math.max(days, daysToCover(earliest, PAGE_DAYS)));
              bump();
            }}
          />
        </Dialog>
      )}

      {editing && (
        <Dialog title="Edit time entry" onClose={() => setEditing(null)}>
          <EntryForm
            projects={projects.data ?? []}
            entry={editing}
            submitLabel="Save entry"
            onSaved={() => {
              setEditing(null);
              bump();
            }}
            onCancel={() => setEditing(null)}
          />
        </Dialog>
      )}
    </>
  );
}

function EntryForm(props: {
  projects: Project[];
  entry?: TimeEntry;
  submitLabel: string;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const { entry } = props;
  const [projectId, setProjectId] = useState(entry ? String(entry.project_id) : "");
  const [date, setDate] = useState(entry?.date ?? isoDate());
  const [duration, setDuration] = useState(entry ? durationToInput(entry.minutes) : "");
  const [description, setDescription] = useState(entry?.description ?? "");
  const [billable, setBillable] = useState(entry?.billable ?? true);
  const { busy, error, setError, run } = useAction();
  const selected = projectId || String(props.projects[0]?.id ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    const minutes = parseDuration(duration);
    if (minutes === null) {
      setError("Enter a duration like 1:30, 1.5 or 90m (up to 24 hours).");
      return;
    }
    const body = { project_id: Number(selected), date, minutes, description, billable };
    run(async () => {
      await api(entry ? `/time/${entry.id}` : "/time", { method: entry ? "PUT" : "POST", body });
      if (!entry) {
        setDuration("");
        setDescription("");
      }
      props.onSaved();
    });
  }

  return (
    <form onSubmit={submit} className={entry ? "stack" : "entry-form"}>
      <Field label="Date">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      </Field>
      <Field label="Project">
        <select value={selected} onChange={(e) => setProjectId(e.target.value)} required>
          <ProjectOptions projects={props.projects} />
        </select>
      </Field>
      <Field label="Duration">
        <input
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          placeholder="1:30"
          inputMode="decimal"
          required
        />
      </Field>
      <Field label="Description" className="grow">
        <input value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <label className="check">
        <input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} />
        Billable
      </label>
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {props.submitLabel}
        </button>
        {entry && (
          <>
            <button type="button" className="btn" onClick={props.onCancel}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => {
                if (confirm("Delete this time entry?")) {
                  run(async () => {
                    await api(`/time/${entry.id}`, { method: "DELETE" });
                    props.onSaved();
                  });
                }
              }}
            >
              Delete entry
            </button>
          </>
        )}
      </div>
      <ErrorNote message={error} />
    </form>
  );
}

type ImportResult = {
  added: number;
  minutes: number;
  skipped_duplicates: number;
  earliest_date: string | null;
  new_clients: string[];
  new_projects: string[];
};

/** Pick a Toggl CSV, see what it would add (a dry run), then import it. */
function ImportForm(props: {
  onCancel: () => void;
  onImported: (message: string, earliest: string | null) => void;
}) {
  const [csv, setCsv] = useState("");
  const [currency, setCurrency] = useState("TRY");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const { busy, error, setError, run } = useAction();

  function check(text: string, newCurrency: string) {
    setPreview(null);
    run(async () =>
      setPreview(
        await api<ImportResult>("/import/toggl", {
          method: "POST",
          body: { csv: text, currency: newCurrency, dry_run: true },
        }),
      ),
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async () => {
      const r = await api<ImportResult>("/import/toggl", {
        method: "POST",
        body: { csv, currency },
      });
      props.onImported(
        `Imported ${r.added} ${r.added === 1 ? "entry" : "entries"} (${formatDuration(r.minutes)}).` +
          (r.skipped_duplicates ? ` Skipped ${r.skipped_duplicates} already here.` : ""),
        r.earliest_date,
      );
    });
  }

  return (
    <form onSubmit={submit} className="stack">
      <p className="muted">
        In Toggl Track, open Reports, Detailed, and export it as CSV. Clients and projects are
        matched by name; entries already here are skipped.
      </p>
      <Field label="Toggl CSV file">
        <input
          type="file"
          accept=".csv,text/csv"
          required
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            if (file.size > 5_000_000) {
              setPreview(null);
              setError("That file is over 5 MB. Export a shorter date range.");
              return;
            }
            const text = await file.text();
            setCsv(text);
            check(text, currency);
          }}
        />
      </Field>
      <Field label="Currency for new clients">
        <select
          value={currency}
          onChange={(e) => {
            setCurrency(e.target.value);
            if (csv) check(csv, e.target.value);
          }}
        >
          {CURRENCIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </Field>
      {preview && (
        <div role="status">
          <p>
            {preview.added === 0
              ? "Nothing new to import."
              : `${preview.added} ${preview.added === 1 ? "entry" : "entries"}, ${formatDuration(preview.minutes)} in total.`}
            {preview.skipped_duplicates > 0 &&
              ` ${preview.skipped_duplicates} already here will be skipped.`}
          </p>
          {preview.new_clients.length > 0 && (
            <p>New clients: {preview.new_clients.join(", ")}.</p>
          )}
          {preview.new_projects.length > 0 && (
            <p>
              New projects, with an hourly rate of 0 until you set one under Clients:{" "}
              {preview.new_projects.join(", ")}.
            </p>
          )}
        </div>
      )}
      <ErrorNote message={error} />
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy || !preview?.added}>
          Import
        </button>
        <button type="button" className="btn" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
