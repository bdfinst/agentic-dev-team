const MAX_LOGIN_ATTEMPTS = 5;
const SESSION_TIMEOUT_SECONDS = 1800;
const MINIMUM_PASSWORD_LENGTH = 12;
const TOKEN_EXPIRY_HOURS = 24;
const MILLISECONDS_PER_SECOND = 1000;

type AuthenticationStatus = "authenticated" | "rejected" | "locked";

interface AuthenticationResult {
  status: AuthenticationStatus;
  sessionToken: string | null;
  failedAttemptCount: number;
  isAccountLocked: boolean;
}

interface UserCredentials {
  emailAddress: string;
  passwordHash: string;
  failedAttemptCount: number;
  lastLoginEpochSeconds: number;
}

function authenticateUser(
  credentials: UserCredentials,
  submittedPassword: string,
): AuthenticationResult {
  const isAccountLocked = credentials.failedAttemptCount >= MAX_LOGIN_ATTEMPTS;

  if (isAccountLocked) {
    return {
      status: "locked",
      sessionToken: null,
      failedAttemptCount: credentials.failedAttemptCount,
      isAccountLocked: true,
    };
  }

  const isPasswordValid = verifyPassword(
    submittedPassword,
    credentials.passwordHash,
  );

  if (!isPasswordValid) {
    const updatedFailedAttemptCount = credentials.failedAttemptCount + 1;
    return {
      status: "rejected",
      sessionToken: null,
      failedAttemptCount: updatedFailedAttemptCount,
      isAccountLocked: updatedFailedAttemptCount >= MAX_LOGIN_ATTEMPTS,
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

function isSessionExpired(lastActivityEpochSeconds: number): boolean {
  const currentEpochSeconds = Math.floor(Date.now() / MILLISECONDS_PER_SECOND);
  const elapsedSeconds = currentEpochSeconds - lastActivityEpochSeconds;
  return elapsedSeconds > SESSION_TIMEOUT_SECONDS;
}

function isPasswordLongEnough(password: string): boolean {
  return password.length >= MINIMUM_PASSWORD_LENGTH;
}

declare function verifyPassword(
  plainPassword: string,
  passwordHash: string,
): boolean;
declare function generateSessionToken(expiryHours: number): string;

export { authenticateUser, isSessionExpired, isPasswordLongEnough };
