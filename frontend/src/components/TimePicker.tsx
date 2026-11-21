import type { TimeEntry } from "../api.ts";
import { formatDate, formatDuration } from "../lib/time.ts";

/** Unbilled entries with a checkbox each. Entries are included unless unticked. */
export function TimePicker(props: {
  entries: TimeEntry[];
  excluded: Set<number>;
  onToggle: (id: number) => void;
}) {
  return (
    <table className="ledger pick stacks">
      <thead>
        <tr>
          <th scope="col">
            <span className="sr-only">Include</span>
          </th>
          <th scope="col">Date</th>
          <th scope="col">Project</th>
          <th scope="col">Description</th>
          <th scope="col" className="num">Time</th>
        </tr>
      </thead>
      <tbody>
        {props.entries.map((entry) => (
          <tr key={entry.id}>
            <td>
              <input
                type="checkbox"
                aria-label={`Include ${entry.project_name}, ${formatDate(entry.date)}, ${formatDuration(entry.minutes)}`}
                checked={!props.excluded.has(entry.id)}
                onChange={() => props.onToggle(entry.id)}
              />
            </td>
            <td className="small">{formatDate(entry.date)}</td>
            <td>{entry.project_name}</td>
            <td className="grow">{entry.description}</td>
            <td className="num">{formatDuration(entry.minutes)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Toggle an id in a set, returning a new set (for React state). */
export function toggled(set: Set<number>, id: number): Set<number> {
  const next = new Set(set);
  if (!next.delete(id)) next.add(id);
  return next;
}
