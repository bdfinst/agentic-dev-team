// FAIL: God object — handles auth, registration, password reset, and email

import crypto from "crypto";

class UserManager {
  private db: any;
  private smtpHost: string;
  private smtpPort: number;
  private tokenSecret: string;

  constructor(db: any) {
    this.db = db;
    this.smtpHost = "smtp.example.com";
    this.smtpPort = 587;
    this.tokenSecret = "s3cret-key";
  }

  async login(email: string, password: string): Promise<string> {
    const user = await this.db.query("SELECT * FROM users WHERE email = ?", [email]);
    if (!user) throw new Error("Invalid credentials");
    const hash = crypto.createHash("sha256").update(password + user.salt).digest("hex");
    if (hash !== user.passwordHash) throw new Error("Invalid credentials");
    const token = crypto.randomBytes(32).toString("hex");
    await this.db.query("INSERT INTO sessions (user_id, token) VALUES (?, ?)", [user.id, token]);
    return token;
  }

  async register(name: string, email: string, password: string): Promise<void> {
    const existing = await this.db.query("SELECT id FROM users WHERE email = ?", [email]);
    if (existing) throw new Error("Email taken");
    const salt = crypto.randomBytes(16).toString("hex");
    const hash = crypto.createHash("sha256").update(password + salt).digest("hex");
    await this.db.query(
      "INSERT INTO users (name, email, password_hash, salt) VALUES (?, ?, ?, ?)",
      [name, email, hash, salt],
    );
    await this.sendEmail(email, "Welcome!", `Hi ${name}, welcome aboard.`);
  }

  async resetPassword(email: string): Promise<void> {
    const user = await this.db.query("SELECT * FROM users WHERE email = ?", [email]);
    if (!user) return; // silent fail to avoid enumeration
    const token = crypto.randomBytes(32).toString("hex");
    const expiry = Date.now() + 3600_000;
    await this.db.query(
      "INSERT INTO password_resets (user_id, token, expiry) VALUES (?, ?, ?)",
      [user.id, token, expiry],
    );
    await this.sendEmail(email, "Password Reset", `Your reset token: ${token}`);
  }

  async confirmReset(token: string, newPassword: string): Promise<void> {
    const reset = await this.db.query("SELECT * FROM password_resets WHERE token = ?", [token]);
    if (!reset || reset.expiry < Date.now()) throw new Error("Invalid or expired token");
    const salt = crypto.randomBytes(16).toString("hex");
    const hash = crypto.createHash("sha256").update(newPassword + salt).digest("hex");
    await this.db.query("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", [hash, salt, reset.user_id]);
    await this.db.query("DELETE FROM password_resets WHERE token = ?", [token]);
  }

  private async sendEmail(to: string, subject: string, body: string): Promise<void> {
    const net = await import("net");
    const socket = net.createConnection(this.smtpPort, this.smtpHost);
    socket.write(`EHLO localhost\r\n`);
    socket.write(`MAIL FROM:<noreply@example.com>\r\n`);
    socket.write(`RCPT TO:<${to}>\r\n`);
    socket.write(`DATA\r\nSubject: ${subject}\r\n\r\n${body}\r\n.\r\n`);
    socket.end(`QUIT\r\n`);
  }
}

export { UserManager };
