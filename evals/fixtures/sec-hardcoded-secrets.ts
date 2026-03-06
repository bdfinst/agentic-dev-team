import axios from "axios";
import jwt from "jsonwebtoken";
import nodemailer from "nodemailer";

// ISSUE: Hardcoded JWT secret
const JWT_SECRET = "EXAMPLE-jwt-key-not-real-00000000";

// ISSUE: Hardcoded API key (obviously fake — for eval fixture only)
const STRIPE_API_KEY = "sk_test_EXAMPLE000000000000000000";

// ISSUE: Hardcoded database password
const DB_CONFIG = {
  host: "db.internal.example.com",
  port: 5432,
  user: "admin",
  password: "EXAMPLE-db-password-not-real",
  database: "app_production",
};

// ISSUE: Hardcoded SMTP credentials
const emailTransport = nodemailer.createTransport({
  host: "smtp.example.com",
  port: 587,
  auth: {
    user: "notifications@example.com",
    pass: "EXAMPLE-smtp-password-not-real",
  },
});

export function generateToken(userId: string): string {
  return jwt.sign({ userId }, JWT_SECRET, { expiresIn: "24h" });
}

export async function chargeCustomer(customerId: string, amount: number) {
  // ISSUE: Secret logged to console
  console.log(`Charging customer ${customerId} with key ${STRIPE_API_KEY}`);

  const response = await axios.post(
    "https://api.stripe.com/v1/charges",
    { customer: customerId, amount, currency: "usd" },
    { headers: { Authorization: `Bearer ${STRIPE_API_KEY}` } }
  );

  return response.data;
}

export async function sendWelcomeEmail(email: string, name: string) {
  await emailTransport.sendMail({
    from: "notifications@example.com",
    to: email,
    subject: "Welcome!",
    html: `<h1>Welcome, ${name}!</h1>`,
  });
}

export function verifyToken(token: string) {
  try {
    return jwt.verify(token, JWT_SECRET);
  } catch {
    return null;
  }
}
