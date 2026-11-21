import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Client, type Project, useLoad } from "../api.ts";
import { Dialog, ErrorNote, Field, PageHeader } from "../components/ui.tsx";
import { CURRENCIES, formatMoney, hundredthsToInput, parseHundredths } from "../lib/money.ts";
import { formatDuration } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

type Editing =
  | { kind: "client"; client?: Client }
  | { kind: "project"; client: Client; project?: Project }
  | null;

export default function Clients() {
  const { version, bump } = useRefresh();
  const clients = useLoad(() => api<Client[]>("/clients"), [version]);
  const projects = useLoad(() => api<Project[]>("/projects"), [version]);
  const [editing, setEditing] = useState<Editing>(null);
  const close = () => setEditing(null);
  const saved = () => {
    close();
    bump();
  };

  return (
    <>
      <PageHeader title="Clients">
        <button type="button" className="btn btn-primary" onClick={() => setEditing({ kind: "client" })}>
          New client
        </button>
      </PageHeader>
      <ErrorNote message={clients.error || projects.error} />

      {clients.data?.length === 0 && (
        <p className="empty">
          No clients yet. Add the first one, then give it a project with an hourly rate.
        </p>
      )}

      {clients.data?.map((client) => {
        const own = (projects.data ?? []).filter((p) => p.client_id === client.id);
        return (
          <section key={client.id} className="client" aria-label={client.name}>
            <header>
              <div>
                <h2>{client.name}</h2>
                <p className="muted">
                  Billed in {client.currency}
                  {client.email && `, ${client.email}`}
                </p>
              </div>
              <div className="actions">
                <button type="button" className="link" onClick={() => setEditing({ kind: "client", client })}>
                  Edit client<span className="sr-only"> {client.name}</span>
                </button>
                <button type="button" className="link" onClick={() => setEditing({ kind: "project", client })}>
                  Add project<span className="sr-only"> to {client.name}</span>
                </button>
                <Link to={`/invoices/new?client=${client.id}`}>New invoice</Link>
              </div>
            </header>
            {own.length === 0 ? (
              <p className="muted client-empty">No projects yet.</p>
            ) : (
              <table className="ledger">
                <thead>
                  <tr>
                    <th scope="col">Project</th>
                    <th scope="col" className="num col-rate">Hourly rate</th>
                    <th scope="col" className="num col-unbilled">Unbilled</th>
                    <th scope="col" className="col-edit">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {own.map((project) => (
                    <tr key={project.id} className={project.archived ? "is-archived" : ""}>
                      <th scope="row">
                        {project.name}
                        {project.archived && <span className="tag">Archived</span>}
                      </th>
                      <td className="num">{formatMoney(project.hourly_rate_minor, project.currency)}</td>
                      <td className="num">
                        {project.unbilled_minutes ? formatDuration(project.unbilled_minutes) : "None"}
                      </td>
                      <td className="row-actions">
                        <button
                          type="button"
                          className="link"
                          onClick={() => setEditing({ kind: "project", client, project })}
                        >
                          Edit<span className="sr-only"> {project.name}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}

      {editing?.kind === "client" && (
        <Dialog title={editing.client ? "Edit client" : "New client"} onClose={close}>
          <ClientForm client={editing.client} onSaved={saved} onCancel={close} />
        </Dialog>
      )}
      {editing?.kind === "project" && (
        <Dialog
          title={editing.project ? "Edit project" : `New project for ${editing.client.name}`}
          onClose={close}
        >
          <ProjectForm client={editing.client} project={editing.project} onSaved={saved} onCancel={close} />
        </Dialog>
      )}
    </>
  );
}

function useSubmit(onSaved: () => void) {
  const [error, setError] = useState("");
  async function run(request: () => Promise<unknown>) {
    setError("");
    try {
      await request();
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return { error, setError, run };
}

function ClientForm(props: { client?: Client; onSaved: () => void; onCancel: () => void }) {
  const { client } = props;
  const [form, setForm] = useState({
    name: client?.name ?? "",
    email: client?.email ?? "",
    address: client?.address ?? "",
    tax_id: client?.tax_id ?? "",
    currency: client?.currency ?? "TRY",
    notes: client?.notes ?? "",
  });
  const { error, run } = useSubmit(props.onSaved);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  function submit(event: FormEvent) {
    event.preventDefault();
    run(() =>
      api(client ? `/clients/${client.id}` : "/clients", { method: client ? "PUT" : "POST", body: form }),
    );
  }

  return (
    <form onSubmit={submit} className="stack">
      <Field label="Name">
        <input value={form.name} onChange={set("name")} maxLength={200} required autoFocus />
      </Field>
      <Field label="Invoice currency">
        <select value={form.currency} onChange={set("currency")}>
          {CURRENCIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </Field>
      <Field label="Email">
        <input type="email" value={form.email} onChange={set("email")} maxLength={200} />
      </Field>
      <Field label="Billing address">
        <textarea value={form.address} onChange={set("address")} rows={3} maxLength={2000} />
      </Field>
      <Field label="Tax ID">
        <input value={form.tax_id} onChange={set("tax_id")} maxLength={200} />
      </Field>
      <Field label="Notes" hint="Only you see these.">
        <textarea value={form.notes} onChange={set("notes")} rows={2} maxLength={2000} />
      </Field>
      <ErrorNote message={error} />
      <div className="form-actions">
        <button type="submit" className="btn btn-primary">
          {client ? "Save client" : "Add client"}
        </button>
        <button type="button" className="btn" onClick={props.onCancel}>
          Cancel
        </button>
        {client && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => {
              if (confirm(`Delete ${client.name}?`)) {
                run(() => api(`/clients/${client.id}`, { method: "DELETE" }));
              }
            }}
          >
            Delete client
          </button>
        )}
      </div>
    </form>
  );
}

function ProjectForm(props: {
  client: Client;
  project?: Project;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { client, project } = props;
  const [name, setName] = useState(project?.name ?? "");
  const [rate, setRate] = useState(project ? hundredthsToInput(project.hourly_rate_minor) : "");
  const [archived, setArchived] = useState(project?.archived ?? false);
  const { error, setError, run } = useSubmit(props.onSaved);

  function submit(event: FormEvent) {
    event.preventDefault();
    const hourly_rate_minor = parseHundredths(rate || "0");
    if (hourly_rate_minor === null) {
      setError("Enter the rate as a number with up to two decimals, like 1500 or 1500.50.");
      return;
    }
    run(() =>
      project
        ? api(`/projects/${project.id}`, { method: "PUT", body: { name, hourly_rate_minor, archived } })
        : api("/projects", { method: "POST", body: { client_id: client.id, name, hourly_rate_minor } }),
    );
  }

  return (
    <form onSubmit={submit} className="stack">
      <Field label="Project name">
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} required autoFocus />
      </Field>
      <Field label={`Hourly rate (${client.currency})`} hint="Used when you invoice tracked time.">
        <input value={rate} onChange={(e) => setRate(e.target.value)} inputMode="decimal" placeholder="0.00" />
      </Field>
      {project && (
        <label className="check">
          <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
          Archived (hidden from the timer)
        </label>
      )}
      <ErrorNote message={error} />
      <div className="form-actions">
        <button type="submit" className="btn btn-primary">
          {project ? "Save project" : "Add project"}
        </button>
        <button type="button" className="btn" onClick={props.onCancel}>
          Cancel
        </button>
        {project && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => {
              if (confirm(`Delete ${project.name}?`)) {
                run(() => api(`/projects/${project.id}`, { method: "DELETE" }));
              }
            }}
          >
            Delete project
          </button>
        )}
      </div>
    </form>
  );
}
