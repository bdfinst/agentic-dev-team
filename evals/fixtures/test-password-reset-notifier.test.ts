import { PasswordResetNotifier } from "../src/password-reset-notifier";
import type { EmailGateway, OutgoingEmail } from "../src/ports/email-gateway";

class RecordingEmailGateway implements EmailGateway {
  readonly sent: OutgoingEmail[] = [];

  async send(email: OutgoingEmail): Promise<void> {
    this.sent.push(email);
  }
}

const RESET_LINK_BASE = "https://app.example.com/reset";
const RESET_TOKEN = "tok-123";
const ACCOUNT = {
  id: "acc-42",
  email: "dana@example.com",
  displayName: "Dana",
};

function makeNotifier(gateway: EmailGateway) {
  return new PasswordResetNotifier(gateway, { resetLinkBase: RESET_LINK_BASE });
}

describe("PasswordResetNotifier", () => {
  it("emails the account holder a reset link carrying the token", async () => {
    const gateway = new RecordingEmailGateway();

    await makeNotifier(gateway).notify(ACCOUNT, RESET_TOKEN);

    expect(gateway.sent).toEqual([
      {
        to: ACCOUNT.email,
        subject: "Reset your password",
        body: expect.stringContaining(`${RESET_LINK_BASE}?token=${RESET_TOKEN}`),
      },
    ]);
  });

  it("sends nothing when the account has no email address", async () => {
    const gateway = new RecordingEmailGateway();
    const noEmail = { ...ACCOUNT, email: null };

    await makeNotifier(gateway).notify(noEmail, RESET_TOKEN);

    expect(gateway.sent).toEqual([]);
  });

  it.each([
    { displayName: "Dana", expectedGreeting: "Hi Dana," },
    { displayName: "", expectedGreeting: "Hi there," },
    { displayName: "   ", expectedGreeting: "Hi there," },
  ])(
    "greets $displayName as '$expectedGreeting'",
    async ({ displayName, expectedGreeting }) => {
      const gateway = new RecordingEmailGateway();

      await makeNotifier(gateway).notify(
        { ...ACCOUNT, displayName },
        RESET_TOKEN,
      );

      const [firstLine] = gateway.sent[0].body.split("\n");
      expect(firstLine).toBe(expectedGreeting);
    },
  );
});
