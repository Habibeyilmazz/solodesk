import type { Project } from "../api.ts";

/** <option>s for a project <select>, grouped under their clients. */
export function ProjectOptions({ projects }: { projects: Project[] }) {
  const byClient = Map.groupBy(projects, (p) => p.client_name);
  return [...byClient].map(([client, list]) => (
    <optgroup key={client} label={client}>
      {list.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </optgroup>
  ));
}
