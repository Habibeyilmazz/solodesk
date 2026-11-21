import { type FormEvent, useState } from "react";
import { api, type Settings, useLoad } from "../api.ts";
import { ErrorNote, Field, PageHeader } from "../components/ui.tsx";
import { parseHundredths, trimHundredths } from "../lib/money.ts";

export default function SettingsPage() {
  const { data, error } = useLoad(() => api<Settings>("/settings"), []);
  return (
    <>
      <PageHeader title="Settings" />
      <ErrorNote message={error} />
      {data && <SettingsForm settings={data} />}
    </>
  );
}

function SettingsForm({ settings }: { settings: Settings }) {
  const [form, setForm] = useState({
    business_name: settings.business_name,
    business_address: settings.business_address,
    business_email: settings.business_email,
    tax_id: settings.tax_id,
    invoice_prefix: settings.invoice_prefix,
    next_invoice_number: String(settings.next_invoice_number),
    tax: trimHundredths(settings.default_tax_rate_bp),
    payment_terms_days: String(settings.payment_terms_days),
    invoice_footer: settings.invoice_footer,
  });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => {
    setForm({ ...form, [key]: e.target.value });
    setSaved(false);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const default_tax_rate_bp = parseHundredths(form.tax || "0");
    if (default_tax_rate_bp === null || default_tax_rate_bp > 10_000) {
      setError("Default tax is a percentage between 0 and 100.");
      return;
    }
    const { tax: _tax, ...rest } = form;
    try {
      await api("/settings", {
        method: "PUT",
        body: {
          ...rest,
          default_tax_rate_bp,
          next_invoice_number: Number(form.next_invoice_number),
          payment_terms_days: Number(form.payment_terms_days),
        },
      });
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <form onSubmit={submit} className="panel settings">
      <h2>Your business, as shown on invoices</h2>
      <div className="stack">
        <Field label="Business name">
          <input value={form.business_name} onChange={set("business_name")} maxLength={200} required />
        </Field>
        <Field label="Address">
          <textarea value={form.business_address} onChange={set("business_address")} rows={3} maxLength={2000} />
        </Field>
        <Field label="Email">
          <input type="email" value={form.business_email} onChange={set("business_email")} maxLength={200} />
        </Field>
        <Field label="Tax ID">
          <input value={form.tax_id} onChange={set("tax_id")} maxLength={200} />
        </Field>
        <Field label="Invoice footer" hint="Bank details or payment instructions.">
          <textarea value={form.invoice_footer} onChange={set("invoice_footer")} rows={3} maxLength={2000} />
        </Field>
      </div>

      <h2>Invoice defaults</h2>
      <div className="row">
        <Field label="Number prefix" hint="Letters, digits, - / _">
          <input
            value={form.invoice_prefix}
            onChange={set("invoice_prefix")}
            maxLength={20}
            pattern="[A-Za-z0-9/_\-]*"
          />
        </Field>
        <Field label="Next number">
          <input
            type="number"
            min={1}
            step={1}
            value={form.next_invoice_number}
            onChange={set("next_invoice_number")}
            required
          />
        </Field>
        <Field label="Default tax %">
          <input value={form.tax} onChange={set("tax")} inputMode="decimal" />
        </Field>
        <Field label="Payment terms (days)">
          <input
            type="number"
            min={0}
            max={365}
            step={1}
            value={form.payment_terms_days}
            onChange={set("payment_terms_days")}
            required
          />
        </Field>
      </div>

      <ErrorNote message={error} />
      <div className="form-actions">
        <button type="submit" className="btn btn-primary">
          Save settings
        </button>
        {saved && (
          <span className="muted" role="status">
            Settings saved.
          </span>
        )}
      </div>
    </form>
  );
}
