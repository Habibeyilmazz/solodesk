import { useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, ApiError, setCsrfToken, setSignedOutHandler } from "./api.ts";
import { TimerBar } from "./components/TimerBar.tsx";
import { RefreshContext } from "./refresh.ts";
import Clients from "./pages/Clients.tsx";
import Dashboard from "./pages/Dashboard.tsx";
import InvoiceDetail from "./pages/InvoiceDetail.tsx";
import InvoiceNew from "./pages/InvoiceNew.tsx";
import Invoices from "./pages/Invoices.tsx";
import Login from "./pages/Login.tsx";
import SettingsPage from "./pages/Settings.tsx";
import Time from "./pages/Time.tsx";

type Session = { authenticated: boolean; csrf_token?: string };

export default function App() {
  const [auth, setAuth] = useState<"loading" | "in" | "out">("loading");

  useEffect(() => {
    setSignedOutHandler(() => setAuth("out"));
    api<Session>("/auth/session").then(
      (session) => {
        if (session.csrf_token) setCsrfToken(session.csrf_token);
        setAuth(session.authenticated ? "in" : "out");
      },
      () => setAuth("out"),
    );
  }, []);

  if (auth === "loading") return null;
  if (auth === "out") return <Login onSignedIn={() => setAuth("in")} />;
  return <Shell onSignedOut={() => setAuth("out")} />;
}

const NAV = [
  ["/", "Dashboard"],
  ["/time", "Time"],
  ["/clients", "Clients"],
  ["/invoices", "Invoices"],
  ["/settings", "Settings"],
] as const;

function Shell({ onSignedOut }: { onSignedOut: () => void }) {
  // One counter for the whole app: any change bumps it and every loaded list refetches.
  const [version, setVersion] = useState(0);
  const refresh = useMemo(() => ({ version, bump: () => setVersion((v) => v + 1) }), [version]);

  async function signOut() {
    try {
      await api("/auth/logout", { method: "POST" });
      onSignedOut();
    } catch (e) {
      // a 401 means the session is already gone, and the app has switched to the sign-in page
      if ((e as ApiError).status !== 401) alert(`You are still signed in. ${(e as Error).message}`);
    }
  }

  return (
    <RefreshContext.Provider value={refresh}>
      <div className="shell">
        <a className="skip" href="#main">
          Skip to content
        </a>
        <header className="cover">
          <NavLink to="/" className="wordmark">
            solodesk
          </NavLink>
          <nav aria-label="Main">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"}>
                {label}
              </NavLink>
            ))}
          </nav>
          <button type="button" className="signout" onClick={signOut}>
            Sign out
          </button>
        </header>
        <div className="desk">
          <TimerBar />
          <main id="main" tabIndex={-1}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/time" element={<Time />} />
              <Route path="/clients" element={<Clients />} />
              <Route path="/invoices" element={<Invoices />} />
              <Route path="/invoices/new" element={<InvoiceNew />} />
              <Route path="/invoices/:id" element={<InvoiceDetail />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}
