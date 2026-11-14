import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

export type TicketPriority = "low" | "medium" | "high" | "urgent";

export interface Ticket {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly priority: TicketPriority;
  readonly labels: readonly string[];
  readonly assigneeId: string | null;
  readonly updatedAt: string;
}

export interface Assignee {
  readonly id: string;
  readonly displayName: string;
}

interface TicketDraft {
  readonly title: string;
  readonly description: string;
  readonly priority: TicketPriority;
  readonly labels: readonly string[];
  readonly assigneeId: string | null;
}

type DraftAction =
  | { type: "field"; field: "title" | "description"; value: string }
  | { type: "priority"; value: TicketPriority }
  | { type: "addLabel"; value: string }
  | { type: "removeLabel"; value: string }
  | { type: "assign"; value: string | null }
  | { type: "reset"; ticket: Ticket };

const PRIORITIES: readonly TicketPriority[] = [
  "low",
  "medium",
  "high",
  "urgent",
];
const AUTOSAVE_DELAY_MS = 2_000;
const MAX_LABELS = 8;

function draftFrom(ticket: Ticket): TicketDraft {
  return {
    title: ticket.title,
    description: ticket.description,
    priority: ticket.priority,
    labels: ticket.labels,
    assigneeId: ticket.assigneeId,
  };
}

function draftReducer(draft: TicketDraft, action: DraftAction): TicketDraft {
  switch (action.type) {
    case "field":
      return { ...draft, [action.field]: action.value };
    case "priority":
      return { ...draft, priority: action.value };
    case "addLabel":
      if (
        draft.labels.includes(action.value) ||
        draft.labels.length >= MAX_LABELS
      ) {
        return draft;
      }
      return { ...draft, labels: [...draft.labels, action.value] };
    case "removeLabel":
      return {
        ...draft,
        labels: draft.labels.filter((label) => label !== action.value),
      };
    case "assign":
      return { ...draft, assigneeId: action.value };
    case "reset":
      return draftFrom(action.ticket);
  }
}

function isDirty(draft: TicketDraft, ticket: Ticket): boolean {
  return (
    draft.title !== ticket.title ||
    draft.description !== ticket.description ||
    draft.priority !== ticket.priority ||
    draft.assigneeId !== ticket.assigneeId ||
    draft.labels.join("|") !== ticket.labels.join("|")
  );
}

interface LabelListProps {
  readonly labels: readonly string[];
  readonly onRemove: (label: string) => void;
}

const LabelList = memo(function LabelList({
  labels,
  onRemove,
}: LabelListProps) {
  return (
    <ul className="labels">
      {labels.map((label) => (
        <li key={label}>
          {label}
          <button
            type="button"
            aria-label={`Remove ${label}`}
            onClick={() => onRemove(label)}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
});

interface AssigneePickerProps {
  readonly assignees: readonly Assignee[];
  readonly selectedId: string | null;
  readonly onSelect: (assigneeId: string | null) => void;
}

const AssigneePicker = memo(function AssigneePicker({
  assignees,
  selectedId,
  onSelect,
}: AssigneePickerProps) {
  const handleChange = useCallback(
    (event: ChangeEvent<HTMLSelectElement>) =>
      onSelect(event.target.value || null),
    [onSelect],
  );
  return (
    <select value={selectedId ?? ""} onChange={handleChange}>
      <option value="">Unassigned</option>
      {assignees.map((assignee) => (
        <option key={assignee.id} value={assignee.id}>
          {assignee.displayName}
        </option>
      ))}
    </select>
  );
});

interface TicketEditorProps {
  readonly ticket: Ticket;
  readonly assignees: readonly Assignee[];
  readonly onSave: (ticketId: string, draft: TicketDraft) => Promise<void>;
}

export function TicketEditor({ ticket, assignees, onSave }: TicketEditorProps) {
  const [draft, dispatch] = useReducer(draftReducer, ticket, draftFrom);
  const [newLabel, setNewLabel] = useState("");
  const [saveState, setSaveState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const titleInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    dispatch({ type: "reset", ticket });
  }, [ticket]);

  useEffect(() => {
    titleInputRef.current?.focus();
  }, [ticket.id]);

  const dirty = useMemo(() => isDirty(draft, ticket), [draft, ticket]);

  const save = useCallback(async () => {
    setSaveState("saving");
    try {
      await onSave(ticket.id, draft);
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }, [onSave, ticket.id]);

  useEffect(() => {
    if (!dirty) return undefined;
    const timerId = setTimeout(() => {
      void save();
    }, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(timerId);
  }, [dirty, draft, save]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const removeLabel = useCallback(
    (label: string) => dispatch({ type: "removeLabel", value: label }),
    [],
  );

  const assign = useCallback(
    (assigneeId: string | null) =>
      dispatch({ type: "assign", value: assigneeId }),
    [],
  );

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void save();
  };

  const handleAddLabel = () => {
    const label = newLabel.trim();
    if (label === "") return;
    dispatch({ type: "addLabel", value: label });
    setNewLabel("");
  };

  return (
    <form className="ticket-editor" onSubmit={handleSubmit}>
      <label>
        Title
        <input
          ref={titleInputRef}
          value={draft.title}
          onChange={(event) =>
            dispatch({
              type: "field",
              field: "title",
              value: event.target.value,
            })
          }
        />
      </label>
      <label>
        Description
        <textarea
          value={draft.description}
          onChange={(event) =>
            dispatch({
              type: "field",
              field: "description",
              value: event.target.value,
            })
          }
        />
      </label>
      <fieldset>
        <legend>Priority</legend>
        {PRIORITIES.map((priority) => (
          <label key={priority}>
            <input
              type="radio"
              name="priority"
              checked={draft.priority === priority}
              onChange={() => dispatch({ type: "priority", value: priority })}
            />
            {priority}
          </label>
        ))}
      </fieldset>
      <LabelList labels={draft.labels} onRemove={removeLabel} />
      <div className="add-label">
        <input
          value={newLabel}
          onChange={(event) => setNewLabel(event.target.value)}
        />
        <button type="button" onClick={handleAddLabel}>
          Add label
        </button>
      </div>
      <AssigneePicker
        assignees={assignees}
        selectedId={draft.assigneeId}
        onSelect={assign}
      />
      <footer>
        <span className={`save-state save-state--${saveState}`}>
          {saveState}
        </span>
        <button type="submit" disabled={!dirty || saveState === "saving"}>
          Save
        </button>
        <button
          type="button"
          onClick={() => dispatch({ type: "reset", ticket })}
        >
          Discard changes
        </button>
      </footer>
    </form>
  );
}
