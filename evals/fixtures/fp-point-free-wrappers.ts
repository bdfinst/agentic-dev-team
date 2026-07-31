// WARN: Redundant function wrappers and un-composed pipelines

const toUpperCase = (s: string): string => s.toUpperCase();
const exclaim = (s: string): string => `${s}!`;
const trim = (s: string): string => s.trim();

// redundant wrapper: forwards its single argument unchanged, no added logic
const shout = (s: string): string => toUpperCase(s);

const sum = (a: number, b: number): number => a + b;
// redundant wrapper: forwards every argument unchanged, in order
const sumPair = (a: number, b: number): number => sum(a, b);

// three-deep nested pipeline over a single value - candidate for compose/pipe
const cleanTitle = (raw: string): string => exclaim(toUpperCase(trim(raw)));

const digitsOnly = /^\d+$/;
// legitimate: preserves the receiver - `const isNumeric = digitsOnly.test;`
// throws a TypeError (V8: "called on incompatible receiver undefined") at call time
const isNumeric = (s: string): boolean => digitsOnly.test(s);

export { shout, sumPair, cleanTitle, isNumeric };
