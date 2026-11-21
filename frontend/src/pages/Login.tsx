import { type FormEvent, useState } from "react";
import { api, setCsrfToken, useAction } from "../api.ts";
import { ErrorNote } from "../components/ui.tsx";

export default function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async () => {
      const session = await api<{ csrf_token: string }>("/auth/login", {
        method: "POST",
        body: { password },
      });
      setCsrfToken(session.csrf_token);
      onSignedIn();
    });
  }

  return (
    <main className="login">
      <form onSubmit={submit}>
        <h1 className="wordmark">solodesk</h1>
        <p>Clients, hours and invoices, on your own machine.</p>
        <label className="field">
          <span className="field-label">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            required
          />
        </label>
        <ErrorNote message={error} />
        <button type="submit" className="btn btn-primary" disabled={busy}>
          Sign in
        </button>
      </form>
    </main>
  );
}
