import type { Mailer } from "./mailer";

let mailer: Mailer;

export function configureMailer(m: Mailer): void {
  mailer = m;
}

export async function sendEmail(customerId: string, template: string, data: object): Promise<void> {
  await mailer.send({ to: customerId, template, data });
}
