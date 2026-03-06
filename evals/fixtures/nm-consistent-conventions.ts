// PASS: Consistent naming, no abbreviations, named constants for magic values.

const MAX_LOGIN_ATTEMPTS = 5;
const SESSION_TIMEOUT_SECONDS = 1800;
const MINIMUM_PASSWORD_LENGTH = 12;
const TOKEN_EXPIRY_HOURS = 24;

type AuthenticationStatus = "authenticated" | "expired" | "locked" | "unknown";

interface AuthenticationResult {
  status: AuthenticationStatus;
  sessionToken: string | null;
  failedAttemptCount: number;
  isAccountLocked: boolean;
}

interface UserCredentials {
  emailAddress: string;
  passwordHash: string;
  failedLoginCount: number;
  lastLoginTimestamp: number;
}

function authenticateUser(
  credentials: UserCredentials,
  submittedPassword: string,
): AuthenticationResult {
  const isAccountLocked =
    credentials.failedLoginCount >= MAX_LOGIN_ATTEMPTS;

  if (isAccountLocked) {
    return {
      status: "locked",
      sessionToken: null,
      failedAttemptCount: credentials.failedLoginCount,
      isAccountLocked: true,
    };
  }

  const isPasswordValid = verifyPassword(
    submittedPassword,
    credentials.passwordHash,
  );

  if (!isPasswordValid) {
    const updatedFailedCount = credentials.failedLoginCount + 1;
    return {
      status: "unknown",
      sessionToken: null,
      failedAttemptCount: updatedFailedCount,
      isAccountLocked: updatedFailedCount >= MAX_LOGIN_ATTEMPTS,
    };
  }

  const sessionToken = generateSessionToken(TOKEN_EXPIRY_HOURS);

  return {
    status: "authenticated",
    sessionToken,
    failedAttemptCount: 0,
    isAccountLocked: false,
  };
}

function isSessionExpired(lastActivityTimestamp: number): boolean {
  const currentTimestamp = Math.floor(Date.now() / 1000);
  const elapsedSeconds = currentTimestamp - lastActivityTimestamp;
  return elapsedSeconds > SESSION_TIMEOUT_SECONDS;
}

function isPasswordLongEnough(password: string): boolean {
  return password.length >= MINIMUM_PASSWORD_LENGTH;
}

declare function verifyPassword(plain: string, hash: string): boolean;
declare function generateSessionToken(expiryHours: number): string;
