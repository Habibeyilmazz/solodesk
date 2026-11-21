// Thin wrapper over fetch: sends the CSRF token on writes and turns API errors into messages.
import { useCallback, useEffect, useRef, useState } from "react";

export type Client = {
  id: number;
  name: string;
  email: string;
  address: string;
  tax_id: string;
  currency: string;
  notes: string;
};

export type Project = {
  id: number;
  client_id: number;
  name: string;
  hourly_rate_minor: number;
  archived: boolean;
  client_name: string;
  currency: string;
  unbilled_minutes: number;
};

export type TimeEntry = {
  id: number;
  project_id: number;
  date: string;
  minutes: number;
  description: string;
  billable: boolean;
  invoice_id: number | null;
  started_at: string | null;
  project_name: string;
  client_id: number;
  client_name: string;
  invoice_number: string | null;
};

export type InvoiceStatus = "draft" | "sent" | "overdue" | "paid";

export type InvoiceLine = {
  id: number;
  description: string;
  quantity_hundredths: number;
  unit_price_minor: number;
  amount_minor: number;
  project_id: number | null;
};

export type Invoice = {
  id: number;
  client_id: number;
  client_name: string;
  number: string | null;
  status: InvoiceStatus;
  currency: string;
  issue_date: string;
  due_date: string;
  tax_rate_bp: number;
  discount_bp: number;
  notes: string;
  subtotal_minor: number;
  discount_minor: number;
  tax_minor: number;
  total_minor: number;
  paid_on: string | null;
  lines?: InvoiceLine[];
};

export type Settings = {
  business_name: string;
  business_address: string;
  business_email: string;
  tax_id: string;
  invoice_prefix: string;
  next_invoice_number: number;
  default_tax_rate_bp: number;
  payment_terms_days: number;
  invoice_footer: string;
};

export type CurrencyStats = {
  revenue_by_month: { month: string; net_minor: number }[];
  revenue_minor: number;
  unpaid_minor: number;
  unpaid_count: number;
  overdue_minor: number;
  overdue_count: number;
  open_invoices: {
    id: number;
    number: string;
    client_name: string;
    due_date: string;
    total_minor: number;
    overdue: boolean;
  }[];
  top_clients: { client_id: number; name: string; net_minor: number }[];
};

export type Dashboard = {
  currencies: string[];
  by_currency: Record<string, CurrencyStats>;
  week: { total_minutes: number; days: { date: string; minutes: number }[] };
  unbilled_minutes: number;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let csrfToken = "";
let onSignedOut = () => {};

export function setCsrfToken(token: string) {
  csrfToken = token;
}

/** Called when any request comes back 401, so the app can show the sign-in page. */
export function setSignedOutHandler(handler: () => void) {
  onSignedOut = handler;
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: ["body", "name"], msg: "..."}]
    return detail
      .map((d) => `${(d.loc ?? []).slice(1).join(".") || "request"}: ${d.msg}`)
      .join("; ");
  }
  return `Request failed (${status})`;
}

async function request(path: string, method: string, body: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  try {
    return await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the solodesk server. Is it still running?");
  }
}

export async function api<T = unknown>(
  path: string,
  options: { method?: "GET" | "POST" | "PUT" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  let response = await request(path, method, options.body);
  if (response.status === 403 && method !== "GET") {
    // Signing in again in another tab replaces the session, which leaves this tab holding a
    // stale CSRF token. Pick up the current one and try once more.
    const session = await (await request("/auth/session", "GET", undefined)).json().catch(() => null);
    if (session?.csrf_token) {
      csrfToken = session.csrf_token;
      response = await request(path, method, options.body);
    }
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/login")) onSignedOut();
    throw new ApiError(response.status, describe(data?.detail, response.status));
  }
  return data as T;
}

/**
 * For forms and buttons that change something. Runs one request at a time: `busy` disables
 * the controls, so a double click cannot submit twice, and `error` is the message to show.
 * `run` resolves to whether the request succeeded.
 */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false); // state alone would miss two clicks in the same frame
  async function run(action: () => Promise<unknown>): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}

/** Load data for a page. `reload` refetches; `error` is a message ready to show. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLoad = useCallback(load, deps);
  useEffect(() => {
    let current = true;
    stableLoad().then(
      (result) => {
        if (current) {
          setData(result);
          setError("");
        }
      },
      (e: Error) => current && setError(e.message),
    );
    return () => {
      current = false;
    };
  }, [stableLoad, version]);
  return { data, error, reload: useCallback(() => setVersion((v) => v + 1), []) };
}
