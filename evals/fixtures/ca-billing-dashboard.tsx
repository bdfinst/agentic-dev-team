import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

interface Customer {
  id: string;
  name: string;
  plan: "starter" | "team" | "enterprise";
}

interface Invoice {
  id: string;
  number: string;
  customerName: string;
  amountCents: number;
  dueDate: string;
  paidAt: string | null;
}

interface CollectionTask {
  id: string;
  title: string;
  assignee: string;
  dueDate: string;
  paidAt: string | null;
}

interface Subscription {
  id: string;
  planName: string;
  seats: number;
  renewalDate: string;
  dueDate: string;
  paidAt: string | null;
}

interface DashboardData {
  customer: Customer;
  invoices: Invoice[];
  tasks: CollectionTask[];
  subscriptions: Subscription[];
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

const MILLIS_PER_DAY = 86_400_000;

function formatCents(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(
    new Date(isoDate),
  );
}

export function Panel({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel__header">
        <h2 className="panel__title">{title}</h2>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="empty-state">{message}</p>;
}

export function DataTable({
  columns,
  children,
}: {
  columns: string[];
  children: ReactNode;
}) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Session context: the customer is read where it is needed, not passed down.
// ---------------------------------------------------------------------------

const CustomerContext = createContext<Customer | null>(null);

function useCustomer(): Customer {
  const customer = useContext(CustomerContext);
  if (!customer)
    throw new Error("useCustomer must be used inside BillingDashboard");
  return customer;
}

function CustomerSummary() {
  const customer = useCustomer();
  return (
    <Panel title="Account">
      <dl className="summary">
        <dt>Customer</dt>
        <dd>{customer.name}</dd>
        <dt>Plan</dt>
        <dd>{customer.plan}</dd>
      </dl>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

function InvoiceRow({
  invoice,
  onSelect,
}: {
  invoice: Invoice;
  onSelect: (id: string) => void;
}) {
  const today = new Date();
  const due = new Date(invoice.dueDate);
  const isOverdue = invoice.paidAt === null && due < today;
  const dayDelta = Math.ceil(
    Math.abs(due.getTime() - today.getTime()) / MILLIS_PER_DAY,
  );
  return (
    <tr onClick={() => onSelect(invoice.id)}>
      <td>{invoice.number}</td>
      <td>{invoice.customerName}</td>
      <td>{formatCents(invoice.amountCents)}</td>
      <td>{formatDate(invoice.dueDate)}</td>
      <td>
        {invoice.paidAt !== null ? (
          <span className="badge badge--paid">Paid</span>
        ) : (
          <span
            className={
              isOverdue ? "badge badge--overdue" : "badge badge--pending"
            }
          >
            {isOverdue
              ? `Overdue by ${dayDelta} days`
              : `Due in ${dayDelta} days`}
          </span>
        )}
      </td>
    </tr>
  );
}

function InvoicesPanel({
  invoices,
  onSelect,
}: {
  invoices: Invoice[];
  onSelect: (id: string) => void;
}) {
  const [showPaid, setShowPaid] = useState(false);
  const visible = useMemo(
    () =>
      showPaid
        ? invoices
        : invoices.filter((invoice) => invoice.paidAt === null),
    [invoices, showPaid],
  );
  return (
    <Panel
      title="Invoices"
      actions={
        <label>
          <input
            type="checkbox"
            checked={showPaid}
            onChange={(event) => setShowPaid(event.target.checked)}
          />
          Show paid
        </label>
      }
    >
      {visible.length === 0 ? (
        <EmptyState message="No open invoices." />
      ) : (
        <DataTable columns={["Number", "Customer", "Amount", "Due", "Status"]}>
          {visible.map((invoice) => (
            <InvoiceRow
              key={invoice.id}
              invoice={invoice}
              onSelect={onSelect}
            />
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Collection tasks
// ---------------------------------------------------------------------------

function TaskRow({
  task,
  onSelect,
}: {
  task: CollectionTask;
  onSelect: (id: string) => void;
}) {
  const today = new Date();
  const due = new Date(task.dueDate);
  const isOverdue = task.paidAt === null && due < today;
  const dayDelta = Math.ceil(
    Math.abs(due.getTime() - today.getTime()) / MILLIS_PER_DAY,
  );
  return (
    <tr onClick={() => onSelect(task.id)}>
      <td>{task.title}</td>
      <td>{task.assignee}</td>
      <td>{formatDate(task.dueDate)}</td>
      <td>
        {task.paidAt !== null ? (
          <span className="badge badge--paid">Paid</span>
        ) : (
          <span
            className={
              isOverdue ? "badge badge--overdue" : "badge badge--pending"
            }
          >
            {isOverdue
              ? `Overdue by ${dayDelta} days`
              : `Due in ${dayDelta} days`}
          </span>
        )}
      </td>
    </tr>
  );
}

function TasksPanel({
  tasks,
  onSelect,
}: {
  tasks: CollectionTask[];
  onSelect: (id: string) => void;
}) {
  return (
    <Panel title="Collection tasks">
      {tasks.length === 0 ? (
        <EmptyState message="Nothing to chase." />
      ) : (
        <DataTable columns={["Task", "Assignee", "Due", "Status"]}>
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} onSelect={onSelect} />
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Subscriptions
// ---------------------------------------------------------------------------

function SubscriptionRow({
  subscription,
  onSelect,
}: {
  subscription: Subscription;
  onSelect: (id: string) => void;
}) {
  const today = new Date();
  const due = new Date(subscription.dueDate);
  const isOverdue = subscription.paidAt === null && due < today;
  const dayDelta = Math.ceil(
    Math.abs(due.getTime() - today.getTime()) / MILLIS_PER_DAY,
  );
  return (
    <tr onClick={() => onSelect(subscription.id)}>
      <td>{subscription.planName}</td>
      <td>{subscription.seats}</td>
      <td>{formatDate(subscription.renewalDate)}</td>
      <td>
        {subscription.paidAt !== null ? (
          <span className="badge badge--paid">Paid</span>
        ) : (
          <span
            className={
              isOverdue ? "badge badge--overdue" : "badge badge--pending"
            }
          >
            {isOverdue
              ? `Overdue by ${dayDelta} days`
              : `Due in ${dayDelta} days`}
          </span>
        )}
      </td>
    </tr>
  );
}

function SubscriptionsPanel({
  subscriptions,
  onSelect,
}: {
  subscriptions: Subscription[];
  onSelect: (id: string) => void;
}) {
  return (
    <Panel title="Subscriptions">
      {subscriptions.length === 0 ? (
        <EmptyState message="No active subscriptions." />
      ) : (
        <DataTable columns={["Plan", "Seats", "Renews", "Status"]}>
          {subscriptions.map((subscription) => (
            <SubscriptionRow
              key={subscription.id}
              subscription={subscription}
              onSelect={onSelect}
            />
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BillingDashboard({
  data,
  onSelect,
}: {
  data: DashboardData;
  onSelect: (id: string) => void;
}) {
  return (
    <CustomerContext.Provider value={data.customer}>
      <main className="billing-dashboard">
        <h1>Billing</h1>
        <CustomerSummary />
        <InvoicesPanel invoices={data.invoices} onSelect={onSelect} />
        <TasksPanel tasks={data.tasks} onSelect={onSelect} />
        <SubscriptionsPanel
          subscriptions={data.subscriptions}
          onSelect={onSelect}
        />
      </main>
    </CustomerContext.Provider>
  );
}
