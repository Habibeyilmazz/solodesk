import { type ReactNode, useEffect, useId, useRef } from "react";
import type { InvoiceStatus } from "../api.ts";

/** A modal built on the native <dialog>: focus trapping and Escape come from the browser. */
export function Dialog(props: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  // read during render: by the time effects run, an autofocused field inside has the focus
  const opener = useRef(document.activeElement);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current!;
    if (!dialog.open) dialog.showModal();
    // the dialog is unmounted rather than closed, so hand focus back ourselves
    return () => (opener.current as HTMLElement | null)?.focus();
  }, []);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={props.onClose}>
      <h2 id={titleId}>{props.title}</h2>
      {props.children}
    </dialog>
  );
}

export function Field(props: {
  label: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={`field ${props.className ?? ""}`}>
      <span className="field-label">{props.label}</span>
      {props.children}
      {props.hint && <span className="field-hint">{props.hint}</span>}
    </label>
  );
}

export function ErrorNote({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="error" role="alert">
      {message}
    </p>
  );
}

const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  overdue: "Overdue",
  paid: "Paid",
};

/** Status in a list: a coloured dot and a word, so colour is never the only signal. */
export function StatusMark({ status }: { status: InvoiceStatus }) {
  return <span className={`status status-${status}`}>{STATUS_LABEL[status]}</span>;
}

/** Status on the invoice itself: a rubber stamp. */
export function Stamp({ status }: { status: InvoiceStatus }) {
  return <span className={`stamp status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function PageHeader(props: { title: string; children?: ReactNode }) {
  useEffect(() => {
    document.title = `${props.title} | solodesk`;
  }, [props.title]);
  return (
    <div className="page-header">
      <h1>{props.title}</h1>
      {props.children && <div className="actions">{props.children}</div>}
    </div>
  );
}
