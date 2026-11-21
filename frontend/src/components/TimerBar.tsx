import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project, type TimeEntry, useAction, useLoad } from "../api.ts";
import { formatClock } from "../lib/time.ts";
import { useRefresh } from "../refresh.ts";
import { ProjectOptions } from "./ProjectOptions.tsx";

const LAST_PROJECT = "solodesk.lastProject";

/** Always on screen: start a timer in two keystrokes, see it running from any page. */
export function TimerBar() {
  const { version, bump } = useRefresh();
  const projects = useLoad(() => api<Project[]>("/projects"), [version]);
  const timer = useLoad(() => api<TimeEntry | null>("/timer"), [version]);
  const [chosen, setChosen] = useState(() => localStorage.getItem(LAST_PROJECT) ?? "");
  const [description, setDescription] = useState("");
  const { busy, error, run } = useAction();
  const [now, setNow] = useState(() => Date.now());

  const running = timer.data;
  const runningId = running?.id;
  useEffect(() => {
    if (runningId === undefined) return;
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [runningId]);

  const active = (projects.data ?? []).filter((p) => !p.archived);
  const projectId = active.some((p) => String(p.id) === chosen) ? chosen : String(active[0]?.id ?? "");

  function start(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem(LAST_PROJECT, projectId);
    run(async () => {
      await api("/timer/start", {
        method: "POST",
        body: { project_id: Number(projectId), description },
      });
      setDescription("");
      bump();
    });
  }

  function stop() {
    run(async () => {
      await api("/timer/stop", { method: "POST" });
      bump();
    });
  }

  if (running) {
    const elapsed = (now - new Date(running.started_at!).getTime()) / 1000;
    return (
      <section className="timer timer-running" aria-label="Timer">
        <span className="timer-clock" role="timer" aria-label="Elapsed time">
          {formatClock(elapsed)}
        </span>
        <span className="timer-what">
          <strong>{running.project_name}</strong>
          <span>
            {running.client_name}
            {running.description && `, ${running.description}`}
          </span>
        </span>
        <button type="button" className="btn btn-stop" onClick={stop} disabled={busy}>
          Stop timer
        </button>
        {error && <span className="timer-error" role="alert">{error}</span>}
      </section>
    );
  }

  if (projects.data && active.length === 0) {
    return (
      <section className="timer" aria-label="Timer">
        <span className="timer-empty">
          To track time, <Link to="/clients">add a client and a project</Link> first.
        </span>
      </section>
    );
  }

  return (
    <section className="timer" aria-label="Timer">
      <form onSubmit={start}>
        <select aria-label="Project" value={projectId} onChange={(e) => setChosen(e.target.value)} required>
          <ProjectOptions projects={active} />
        </select>
        <input
          aria-label="What are you working on?"
          placeholder="What are you working on?"
          value={description}
          maxLength={500}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={!projectId || busy}>
          Start timer
        </button>
      </form>
      {error && <span className="timer-error" role="alert">{error}</span>}
    </section>
  );
}
