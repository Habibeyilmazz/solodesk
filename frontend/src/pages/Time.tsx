import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project, type TimeEntry, useAction, useLoad } from "../api.ts";
import { ProjectOptions } from "../components/ProjectOptions.tsx";
import { Dialog, ErrorNote, Field, PageHeader } from "../components/ui.tsx";
import {
  addDays,
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
  const from = addDays(isoDate(), -days);
  const entries = useLoad(() => api<TimeEntry[]>(`/time?date_from=${from}&limit=5000`), [version, from]);
  const projects = useLoad(() => api<Project[]>("/projects"), [version]);
  const active = (projects.data ?? []).filter((p) => !p.archived);
  const byDay = Map.groupBy(entries.data ?? [], (e) => e.date);

  return (
    <>
      <PageHeader title="Time">
        <a className="btn" href="/api/export/time.csv" download>
          Export CSV
        </a>
      </PageHeader>

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
