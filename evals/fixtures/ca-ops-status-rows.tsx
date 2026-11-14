import type { ReactNode } from "react";
import { DataTable, StatusBadge, type BadgeTone } from "../ui";

interface Shipment {
  id: string;
  trackingNumber: string;
  carrier: string;
  stage: "label-created" | "in-transit" | "delivered" | "returned";
}

interface SupportTicket {
  id: string;
  subject: string;
  requester: string;
  priority: "low" | "normal" | "urgent";
  slaBreached: boolean;
}

interface Refund {
  id: string;
  orderNumber: string;
  amountCents: number;
  state: "requested" | "approved" | "rejected" | "paid";
}

const SHIPMENT_TONES: Record<Shipment["stage"], BadgeTone> = {
  "label-created": "neutral",
  "in-transit": "info",
  delivered: "success",
  returned: "warning",
};

function ticketTone(ticket: SupportTicket): BadgeTone {
  if (ticket.slaBreached) return "danger";
  return ticket.priority === "urgent" ? "warning" : "neutral";
}

const REFUND_TONES: Record<Refund["state"], BadgeTone> = {
  requested: "neutral",
  approved: "info",
  rejected: "danger",
  paid: "success",
};

function formatCents(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

export function ShipmentRow({ shipment }: { shipment: Shipment }) {
  return (
    <tr>
      <td>{shipment.trackingNumber}</td>
      <td>{shipment.carrier}</td>
      <td>
        <StatusBadge tone={SHIPMENT_TONES[shipment.stage]}>
          {shipment.stage}
        </StatusBadge>
      </td>
    </tr>
  );
}

export function TicketRow({ ticket }: { ticket: SupportTicket }) {
  return (
    <tr>
      <td>{ticket.subject}</td>
      <td>{ticket.requester}</td>
      <td>
        <StatusBadge tone={ticketTone(ticket)}>
          {ticket.slaBreached ? "SLA breached" : ticket.priority}
        </StatusBadge>
      </td>
    </tr>
  );
}

export function RefundRow({ refund }: { refund: Refund }) {
  return (
    <tr>
      <td>{refund.orderNumber}</td>
      <td>{formatCents(refund.amountCents)}</td>
      <td>
        <StatusBadge tone={REFUND_TONES[refund.state]}>
          {refund.state}
        </StatusBadge>
      </td>
    </tr>
  );
}

export function OperationsOverview({
  shipments,
  tickets,
  refunds,
}: {
  shipments: Shipment[];
  tickets: SupportTicket[];
  refunds: Refund[];
}) {
  return (
    <main>
      <h1>Operations</h1>
      <Section title="Shipments">
        <DataTable columns={["Tracking", "Carrier", "Stage"]}>
          {shipments.map((shipment) => (
            <ShipmentRow key={shipment.id} shipment={shipment} />
          ))}
        </DataTable>
      </Section>
      <Section title="Support tickets">
        <DataTable columns={["Subject", "Requester", "Priority"]}>
          {tickets.map((ticket) => (
            <TicketRow key={ticket.id} ticket={ticket} />
          ))}
        </DataTable>
      </Section>
      <Section title="Refunds">
        <DataTable columns={["Order", "Amount", "State"]}>
          {refunds.map((refund) => (
            <RefundRow key={refund.id} refund={refund} />
          ))}
        </DataTable>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
