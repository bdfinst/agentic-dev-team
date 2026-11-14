import { sendEmail } from "./email";

export type NotificationEvent =
  | { kind: "order-placed"; customerId: string; orderId: string }
  | { kind: "order-shipped"; customerId: string; orderId: string };

export async function dispatch(event: NotificationEvent): Promise<void> {
  switch (event.kind) {
    case "order-placed":
      return sendEmail(event.customerId, "order-placed", { orderId: event.orderId });
    case "order-shipped":
      return sendEmail(event.customerId, "order-shipped", { orderId: event.orderId });
  }
}
