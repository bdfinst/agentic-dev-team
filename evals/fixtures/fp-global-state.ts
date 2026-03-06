// FAIL: Global state mutations — window.*, process.env.*, let-instead-of-const, ++ outside loops

declare const window: { localStorage: Storage; location: { href: string } } & Record<string, unknown>;

let appVersion = "1.0.0"; // should be const
let requestCount = 0; // should be const (or use a different pattern)

function trackPageView(page: string): void {
  requestCount++; // mutation: ++ outside a loop
  window.localStorage.setItem("lastPage", page);
}

function setFeatureFlag(name: string, enabled: boolean): void {
  window[`ff_${name}`] = enabled; // mutation: window property assignment
}

function configureEnvironment(env: string): void {
  process.env.NODE_ENV = env; // mutation: process.env assignment
  process.env.APP_VERSION = appVersion; // mutation: process.env assignment
}

function redirectToLogin(): void {
  window.location.href = "/login"; // mutation: window.location assignment
}

function incrementCounter(): number {
  requestCount++; // mutation: ++ outside a loop
  return requestCount;
}

let debugMode = false; // should be const

function enableDebug(): void {
  debugMode = true; // reassignment of let that should be const
  process.env.DEBUG = "true"; // mutation: process.env assignment
}

function registerGlobalHandler(name: string, handler: () => void): void {
  window[name] = handler; // mutation: window property assignment
}

function buildInfo(): string {
  let label = `v${appVersion}`; // should be const
  return label;
}

export {
  appVersion,
  requestCount,
  trackPageView,
  setFeatureFlag,
  configureEnvironment,
  redirectToLogin,
  incrementCounter,
  debugMode,
  enableDebug,
  registerGlobalHandler,
  buildInfo,
};
