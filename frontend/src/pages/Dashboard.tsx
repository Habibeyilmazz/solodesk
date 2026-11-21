import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type CurrencyStats, type Dashboard as DashboardData, useLoad } from "../api.ts";
import { ErrorNote, PageHeader } from "../components/ui.tsx";
import { formatMoney } from "../lib/money.ts";
import { formatDate, formatDuration } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";

const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short" });
const MONTH_YEAR = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" });
const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
const monthDate = (month: string) => new Date(`${month}-01T00:00:00`);

export default function Dashboard() {
  const { version } = useRefresh();
  const { data, error } = useLoad(() => api<DashboardData>("/dashboard"), [version]);
  const [picked, setPicked] = useState("");

  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const currency = data.currencies.includes(picked) ? picked : data.currencies[0];
  const stats = currency ? data.by_currency[currency] : null;

  return (
    <>
      <PageHeader title="Dashboard">
        {data.currencies.length > 1 && (
          <div className="segmented" role="group" aria-label="Currency">
            {data.currencies.map((c) => (
              <button key={c} type="button" aria-pressed={c === currency} onClick={() => setPicked(c)}>
                {c}
              </button>
            ))}
          </div>
        )}
      </PageHeader>

      {stats ? (
        <Money stats={stats} currency={currency} />
      ) : (
        <p className="empty">
          Nothing invoiced yet. <Link to="/clients">Add a client</Link>, track some time, then{" "}
          <Link to="/invoices/new">create your first invoice</Link>.
        </p>
      )}

      <section className="panel week" aria-labelledby="week-title">
        <div>
          <h2 id="week-title">Hours this week</h2>
          <p className="figure">{formatDuration(data.week.total_minutes)}</p>
          {data.unbilled_minutes > 0 && (
            <p className="muted">
              {formatDuration(data.unbilled_minutes)} of billable time is not on an invoice yet.{" "}
              <Link to="/invoices/new">Invoice it</Link>
            </p>
          )}
        </div>
        <WeekBars days={data.week.days} />
      </section>
    </>
  );
}

function Money({ stats, currency }: { stats: CurrencyStats; currency: string }) {
  const best = Math.max(...stats.top_clients.map((c) => c.net_minor), 1);
  return (
    <>
      <div className="dash-grid">
        <section className="panel" aria-labelledby="revenue-title">
          <h2 id="revenue-title">Revenue, last 12 months</h2>
          <RevenueChart months={stats.revenue_by_month} currency={currency} total={stats.revenue_minor} />
        </section>

        <section className="panel" aria-labelledby="unpaid-title">
          <h2 id="unpaid-title">Unpaid</h2>
          <p className="figure">{formatMoney(stats.unpaid_minor, currency)}</p>
          <p className="muted">
            {stats.unpaid_count === 0
              ? "Every sent invoice has been paid."
              : `Across ${count(stats.unpaid_count, "invoice")}, tax included.`}
          </p>
          {stats.overdue_count > 0 && (
            <p className="overdue-note">
              <strong>{formatMoney(stats.overdue_minor, currency)}</strong> is overdue (
              <Link to="/invoices?status=overdue">{count(stats.overdue_count, "invoice")}</Link>).
            </p>
          )}
          {stats.open_invoices.length > 0 && (
            <ul className="open-invoices">
              {stats.open_invoices.map((invoice) => (
                <li key={invoice.id}>
                  <Link to={`/invoices/${invoice.id}`}>{invoice.number}</Link>
                  <span className="num">{formatMoney(invoice.total_minor, currency)}</span>
                  <span className="muted">{invoice.client_name}</span>
                  <span className={invoice.overdue ? "num late" : "num muted"}>
                    {invoice.overdue ? "Was due" : "Due"} {formatDate(invoice.due_date)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel" aria-labelledby="clients-title">
        <h2 id="clients-title">Top clients, last 12 months</h2>
        {stats.top_clients.length === 0 ? (
          <p className="muted">No paid invoices in {currency} yet.</p>
        ) : (
          <table className="ledger top-clients">
            <tbody>
              {stats.top_clients.map((client) => (
                <tr key={client.client_id}>
                  <th scope="row">{client.name}</th>
                  <td className="share">
                    <span style={{ width: `${(client.net_minor / best) * 100}%` }} />
                  </td>
                  <td className="num">{formatMoney(client.net_minor, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function count(n: number, noun: string) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function RevenueChart(props: {
  months: CurrencyStats["revenue_by_month"];
  currency: string;
  total: number;
}) {
  const { months, currency } = props;
  const [focus, setFocus] = useState<number | null>(null);
  const max = Math.max(...months.map((m) => m.net_minor), 1);
  const width = 600;
  const height = 180;
  const slot = width / months.length;
  const shown = focus === null ? null : months[focus];

  return (
    <figure className="chart">
      <figcaption>
        <span className="figure">
          {formatMoney(shown ? shown.net_minor : props.total, currency)}
        </span>
        <span className="muted">
          {shown ? MONTH_YEAR.format(monthDate(shown.month)) : "Paid invoices, before tax"}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height + 22}`} role="group" aria-label="Revenue per month">
        <line x1="0" x2={width} y1={height + 0.5} y2={height + 0.5} className="axis" />
        {months.map((m, i) => {
          const bar = Math.round((m.net_minor / max) * (height - 4));
          return (
            <g
              key={m.month}
              tabIndex={0}
              role="img"
              aria-label={`${MONTH_YEAR.format(monthDate(m.month))}: ${formatMoney(m.net_minor, currency)}`}
              className={i === focus ? "bar is-focus" : "bar"}
              onMouseEnter={() => setFocus(i)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(i)}
              onBlur={() => setFocus(null)}
            >
              <rect x={i * slot} y="0" width={slot} height={height + 22} className="hit" />
              <rect x={i * slot + slot * 0.18} y={height - bar} width={slot * 0.64} height={bar} />
              <text x={i * slot + slot / 2} y={height + 16} textAnchor="middle">
                {MONTH.format(monthDate(m.month))}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

function WeekBars({ days }: { days: DashboardData["week"]["days"] }) {
  const max = Math.max(...days.map((d) => d.minutes), 60);
  return (
    <ol className="week-bars">
      {days.map((day) => (
        <li key={day.date}>
          <span className="week-value">{day.minutes > 0 ? formatDuration(day.minutes) : ""}</span>
          <span className="week-bar" style={{ height: `${(day.minutes / max) * 100}%` }} />
          <span className="week-day">{WEEKDAY.format(new Date(`${day.date}T00:00:00`))}</span>
        </li>
      ))}
    </ol>
  );
}
