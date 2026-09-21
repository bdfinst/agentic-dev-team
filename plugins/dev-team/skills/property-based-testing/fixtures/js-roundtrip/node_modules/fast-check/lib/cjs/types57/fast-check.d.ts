import { RandomGenerator as RandomGenerator$1 } from "pure-rand/types/RandomGenerator";
import { JumpableRandomGenerator } from "pure-rand/types/JumpableRandomGenerator";
//#region src/check/precondition/Pre.d.ts
/**
 * Add pre-condition checks inside a property execution
 * @param expectTruthy - cancel the run whenever this value is falsy
 * @remarks Since 1.3.0
 * @public
 */
export declare function pre(expectTruthy: boolean): asserts expectTruthy;
//#endregion
//#region src/random/generator/RandomGenerator.d.ts
interface RandomGenerator7x {
  clone(): RandomGenerator7x;
  next(): [number, RandomGenerator7x];
  jump?(): RandomGenerator7x;
  unsafeNext(): number;
  unsafeJump?(): void;
  getState(): readonly number[];
}
/**
 * Merged type supporting both pure-rand v7 and v8 random generators.
 * Keeping compatibility with v7 avoids a breaking API change and a new major version.
 * @remarks Since 4.6.0
 * @public
 */
type RandomGenerator = RandomGenerator7x | RandomGenerator$1 | JumpableRandomGenerator;
//#endregion
//#region src/random/generator/Random.d.ts
/**
 * Wrapper around an instance of a `pure-rand`'s random number generator
 * offering a simpler interface to deal with random with impure patterns
 *
 * @public
 */
export declare class Random {
  /**
   * Create a mutable random number generator by cloning the passed one and mutate it
   * @param sourceRng - Immutable random generator from pure-rand library, will not be altered (a clone will be)
   */
  constructor(sourceRng: RandomGenerator);
  /**
   * Clone the random number generator
   */
  clone(): Random;
  /**
   * Generate an integer having `bits` random bits
   * @param bits - Number of bits to generate
   * @deprecated Prefer {@link nextInt} with explicit bounds: `nextInt(0, (1 << bits) - 1)`
   */
  next(bits: number): number;
  /**
   * Generate a random boolean
   * @deprecated Prefer {@link nextInt} with explicit bounds: `nextInt(0, 1) === 1`
   */
  nextBoolean(): boolean;
  /**
   * Generate a random integer (32 bits)
   * @deprecated Prefer {@link nextInt} with explicit bounds: `nextInt(-2147483648, 2147483647)`
   */
  nextInt(): number;
  /**
   * Generate a random integer between min (included) and max (included)
   * @param min - Minimal integer value
   * @param max - Maximal integer value
   */
  nextInt(min: number, max: number): number;
  /**
   * Generate a random bigint between min (included) and max (included)
   * @param min - Minimal bigint value
   * @param max - Maximal bigint value
   */
  nextBigInt(min: bigint, max: bigint): bigint;
  /**
   * Generate a random floating point number between 0.0 (included) and 1.0 (excluded)
   * @deprecated Prefer {@link nextInt} with explicit bounds
   */
  nextDouble(): number;
  /**
   * Extract the internal state of the internal RandomGenerator backing the current instance of Random
   */
  getState(): readonly number[] | undefined;
}
//#endregion
//#region src/stream/Stream.d.ts
/**
 * Wrapper around `IterableIterator` interface
 * offering a set of helpers to deal with iterations in a simple way
 *
 * @remarks Since 0.0.7
 * @public
 */
export declare class Stream<T> implements IterableIterator<T> {
  /** @internal */ private readonly g;
  /**
   * Create an empty stream of T
   * @remarks Since 0.0.1
   */
  static nil<T>(): Stream<T>;
  /**
   * Create a stream of T from a variable number of elements
   *
   * @param elements - Elements used to create the Stream
   * @remarks Since 2.12.0
   */
  static of<T>(...elements: T[]): Stream<T>;
  /**
   * Create a Stream based on `g`
   * @param g - Underlying data of the Stream
   */
  constructor(g: IterableIterator<T>);
  next(): IteratorResult<T>;
  [Symbol.iterator](): IterableIterator<T>;
  /**
   * Map all elements of the Stream using `f`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Mapper function
   * @remarks Since 0.0.1
   */
  map<U>(f: (v: T) => U): Stream<U>;
  /**
   * Flat map all elements of the Stream using `f`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Mapper function
   * @remarks Since 0.0.1
   */
  flatMap<U>(f: (v: T) => IterableIterator<U>): Stream<U>;
  /**
   * Drop elements from the Stream while `f(element) === true`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Drop condition
   * @remarks Since 0.0.1
   */
  dropWhile(f: (v: T) => boolean): Stream<T>;
  /**
   * Drop `n` first elements of the Stream
   *
   * WARNING: It closes the current stream
   *
   * @param n - Number of elements to drop
   * @remarks Since 0.0.1
   */
  drop(n: number): Stream<T>;
  /**
   * Take elements from the Stream while `f(element) === true`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Take condition
   * @remarks Since 0.0.1
   */
  takeWhile(f: (v: T) => boolean): Stream<T>;
  /**
   * Take `n` first elements of the Stream
   *
   * WARNING: It closes the current stream
   *
   * @param n - Number of elements to take
   * @remarks Since 0.0.1
   */
  take(n: number): Stream<T>;
  /**
   * Filter elements of the Stream
   *
   * WARNING: It closes the current stream
   *
   * @param f - Elements to keep
   * @remarks Since 1.23.0
   */
  filter<U extends T>(f: (v: T) => v is U): Stream<U>;
  /**
   * Filter elements of the Stream
   *
   * WARNING: It closes the current stream
   *
   * @param f - Elements to keep
   * @remarks Since 0.0.1
   */
  filter(f: (v: T) => boolean): Stream<T>;
  /**
   * Check whether all elements of the Stream are successful for `f`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Condition to check
   * @remarks Since 0.0.1
   */
  every(f: (v: T) => boolean): boolean;
  /**
   * Check whether one of the elements of the Stream is successful for `f`
   *
   * WARNING: It closes the current stream
   *
   * @param f - Condition to check
   * @remarks Since 0.0.1
   */
  has(f: (v: T) => boolean): [boolean, T | null];
  /**
   * Join `others` Stream to the current Stream
   *
   * WARNING: It closes the current stream and the other ones (as soon as it iterates over them)
   *
   * @param others - Streams to join to the current Stream
   * @remarks Since 0.0.1
   */
  join(...others: IterableIterator<T>[]): Stream<T>;
  /**
   * Take the `nth` element of the Stream of the last (if it does not exist)
   *
   * WARNING: It closes the current stream
   *
   * @param nth - Position of the element to extract
   * @remarks Since 0.0.12
   */
  getNthOrLast(nth: number): T | null;
}
/**
 * Create a Stream based on `g`
 *
 * @param g - Underlying data of the Stream
 *
 * @remarks Since 0.0.7
 * @public
 */
export declare function stream<T>(g: IterableIterator<T>): Stream<T>;
//#endregion
//#region src/check/arbitrary/definition/Value.d.ts
/**
 * A `Value<T, TShrink = T>` holds an internal value of type `T`
 * and its associated context
 *
 * @remarks Since 3.0.0 (previously called `NextValue` in 2.15.0)
 * @public
 */
export declare class Value<T> {
  /**
   * State storing the result of hasCloneMethod
   * If `true` the value will be cloned each time it gets accessed
   * @remarks Since 2.15.0
   */
  readonly hasToBeCloned: boolean;
  /**
   * Safe value of the shrinkable
   * Depending on `hasToBeCloned` it will either be `value_` or a clone of it
   * @remarks Since 2.15.0
   */
  readonly value: T;
  /**
   * Internal value of the shrinkable
   * @remarks Since 2.15.0
   */
  readonly value_: T;
  /**
   * Context for the generated value
   * TODO - Do we want to clone it too?
   * @remarks 2.15.0
   */
  readonly context: unknown;
  /**
   * @param value_ - Internal value of the shrinkable
   * @param context - Context associated to the generated value (useful for shrink)
   * @param customGetValue - Limited to internal usages (to ease migration to next), it will be removed on next major
   */
  constructor(value_: T, context: unknown, customGetValue?: () => T);
}
//#endregion
//#region src/check/arbitrary/definition/Arbitrary.d.ts
/**
 * Abstract class able to generate values on type `T`
 *
 * The values generated by an instance of Arbitrary can be previewed - with {@link sample} - or classified - with {@link statistics}.
 *
 * @remarks Since 0.0.7
 * @public
 */
export declare abstract class Arbitrary<T> {
  /**
   * Generate a value of type `T` along with its context (if any)
   * based on the provided random number generator
   *
   * @param mrng - Random number generator
   * @param biasFactor - If taken into account 1 value over biasFactor must be biased. Either integer value greater or equal to 2 (bias) or undefined (no bias)
   * @returns Random value of type `T` and its context
   *
   * @remarks Since 0.0.1 (return type changed in 3.0.0)
   */
  abstract generate(mrng: Random, biasFactor: number | undefined): Value<T>;
  /**
   * Check if a given value could be pass to `shrink` without providing any context.
   *
   * In general, `canShrinkWithoutContext` is not designed to be called for each `shrink` but rather on very special cases.
   * Its usage must be restricted to `canShrinkWithoutContext` or in the rare* contexts of a `shrink` method being called without
   * any context. In this ill-formed case of `shrink`, `canShrinkWithoutContext` could be used or called if needed.
   *
   * *we fall in that case when fast-check is asked to shrink a value that has been provided manually by the user,
   *  in other words: a value not coming from a call to `generate` or a normal `shrink` with context.
   *
   * @param value - Value to be assessed
   * @returns `true` if and only if the value could have been generated by this instance
   *
   * @remarks Since 3.0.0
   */
  abstract canShrinkWithoutContext(value: unknown): value is T;
  /**
   * Shrink a value of type `T`, may rely on the context previously provided to shrink efficiently
   *
   * Must never be called with possibly invalid values and no context without ensuring that such call is legal
   * by calling `canShrinkWithoutContext` first on the value.
   *
   * @param value - The value to shrink
   * @param context - Its associated context (the one returned by generate) or `undefined` if no context but `canShrinkWithoutContext(value) === true`
   * @returns Stream of shrinks for value based on context (if provided)
   *
   * @remarks Since 3.0.0
   */
  abstract shrink(value: T, context: unknown | undefined): Stream<Value<T>>;
  /**
   * Create another arbitrary by filtering values against `predicate`
   *
   * All the values produced by the resulting arbitrary
   * satisfy `predicate(value) == true`
   *
   * Be aware that using filter may highly impact the time required to generate a valid entry
   *
   * @example
   * ```typescript
   * const integerGenerator: Arbitrary<number> = ...;
   * const evenIntegerGenerator: Arbitrary<number> = integerGenerator.filter(e => e % 2 === 0);
   * // new Arbitrary only keeps even values
   * ```
   *
   * @param refinement - Predicate, to test each produced element. Return true to keep the element, false otherwise
   * @returns New arbitrary filtered using predicate
   *
   * @remarks Since 1.23.0
   */
  filter<U extends T>(refinement: (t: T) => t is U): Arbitrary<U>;
  /**
   * Create another arbitrary by filtering values against `predicate`
   *
   * All the values produced by the resulting arbitrary
   * satisfy `predicate(value) == true`
   *
   * Be aware that using filter may highly impact the time required to generate a valid entry
   *
   * @example
   * ```typescript
   * const integerGenerator: Arbitrary<number> = ...;
   * const evenIntegerGenerator: Arbitrary<number> = integerGenerator.filter(e => e % 2 === 0);
   * // new Arbitrary only keeps even values
   * ```
   *
   * @param predicate - Predicate, to test each produced element. Return true to keep the element, false otherwise
   * @returns New arbitrary filtered using predicate
   *
   * @remarks Since 0.0.1
   */
  filter(predicate: (t: T) => boolean): Arbitrary<T>;
  /**
   * Create another arbitrary by mapping all produced values using the provided `mapper`
   * Values produced by the new arbitrary are the result of applying `mapper` value by value
   *
   * @example
   * ```typescript
   * const rgbChannels: Arbitrary<{r:number,g:number,b:number}> = ...;
   * const color: Arbitrary<string> = rgbChannels.map(ch => `#${(ch.r*65536 + ch.g*256 + ch.b).toString(16).padStart(6, '0')}`);
   * // transform an Arbitrary producing {r,g,b} integers into an Arbitrary of '#rrggbb'
   * ```
   *
   * @param mapper - Map function, to produce a new element based on an old one
   * @param unmapper - Optional unmap function, it will never be used except when shrinking user defined values. Must throw if value is not compatible (since 3.0.0)
   * @returns New arbitrary with mapped elements
   *
   * @remarks Since 0.0.1
   */
  map<U>(mapper: (t: T) => U, unmapper?: (possiblyU: unknown) => T): Arbitrary<U>;
  /**
   * Create another arbitrary by mapping a value from a base Arbirary using the provided `fmapper`
   * Values produced by the new arbitrary are the result of the arbitrary generated by applying `fmapper` to a value
   * @example
   * ```typescript
   * const arrayAndLimitArbitrary = fc.nat().chain((c: number) => fc.tuple( fc.array(fc.nat(c)), fc.constant(c)));
   * ```
   *
   * @param chainer - Chain function, to produce a new Arbitrary using a value from another Arbitrary
   * @returns New arbitrary of new type
   *
   * @remarks Since 1.2.0
   */
  chain<U>(chainer: (t: T) => Arbitrary<U>): Arbitrary<U>;
}
//#endregion
//#region src/check/precondition/PreconditionFailure.d.ts
/**
 * Error type produced whenever a precondition fails
 * @remarks Since 2.2.0
 * @public
 */
export declare class PreconditionFailure extends Error {
  readonly interruptExecution: boolean;
  constructor(interruptExecution?: boolean);
  static isFailure(err: unknown): err is PreconditionFailure;
}
//#endregion
//#region src/check/property/IRawProperty.d.ts
/**
 * Represent failures of the property
 * @remarks Since 3.0.0
 * @public
 */
type PropertyFailure = {
  /**
   * The original error that has been intercepted.
   * Possibly not an instance Error as users can throw anything.
   * @remarks Since 3.0.0
   */
  error: unknown;
};
/**
 * Property
 *
 * A property is the combination of:
 * - Arbitraries: how to generate the inputs for the algorithm
 * - Predicate: how to confirm the algorithm succeeded?
 *
 * @remarks Since 1.19.0
 * @public
 */
interface IRawProperty<Ts, IsAsync extends boolean = boolean> {
  /**
   * Is the property asynchronous?
   *
   * true in case of asynchronous property, false otherwise
   * @remarks Since 0.0.7
   */
  isAsync(): IsAsync;
  /**
   * Generate values of type Ts
   *
   * @param mrng - Random number generator
   * @param runId - Id of the generation, starting at 0 - if set the generation might be biased
   *
   * @remarks Since 0.0.7 (return type changed in 3.0.0)
   */
  generate(mrng: Random, runId?: number): Value<Ts>;
  /**
   * Shrink value of type Ts
   *
   * @param value - The value to be shrunk, it can be context-less
   *
   * @remarks Since 3.0.0
   */
  shrink(value: Value<Ts>): Stream<Value<Ts>>;
  /**
   * Check the predicate for v
   * @param v - Value of which we want to check the predicate
   * @remarks Since 0.0.7
   */
  run(v: Ts): (IsAsync extends true ? Promise<PreconditionFailure | PropertyFailure | null> : never) | (IsAsync extends false ? PreconditionFailure | PropertyFailure | null : never);
  /**
   * Run before each hook
   * @remarks Since 3.4.0
   */
  runBeforeEach: () => (IsAsync extends true ? Promise<void> : never) | (IsAsync extends false ? void : never);
  /**
   * Run after each hook
   * @remarks Since 3.4.0
   */
  runAfterEach: () => (IsAsync extends true ? Promise<void> : never) | (IsAsync extends false ? void : never);
}
//#endregion
//#region src/arbitrary/_internals/helpers/MaxLengthFromMinLength.d.ts
/**
 * The size parameter defines how large the generated values could be.
 *
 * The default in fast-check is 'small' but it could be increased (resp. decreased)
 * to ask arbitraries for larger (resp. smaller) values.
 *
 * @remarks Since 2.22.0
 * @public
 */
type Size = "xsmall" | "small" | "medium" | "large" | "xlarge";
/**
 * @remarks Since 2.22.0
 * @public
 */
type RelativeSize = "-4" | "-3" | "-2" | "-1" | "=" | "+1" | "+2" | "+3" | "+4";
/**
 * Superset of {@link Size} to override the default defined for size
 * @remarks Since 2.22.0
 * @public
 */
type SizeForArbitrary = RelativeSize | Size | "max" | undefined;
/**
 * Superset of {@link Size} to override the default defined for size.
 * It can either be based on a numeric value manually selected by the user (not recommended)
 * or rely on presets based on size (recommended).
 *
 * This size will be used to infer a bias to limit the depth, used as follow within recursive structures:
 * While going deeper, the bias on depth will increase the probability to generate small instances.
 *
 * When used with {@link Size}, the larger the size the deeper the structure.
 * When used with numeric values, the larger the number (floating point number &gt;= 0),
 * the deeper the structure. `+0` means extremelly biased depth meaning barely impossible to generate
 * deep structures, while `Number.POSITIVE_INFINITY` means "depth has no impact".
 *
 * Using `max` or `Number.POSITIVE_INFINITY` is fully equivalent.
 *
 * @remarks Since 2.25.0
 * @public
 */
type DepthSize = RelativeSize | Size | "max" | number | undefined;
//#endregion
//#region src/check/runner/configuration/RandomType.d.ts
/**
 * Random generators automatically recognized by the framework
 * without having to pass a builder function
 * @remarks Since 2.2.0
 * @public
 */
type RandomType = "mersenne" | "congruential" | "congruential32" | "xorshift128plus" | "xoroshiro128plus";
//#endregion
//#region src/check/runner/configuration/VerbosityLevel.d.ts
/**
 * Verbosity level
 * @remarks Since 1.9.1
 * @public
 */
export declare enum VerbosityLevel {
  /**
   * Level 0 (default)
   *
   * Minimal reporting:
   * - minimal failing case
   * - error log corresponding to the minimal failing case
   *
   * @remarks Since 1.9.1
   */
  None = 0,
  /**
   * Level 1
   *
   * Failures reporting:
   * - same as `VerbosityLevel.None`
   * - list all the failures encountered during the shrinking process
   *
   * @remarks Since 1.9.1
   */
  Verbose = 1,
  /**
   * Level 2
   *
   * Execution flow reporting:
   * - same as `VerbosityLevel.None`
   * - all runs with their associated status displayed as a tree
   *
   * @remarks Since 1.9.1
   */
  VeryVerbose = 2
}
//#endregion
//#region src/check/runner/reporter/ExecutionStatus.d.ts
/**
 * Status of the execution of the property
 * @remarks Since 1.9.0
 * @public
 */
export declare enum ExecutionStatus {
  Success = 0,
  Skipped = -1,
  Failure = 1
}
//#endregion
//#region src/check/runner/reporter/ExecutionTree.d.ts
/**
 * Summary of the execution process
 * @remarks Since 1.9.0
 * @public
 */
interface ExecutionTree<Ts> {
  /**
   * Status of the property
   * @remarks Since 1.9.0
   */
  status: ExecutionStatus;
  /**
   * Generated value
   * @remarks Since 1.9.0
   */
  value: Ts;
  /**
   * Values derived from this value
   * @remarks Since 1.9.0
   */
  children: ExecutionTree<Ts>[];
}
//#endregion
//#region src/check/runner/reporter/RunDetails.d.ts
/**
 * Post-run details produced by {@link check}
 *
 * A failing property can easily detected by checking the `failed` flag of this structure
 *
 * @remarks Since 0.0.7
 * @public
 */
type RunDetails<Ts> = RunDetailsFailureProperty<Ts> | RunDetailsFailureTooManySkips<Ts> | RunDetailsFailureInterrupted<Ts> | RunDetailsSuccess<Ts>;
/**
 * Run reported as failed because
 * the property failed
 *
 * Refer to {@link RunDetailsCommon} for more details
 *
 * @remarks Since 1.25.0
 * @public
 */
interface RunDetailsFailureProperty<Ts> extends RunDetailsCommon<Ts> {
  failed: true;
  interrupted: boolean;
  counterexample: Ts;
  counterexamplePath: string;
  errorInstance: unknown;
}
/**
 * Run reported as failed because
 * too many retries have been attempted to generate valid values
 *
 * Refer to {@link RunDetailsCommon} for more details
 *
 * @remarks Since 1.25.0
 * @public
 */
interface RunDetailsFailureTooManySkips<Ts> extends RunDetailsCommon<Ts> {
  failed: true;
  interrupted: false;
  counterexample: null;
  counterexamplePath: null;
  errorInstance: null;
}
/**
 * Run reported as failed because
 * it took too long and thus has been interrupted
 *
 * Refer to {@link RunDetailsCommon} for more details
 *
 * @remarks Since 1.25.0
 * @public
 */
interface RunDetailsFailureInterrupted<Ts> extends RunDetailsCommon<Ts> {
  failed: true;
  interrupted: true;
  counterexample: null;
  counterexamplePath: null;
  errorInstance: null;
}
/**
 * Run reported as success
 *
 * Refer to {@link RunDetailsCommon} for more details
 *
 * @remarks Since 1.25.0
 * @public
 */
interface RunDetailsSuccess<Ts> extends RunDetailsCommon<Ts> {
  failed: false;
  interrupted: boolean;
  counterexample: null;
  counterexamplePath: null;
  errorInstance: null;
}
/**
 * Shared part between variants of RunDetails
 * @remarks Since 2.2.0
 * @public
 */
interface RunDetailsCommon<Ts> {
  /**
   * Does the property failed during the execution of {@link check}?
   * @remarks Since 0.0.7
   */
  failed: boolean;
  /**
   * Was the execution interrupted?
   * @remarks Since 1.19.0
   */
  interrupted: boolean;
  /**
   * Number of runs
   *
   * - In case of failed property: Number of runs up to the first failure (including the failure run)
   * - Otherwise: Number of successful executions
   *
   * @remarks Since 1.0.0
   */
  numRuns: number;
  /**
   * Number of skipped entries due to failed pre-condition
   *
   * As `numRuns` it only takes into account the skipped values that occured before the first failure.
   * Refer to {@link pre} to add such pre-conditions.
   *
   * @remarks Since 1.3.0
   */
  numSkips: number;
  /**
   * Number of shrinks required to get to the minimal failing case (aka counterexample)
   * @remarks Since 1.0.0
   */
  numShrinks: number;
  /**
   * Seed that have been used by the run
   *
   * It can be forced in {@link assert}, {@link check}, {@link sample} and {@link statistics} using `Parameters`
   * @remarks Since 0.0.7
   */
  seed: number;
  /**
   * In case of failure: the counterexample contains the minimal failing case (first failure after shrinking)
   * @remarks Since 0.0.7
   */
  counterexample: Ts | null;
  /**
   * In case of failure: it contains the error that has been thrown if any
   * @remarks Since 3.0.0
   */
  errorInstance: unknown | null;
  /**
   * In case of failure: path to the counterexample
   *
   * For replay purposes, it can be forced in {@link assert}, {@link check}, {@link sample} and {@link statistics} using `Parameters`
   *
   * @remarks Since 1.0.0
   */
  counterexamplePath: string | null;
  /**
   * List all failures that have occurred during the run
   *
   * You must enable verbose with at least `Verbosity.Verbose` in `Parameters`
   * in order to have values in it
   *
   * @remarks Since 1.1.0
   */
  failures: Ts[];
  /**
   * Execution summary of the run
   *
   * Traces the origin of each value encountered during the test and its execution status.
   * Can help to diagnose shrinking issues.
   *
   * You must enable verbose with at least `Verbosity.Verbose` in `Parameters`
   * in order to have values in it:
   * - Verbose: Only failures
   * - VeryVerbose: Failures, Successes and Skipped
   *
   * @remarks Since 1.9.0
   */
  executionSummary: ExecutionTree<Ts>[];
  /**
   * Verbosity level required by the user
   * @remarks Since 1.9.0
   */
  verbose: VerbosityLevel;
  /**
   * Configuration of the run
   *
   * It includes both local parameters set on {@link check} or {@link assert}
   * and global ones specified using {@link configureGlobal}
   *
   * @remarks Since 1.25.0
   */
  runConfiguration: Parameters<Ts>;
}
//#endregion
//#region src/check/plugin/Plugin.d.ts
/**
 * Storage shared by all the plugins instantiated for one call to {@link check} or {@link assert}.
 * Use it to cooperate across plugins.
 *
 * @remarks Since 4.10.0
 * @public
 */
type PluginStore = {
  /**
   * Read the value registered for `key`, if any.
   * WARNING: `T` is declared by the caller, never checked by the store.
   * @remarks Since 4.10.0
   */
  get: <T>(key: symbol) => T | undefined;
  /**
   * Register `value` for `key`, replacing any previous value.
   * @remarks Since 4.10.0
   */
  set: <T>(key: symbol, value: T) => void;
};
/**
 * Runtime part of a plugin.
 *
 * The runtime part is made of the hooks called by the runner.
 * Hooks will be called when relevant for the runner.
 *
 * All the hooks are optional.
 *
 * @remarks Since 4.10.0
 * @public
 */
type PluginInstance<Ts> = {
  /**
   * Surcharge the original `generate` coming with the property with extra capabilities.
   *
   * @remarks Since 4.10.0
   */
  decorateGenerate?: (nestedGenerate: IRawProperty<Ts, boolean>["generate"]) => IRawProperty<Ts, boolean>["generate"];
  /**
   * Enrich the execution of the predicate linked to the property with extra behaviors.
   * Called once per execution of the predicate.
   *
   * WARNING: `nestedRun` never throws and neither should the function returned by `decorateRun`.
   * WARNING: If run returns synchronously, the decorated function must too.
   *
   * @remarks Since 4.10.0
   */
  decorateRun?: (nestedRun: IRawProperty<Ts, boolean>["run"]) => IRawProperty<Ts, boolean>["run"];
  /**
   * Called once at the end of the full property assessment, with the result of the execution.
   *
   * Throwing allows you to override the default error reporting provided by {@link assert}.
   *
   * Every `onAllRunsComplete` is guaranteed to run, even if another `onAllRunsComplete` threw.
   * In case several of them throw, only the first failure is reported, the others will be swallowed.
   *
   * WARNING: Always return synchronously for synchronous properties.
   *
   * @remarks Since 4.10.0
   */
  onAllRunsComplete?: (runDetails: RunDetails<Ts>) => Promise<void> | void;
  /**
   * Called once at the end of the full property assessment, after all other methods of the plugin.
   * Use it to clean up and release resources acquired by the plugin.
   *
   * Every `afterAll` is guaranteed to run, even if an `onAllRunsComplete` or another `afterAll` threw.
   * In case several `onAllRunsComplete` or `afterAll` throw, only the first failure is reported, the others will be swallowed.
   *
   * WARNING: Always return synchronously for synchronous properties.
   *
   * @remarks Since 4.10.0
   */
  afterAll?: () => Promise<void> | void;
};
/**
 * Builder instantiating a plugin.
 * Each property will instantiate its own plugin when starting to be assessed via {@link check} or {@link assert}.
 *
 * Parameters received by the Plugin function:
 * - 1st argument or pluginIndex: Corresponds to the index of the plugin within the run (starts at zero).
 *   Plugins are instantiated in order. As such, for a given batch expect to see index 0 instantiated first, followed by others.
 * - 2nd argument or pluginStore: Context parameter shared across all builders.
 *   The store can be leveraged to exchange insights with other builders.
 *
 * @remarks Since 4.10.0
 * @public
 */
type Plugin<Ts> = (pluginIndex: number, pluginStore: PluginStore) => PluginInstance<Ts>;
//#endregion
//#region src/check/runner/configuration/Parameters.d.ts
/**
 * Customization of the parameters used to run the properties
 * @remarks Since 0.0.6
 * @public
 */
interface Parameters<T = void> {
  /**
   * Initial seed of the generator: `Date.now()` by default
   *
   * It can be forced to replay a failed run.
   *
   * In theory, seeds are supposed to be 32-bit integers.
   * In case of double value, the seed will be rescaled into a valid 32-bit integer (eg.: values between 0 and 1 will be evenly spread into the range of possible seeds).
   *
   * @remarks Since 0.0.6
   */
  seed?: number;
  /**
   * Random number generator: `xorshift128plus` by default
   *
   * Random generator is the core element behind the generation of random values - changing it might directly impact the quality and performances of the generation of random values.
   * It can be one of: 'mersenne', 'congruential', 'congruential32', 'xorshift128plus', 'xoroshiro128plus'
   * Or any function able to build a `RandomGenerator` based on a seed
   *
   * As required since pure-rand v6.0.0, when passing a builder for {@link RandomGenerator},
   * the random number generator must generate values between -0x80000000 and 0x7fffffff.
   *
   * @remarks Since 1.6.0
   */
  randomType?: RandomType | ((seed: number) => RandomGenerator);
  /**
   * Number of runs before success: 100 by default
   * @remarks Since 1.0.0
   */
  numRuns?: number;
  /**
   * Maximal number of skipped values per run
   *
   * Skipped is considered globally, so this value is used to compute maxSkips = maxSkipsPerRun * numRuns.
   * Runner will consider a run to have failed if it skipped maxSkips+1 times before having generated numRuns valid entries.
   *
   * See {@link pre} for more details on pre-conditions
   *
   * @remarks Since 1.3.0
   */
  maxSkipsPerRun?: number;
  /**
   * Maximum time in milliseconds for the predicate to answer: disabled by default
   *
   * WARNING: Only works for async code (see {@link asyncProperty}), will not interrupt a synchronous code.
   * @remarks Since 0.0.11
   * @deprecated Prefer the `timeout` plugin: `fc.assert(property, { plugins: [fc.timeout(timeMs)] })`
   */
  timeout?: number;
  /**
   * Skip all runs after a given time limit: disabled by default
   *
   * NOTE: Relies on `Date.now()`.
   *
   * NOTE:
   * Useful to stop too long shrinking processes.
   * Replay capability (see `seed`, `path`) can resume the shrinking.
   *
   * WARNING:
   * It skips runs. Thus test might be marked as failed.
   * Indeed, it might not reached the requested number of successful runs.
   *
   * @remarks Since 1.15.0
   */
  skipAllAfterTimeLimit?: number;
  /**
   * Interrupt test execution after a given time limit: disabled by default
   *
   * NOTE: Relies on `Date.now()`.
   *
   * NOTE:
   * Useful to avoid having too long running processes in your CI.
   * Replay capability (see `seed`, `path`) can still be used if needed.
   *
   * WARNING:
   * If the test got interrupted before any failure occured
   * and before it reached the requested number of runs specified by `numRuns`
   * it will be marked as success. Except if `markInterruptAsFailure` has been set to `true`
   *
   * @remarks Since 1.19.0
   * @deprecated Prefer the `interruptAfterTimeLimit` plugin: `fc.assert(property, { plugins: [fc.interruptAfterTimeLimit(timeMs)] })`
   */
  interruptAfterTimeLimit?: number;
  /**
   * Mark interrupted runs as failed runs if preceded by one success or more: disabled by default
   * Interrupted with no success at all always defaults to failure whatever the value of this flag.
   * @remarks Since 1.19.0
   * @deprecated Prefer the `failOnInterrupt` option of the `interruptAfterTimeLimit` plugin: `fc.interruptAfterTimeLimit(timeMs, { failOnInterrupt: true })`
   */
  markInterruptAsFailure?: boolean;
  /**
   * Skip runs corresponding to already tried values.
   *
   * WARNING:
   * Discarded runs will be retried. Under the hood they are simple calls to `fc.pre`.
   * In other words, if you ask for 100 runs but your generator can only generate 10 values then the property will fail as 100 runs will never be reached.
   * Contrary to `ignoreEqualValues` you always have the number of runs you requested.
   *
   * NOTE: Relies on `fc.stringify` to check the equality.
   *
   * @remarks Since 2.14.0
   * @deprecated Prefer the `skipEqualValues` plugin: `fc.assert(property, { plugins: [fc.skipEqualValues()] })`
   */
  skipEqualValues?: boolean;
  /**
   * Discard runs corresponding to already tried values.
   *
   * WARNING:
   * Discarded runs will not be replaced.
   * In other words, if you ask for 100 runs and have 2 discarded runs you will only have 98 effective runs.
   *
   * NOTE: Relies on `fc.stringify` to check the equality.
   *
   * @remarks Since 2.14.0
   * @deprecated Prefer the `ignoreEqualValues` plugin: `fc.assert(property, { plugins: [fc.ignoreEqualValues()] })`
   */
  ignoreEqualValues?: boolean;
  /**
   * Way to replay a failing property directly with the counterexample.
   * It can be fed with the counterexamplePath returned by the failing test (requires `seed` too).
   * @remarks Since 1.0.0
   */
  path?: string;
  /**
   * Logger (see {@link statistics}): `console.log` by default
   * @remarks Since 0.0.6
   */
  logger?(v: string): void;
  /**
   * Force the use of unbiased arbitraries: biased by default
   * @remarks Since 1.1.0
   * @deprecated Prefer the `unbiased` plugin: `fc.assert(property, { plugins: [fc.unbiased()] })`
   */
  unbiased?: boolean;
  /**
   * Enable verbose mode: {@link VerbosityLevel.None} by default
   *
   * Using `verbose: true` is equivalent to `verbose: VerbosityLevel.Verbose`
   *
   * It can prove very useful to troubleshoot issues.
   * See {@link VerbosityLevel} for more details on each level.
   *
   * @remarks Since 1.1.0
   */
  verbose?: boolean | VerbosityLevel;
  /**
   * Custom values added at the beginning of generated ones
   *
   * It enables users to come with examples they want to test at every run
   *
   * @remarks Since 1.4.0
   */
  examples?: T[];
  /**
   * Stop run on failure
   *
   * It makes the run stop at the first encountered failure without shrinking.
   *
   * When used in complement to `seed` and `path`,
   * it replays only the minimal counterexample.
   *
   * @remarks Since 1.11.0
   */
  endOnFailure?: boolean;
  /**
   * Replace the default reporter handling errors by a custom one
   *
   * Reporter is responsible to throw in case of failure: default one throws whenever `runDetails.failed` is true.
   * But you may want to change this behaviour in yours.
   *
   * Only used when calling {@link assert}
   * Cannot be defined in conjonction with `asyncReporter`
   *
   * @example
   * ```typescript
   * // Prefer a plugin relying on the `onAllRunsComplete` hook.
   * const reporterPlugin: fc.Plugin<unknown> = () => ({
   *   onAllRunsComplete: (runDetails) => {
   *     if (runDetails.failed) {
   *       throw new Error(fc.defaultReportMessage(runDetails));
   *     }
   *   },
   * });
   * fc.assert(property, { plugins: [reporterPlugin] });
   * ```
   *
   * @remarks Since 1.25.0
   * @deprecated Prefer a plugin relying on the `onAllRunsComplete` hook: `fc.assert(property, { plugins: [reporterPlugin] })`
   */
  reporter?: (runDetails: RunDetails<T>) => void;
  /**
   * Replace the default reporter handling errors by a custom one
   *
   * Reporter is responsible to throw in case of failure: default one throws whenever `runDetails.failed` is true.
   * But you may want to change this behaviour in yours.
   *
   * Only used when calling {@link assert}
   * Cannot be defined in conjonction with `reporter`
   * Not compatible with synchronous properties: runner will throw
   *
   * @example
   * ```typescript
   * // Prefer a plugin relying on the `onAllRunsComplete` hook.
   * const reporterPlugin: fc.Plugin<unknown> = () => ({
   *   onAllRunsComplete: async (runDetails) => {
   *     if (runDetails.failed) {
   *       throw new Error(fc.asyncDefaultReportMessage(runDetails));
   *     }
   *   },
   * });
   * await fc.assert(asyncProperty, { plugins: [reporterPlugin] });
   * ```
   *
   * @remarks Since 1.25.0
   * @deprecated Prefer a plugin relying on an asynchronous `onAllRunsComplete` hook: `fc.assert(asyncProperty, { plugins: [reporterPlugin] })`
   */
  asyncReporter?: (runDetails: RunDetails<T>) => Promise<void>;
  /**
   * By default the Error causing the failure of the predicate will not be directly exposed within the message
   * of the Error thown by fast-check. It will be exposed by a cause field attached to the Error.
   *
   * The Error with cause has been supported by Node since 16.14.0 and is properly supported in many test runners.
   *
   * But if the original Error fails to appear within your test runner,
   * Or if you prefer the Error to be included directly as part of the message of the resulted Error,
   * you can toggle this flag and the Error produced by fast-check in case of failure will expose the source Error
   * as part of the message and not as a cause.
   */
  includeErrorInReport?: boolean;
  /**
   * Set of plugins extending the way the property gets executed by the runner
   *
   * Each plugin is instantiated once per run.
   * They can be leveraged to control and enrich the execution flow of each predicate.
   *
   * They come after the plugins installed globally via {@link installGlobalPlugin}.
   * At execution time, the first plugin of the resulting array is entered first while the last one is the closest to the predicate.
   * Plugins are instantiated in order.
   *
   * @remarks Since 4.10.0
   */
  plugins?: Plugin<T>[];
}
//#endregion
//#region src/check/runner/configuration/GlobalParameters.d.ts
/**
 * Type of legal hook function that can be used in the global parameter `beforeEach` and/or `afterEach`
 * Prefer `beforeEach` and/or `afterEach` plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
 * @remarks Since 2.3.0
 * @public
 */
type GlobalPropertyHookFunction = () => void;
/**
 * Type of legal hook function that can be used in the global parameter `asyncBeforeEach` and/or `asyncAfterEach`
 * Prefer `beforeEach` and/or `afterEach` plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
 * @remarks Since 2.3.0
 * @public
 */
type GlobalAsyncPropertyHookFunction = (() => Promise<unknown>) | (() => void);
/**
 * Type describing the global overrides
 * @remarks Since 1.18.0
 * @public
 */
type GlobalParameters = Pick<Parameters<unknown>, Exclude<keyof Parameters<unknown>, "path" | "examples" | "plugins">> & {
  /**
   * Specify a function that will be called before each execution of a property.
   * It behaves as-if you manually called `beforeEach` method on all the properties you execute with fast-check.
   *
   * The function will be used for both {@link fast-check#property} and {@link fast-check#asyncProperty}.
   * This global override should never be used in conjunction with `asyncBeforeEach`.
   *
   * @deprecated Prefer the life-cycle plugins: `fc.installGlobalPlugin(fc.beforeEach(fn))`
   * @remarks Since 2.3.0
   */
  beforeEach?: GlobalPropertyHookFunction;
  /**
   * Specify a function that will be called after each execution of a property.
   * It behaves as-if you manually called `afterEach` method on all the properties you execute with fast-check.
   *
   * The function will be used for both {@link fast-check#property} and {@link fast-check#asyncProperty}.
   * This global override should never be used in conjunction with `asyncAfterEach`.
   *
   * @deprecated Prefer the life-cycle plugins: `fc.installGlobalPlugin(fc.afterEach(fn))`
   * @remarks Since 2.3.0
   */
  afterEach?: GlobalPropertyHookFunction;
  /**
   * Specify a function that will be called before each execution of an asynchronous property.
   * It behaves as-if you manually called `beforeEach` method on all the asynchronous properties you execute with fast-check.
   *
   * The function will be used only for {@link fast-check#asyncProperty}. It makes synchronous properties created by {@link fast-check#property} unable to run.
   * This global override should never be used in conjunction with `beforeEach`.
   *
   * @deprecated Prefer the life-cycle plugins: `fc.installGlobalPlugin(fc.beforeEach(fn))`
   * @remarks Since 2.3.0
   */
  asyncBeforeEach?: GlobalAsyncPropertyHookFunction;
  /**
   * Specify a function that will be called after each execution of an asynchronous property.
   * It behaves as-if you manually called `afterEach` method on all the asynchronous properties you execute with fast-check.
   *
   * The function will be used only for {@link fast-check#asyncProperty}. It makes synchronous properties created by {@link fast-check#property} unable to run.
   * This global override should never be used in conjunction with `afterEach`.
   *
   * @deprecated Prefer the life-cycle plugins: `fc.installGlobalPlugin(fc.afterEach(fn))`
   * @remarks Since 2.3.0
   */
  asyncAfterEach?: GlobalAsyncPropertyHookFunction;
  /**
   * Define the base size to be used by arbitraries.
   *
   * By default arbitraries not specifying any size will default to it (except in some cases when used defaultSizeToMaxWhenMaxSpecified is true).
   * For some arbitraries users will want to override the default and either define another size relative to this one,
   * or a fixed one.
   *
   * @defaultValue `"small"`
   * @remarks Since 2.22.0
   */
  baseSize?: Size;
  /**
   * When set to `true` and if the size has not been defined for this precise instance,
   * it will automatically default to `"max"` if the user specified a upper bound for the range
   * (applies to length and to depth).
   *
   * When `false`, the size will be defaulted to `baseSize` even if the user specified
   * a upper bound for the range.
   *
   * @remarks Since 2.22.0
   */
  defaultSizeToMaxWhenMaxSpecified?: boolean;
};
/**
 * Define global parameters that will be used by all the runners
 *
 * @example
 * ```typescript
 * fc.configureGlobal({ numRuns: 10 });
 * //...
 * fc.assert(
 *   fc.property(
 *     fc.nat(), fc.nat(),
 *     (a, b) => a + b === b + a
 *   ), { seed: 42 }
 * ) // equivalent to { numRuns: 10, seed: 42 }
 * ```
 *
 * @param parameters - Global parameters
 *
 * @remarks Since 1.18.0
 * @public
 */
export declare function configureGlobal(parameters: GlobalParameters): void;
/**
 * Read global parameters that will be used by runners
 * @remarks Since 1.18.0
 * @public
 */
export declare function readConfigureGlobal(): GlobalParameters;
/**
 * Reset global parameters
 * @remarks Since 1.18.0
 * @public
 */
export declare function resetConfigureGlobal(): void;
//#endregion
//#region src/check/property/AsyncProperty.generic.d.ts
/**
 * Type of legal hook function that can be used to call `beforeEach` or `afterEach`
 * on a {@link IAsyncPropertyWithHooks}
 *
 * @deprecated Prefer `beforeEach` and/or `afterEach` plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
 * @remarks Since 2.2.0
 * @public
 */
type AsyncPropertyHookFunction = ((previousHookFunction: GlobalAsyncPropertyHookFunction) => Promise<unknown>) | ((previousHookFunction: GlobalAsyncPropertyHookFunction) => void);
/**
 * Interface for asynchronous property, see {@link IRawProperty}
 * @remarks Since 1.19.0
 * @public
 */
interface IAsyncProperty<Ts> extends IRawProperty<Ts, true> {}
/**
 * Interface for asynchronous property defining hooks, see {@link IAsyncProperty}
 * @remarks Since 2.2.0
 * @public
 */
interface IAsyncPropertyWithHooks<Ts> extends IAsyncProperty<Ts> {
  /**
   * Define a function that should be called before all calls to the predicate
   * @param hookFunction - Function to be called
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
   * @remarks Since 1.6.0
   */
  beforeEach(hookFunction: AsyncPropertyHookFunction): IAsyncPropertyWithHooks<Ts>;
  /**
   * Define a function that should be called after all calls to the predicate
   * @param hookFunction - Function to be called
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.afterEach(fn)] })`
   * @remarks Since 1.6.0
   */
  afterEach(hookFunction: AsyncPropertyHookFunction): IAsyncPropertyWithHooks<Ts>;
}
//#endregion
//#region src/check/property/AsyncProperty.d.ts
/**
 * Instantiate a new {@link fast-check#IAsyncProperty}
 * @param predicate - Assess the success of the property. Would be considered falsy if it throws or if its output evaluates to false
 * @remarks Since 0.0.7
 * @public
 */
declare function asyncProperty<Ts extends [unknown, ...unknown[]]>(...args: [...arbitraries: { [K in keyof Ts]: Arbitrary<Ts[K]>; }, predicate: (...args: Ts) => Promise<boolean | void>]): IAsyncPropertyWithHooks<Ts>;
//#endregion
//#region src/check/property/Property.generic.d.ts
/**
 * Type of legal hook function that can be used to call `beforeEach` or `afterEach`
 * on a {@link IPropertyWithHooks}
 *
 * @deprecated Prefer `beforeEach` and/or `afterEach` plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
 * @remarks Since 2.2.0
 * @public
 */
type PropertyHookFunction = (globalHookFunction: GlobalPropertyHookFunction) => void;
/**
 * Interface for synchronous property, see {@link IRawProperty}
 * @remarks Since 1.19.0
 * @public
 */
interface IProperty<Ts> extends IRawProperty<Ts, false> {}
/**
 * Interface for synchronous property defining hooks, see {@link IProperty}
 * @remarks Since 2.2.0
 * @public
 */
interface IPropertyWithHooks<Ts> extends IProperty<Ts> {
  /**
   * Define a function that should be called before all calls to the predicate
   * @param invalidHookFunction - Function to be called, please provide a valid hook function
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
   * @remarks Since 1.6.0
   */
  beforeEach(invalidHookFunction: (hookFunction: GlobalPropertyHookFunction) => Promise<unknown>): "beforeEach expects a synchronous function but was given a function returning a Promise";
  /**
   * Define a function that should be called before all calls to the predicate
   * @param hookFunction - Function to be called
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
   * @remarks Since 1.6.0
   */
  beforeEach(hookFunction: PropertyHookFunction): IPropertyWithHooks<Ts>;
  /**
   * Define a function that should be called after all calls to the predicate
   * @param invalidHookFunction - Function to be called, please provide a valid hook function
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.afterEach(fn)] })`
   * @remarks Since 1.6.0
   */
  afterEach(invalidHookFunction: (hookFunction: GlobalPropertyHookFunction) => Promise<unknown>): "afterEach expects a synchronous function but was given a function returning a Promise";
  /**
   * Define a function that should be called after all calls to the predicate
   * @param hookFunction - Function to be called
   * @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.afterEach(fn)] })`
   * @remarks Since 1.6.0
   */
  afterEach(hookFunction: PropertyHookFunction): IPropertyWithHooks<Ts>;
}
//#endregion
//#region src/check/property/Property.d.ts
/**
 * Instantiate a new {@link fast-check#IProperty}
 * @param predicate - Assess the success of the property. Would be considered falsy if it throws or if its output evaluates to false
 * @remarks Since 0.0.1
 * @public
 */
declare function property<Ts extends [unknown, ...unknown[]]>(...args: [...arbitraries: { [K in keyof Ts]: Arbitrary<Ts[K]>; }, predicate: (...args: Ts) => boolean | void]): IPropertyWithHooks<Ts>;
//#endregion
//#region src/check/runner/Runner.d.ts
/**
 * Run the property, do not throw contrary to {@link assert}
 *
 * WARNING: Has to be awaited
 *
 * @param property - Asynchronous property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @returns Test status and other useful details
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function check<Ts>(property: IAsyncProperty<Ts>, params?: Parameters<Ts>): Promise<RunDetails<Ts>>;
/**
 * Run the property, do not throw contrary to {@link assert}
 *
 * @param property - Synchronous property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @returns Test status and other useful details
 *
 * @remarks Since 0.0.1
 * @public
 */
declare function check<Ts>(property: IProperty<Ts>, params?: Parameters<Ts>): RunDetails<Ts>;
/**
 * Run the property, do not throw contrary to {@link assert}
 *
 * WARNING: Has to be awaited if the property is asynchronous
 *
 * @param property - Property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @returns Test status and other useful details
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function check<Ts>(property: IRawProperty<Ts>, params?: Parameters<Ts>): Promise<RunDetails<Ts>> | RunDetails<Ts>;
/**
 * Run the property, throw in case of failure
 *
 * It can be called directly from describe/it blocks of Mocha.
 * No meaningful results are produced in case of success.
 *
 * WARNING: Has to be awaited
 *
 * @param property - Asynchronous property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function assert<Ts>(property: IAsyncProperty<Ts>, params?: Parameters<Ts>): Promise<void>;
/**
 * Run the property, throw in case of failure
 *
 * It can be called directly from describe/it blocks of Mocha.
 * No meaningful results are produced in case of success.
 *
 * @param property - Synchronous property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @remarks Since 0.0.1
 * @public
 */
declare function assert<Ts>(property: IProperty<Ts>, params?: Parameters<Ts>): void;
/**
 * Run the property, throw in case of failure
 *
 * It can be called directly from describe/it blocks of Mocha.
 * No meaningful results are produced in case of success.
 *
 * WARNING: Returns a promise to be awaited if the property is asynchronous
 *
 * @param property - Synchronous or asynchronous property to be checked
 * @param params - Optional parameters to customize the execution
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function assert<Ts>(property: IRawProperty<Ts>, params?: Parameters<Ts>): Promise<void> | void;
//#endregion
//#region src/check/runner/Sampler.d.ts
/**
 * Generate an array containing all the values that would have been generated during {@link assert} or {@link check}
 *
 * @example
 * ```typescript
 * fc.sample(fc.nat(), 10); // extract 10 values from fc.nat() Arbitrary
 * fc.sample(fc.nat(), {seed: 42}); // extract values from fc.nat() as if we were running fc.assert with seed=42
 * ```
 *
 * @param generator - {@link IProperty} or {@link Arbitrary} to extract the values from
 * @param params - Integer representing the number of values to generate or `Parameters` as in {@link assert}
 *
 * @remarks Since 0.0.6
 * @public
 */
declare function sample<Ts>(generator: IRawProperty<Ts> | Arbitrary<Ts>, params?: Parameters<Ts> | number): Ts[];
/**
 * Gather useful statistics concerning generated values
 *
 * Print the result in `console.log` or `params.logger` (if defined)
 *
 * @example
 * ```typescript
 * fc.statistics(
 *     fc.nat(999),
 *     v => v < 100 ? 'Less than 100' : 'More or equal to 100',
 *     {numRuns: 1000, logger: console.log});
 * // Classify 1000 values generated by fc.nat(999) into two categories:
 * // - Less than 100
 * // - More or equal to 100
 * // The output will be sent line by line to the logger
 * ```
 *
 * @param generator - {@link IProperty} or {@link Arbitrary} to extract the values from
 * @param classify - Classifier function that can classify the generated value in zero, one or more categories (with free labels)
 * @param params - Integer representing the number of values to generate or `Parameters` as in {@link assert}
 *
 * @remarks Since 0.0.6
 * @public
 */
declare function statistics<Ts>(generator: IRawProperty<Ts> | Arbitrary<Ts>, classify: (v: Ts) => string | string[], params?: Parameters<Ts> | number): void;
//#endregion
//#region src/arbitrary/_internals/builders/GeneratorValueBuilder.d.ts
/**
 * Take an arbitrary builder and all its arguments separatly.
 * Generate a value out of it.
 *
 * @remarks Since 3.8.0
 * @public
 */
type GeneratorValueFunction = <T, TArgs extends unknown[]>(arb: (...params: TArgs) => Arbitrary<T>, ...args: TArgs) => T;
/**
 * The values part is mostly exposed for the purpose of the tests.
 * Or if you want to have a custom error formatter for this kind of values.
 *
 * @remarks Since 3.8.0
 * @public
 */
type GeneratorValueMethods = {
  values: () => unknown[];
};
/**
 * An instance of {@link GeneratorValue} can be leveraged within predicates themselves to produce extra random values
 * while preserving part of the shrinking capabilities on the produced values.
 *
 * It can be seen as a way to start property based testing within something looking closer from what users will
 * think about when thinking about random in tests. But contrary to raw random, it comes with many useful strengths
 * such as: ability to re-run the test (seeded), shrinking...
 *
 * @remarks Since 3.8.0
 * @public
 */
type GeneratorValue = GeneratorValueFunction & GeneratorValueMethods;
//#endregion
//#region src/arbitrary/gen.d.ts
/**
 * Generate values within the test execution itself by leveraging the strength of `gen`
 *
 * @example
 * ```javascript
 * fc.assert(
 *   fc.property(fc.gen(), gen => {
 *     const size = gen(fc.nat, {max: 10});
 *     const array = [];
 *     for (let index = 0 ; index !== size ; ++index) {
 *       array.push(gen(fc.integer));
 *     }
 *     // Here is an array!
 *     // Note: Prefer fc.array(fc.integer(), {maxLength: 10}) if you want to produce such array
 *   })
 * )
 * ```
 *
 * ⚠️ WARNING:
 * While `gen` is easy to use, it may not shrink as well as tailored arbitraries based on `filter` or `map`.
 *
 * ⚠️ WARNING:
 * Additionally it cannot run back the test properly when attempting to replay based on a seed and a path.
 * You'll need to limit yourself to the seed and drop the path from the options if you attempt to replay something
 * implying it.  More precisely, you may keep the very first part of the path but have to drop anything after the
 * first ":".
 *
 * ⚠️ WARNING:
 * It also does not support custom examples.
 *
 * @remarks Since 3.8.0
 * @public
 */
export declare function gen(): Arbitrary<GeneratorValue>;
//#endregion
//#region src/arbitrary/_internals/helpers/DepthContext.d.ts
/**
 * Type used to strongly type instances of depth identifier while keeping internals
 * what they contain internally
 *
 * @remarks Since 2.25.0
 * @public
 */
type DepthIdentifier = {} & DepthContext;
/**
 * Instance of depth, can be used to alter the depth perceived by an arbitrary
 * or to bias your own arbitraries based on the current depth
 *
 * @remarks Since 2.25.0
 * @public
 */
type DepthContext = {
  /**
   * Current depth (starts at 0, continues with 1, 2...).
   * Only made of integer values superior or equal to 0.
   *
   * Remark: Whenever altering the `depth` during a `generate`, please make sure to ALWAYS
   * reset it to its original value before you leave the `generate`. Otherwise the execution
   * will imply side-effects that will potentially impact the following runs and make replay
   * of the issue barely impossible.
   */
  depth: number;
};
/**
 * Get back the requested DepthContext
 * @remarks Since 2.25.0
 * @public
 */
export declare function getDepthContextFor(contextMeta: DepthContext | DepthIdentifier | string | undefined): DepthContext;
/**
 * Create a new and unique instance of DepthIdentifier
 * that can be shared across multiple arbitraries if needed
 * @public
 */
export declare function createDepthIdentifier(): DepthIdentifier;
//#endregion
//#region src/arbitrary/array.d.ts
/**
 * Constraints to be applied on {@link array}
 * @remarks Since 2.4.0
 * @public
 */
interface ArrayConstraints {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 2.4.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.4.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   *
   * When used in conjonction with `maxLength`, `size` will be used to define
   * the upper bound of the generated array size while `maxLength` will be used
   * to define and document the general maximal length allowed for this case.
   *
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
  /**
   * When receiving a depth identifier, the arbitrary will impact the depth
   * attached to it to avoid going too deep if it already generated lots of items.
   *
   * In other words, if the number of generated values within the collection is large
   * then the generated items will tend to be less deep to avoid creating structures a lot
   * larger than expected.
   *
   * For the moment, the depth is not taken into account to compute the number of items to
   * define for a precise generate call of the array. Just applied onto eligible items.
   *
   * @remarks Since 2.25.0
   */
  depthIdentifier?: DepthIdentifier | string;
}
/**
 * For arrays of values coming from `arb`
 *
 * @param arb - Arbitrary used to generate the values inside the array
 * @param constraints - Constraints to apply when building instances (since 2.4.0)
 *
 * @remarks Since 0.0.1
 * @public
 */
declare function array<T>(arb: Arbitrary<T>, constraints?: ArrayConstraints): Arbitrary<T[]>;
//#endregion
//#region src/arbitrary/bigInt.d.ts
/**
 * Constraints to be applied on {@link bigInt}
 * @remarks Since 2.6.0
 * @public
 */
interface BigIntConstraints {
  /**
   * Lower bound for the generated bigints (eg.: -5n, 0n, BigInt(Number.MIN_SAFE_INTEGER))
   * @remarks Since 2.6.0
   */
  min?: bigint;
  /**
   * Upper bound for the generated bigints (eg.: -2n, 2147483647n, BigInt(Number.MAX_SAFE_INTEGER))
   * @remarks Since 2.6.0
   */
  max?: bigint;
}
/**
 * For bigint
 * @remarks Since 1.9.0
 * @public
 */
declare function bigInt(): Arbitrary<bigint>;
/**
 * For bigint between min (included) and max (included)
 *
 * @param min - Lower bound for the generated bigints (eg.: -5n, 0n, BigInt(Number.MIN_SAFE_INTEGER))
 * @param max - Upper bound for the generated bigints (eg.: -2n, 2147483647n, BigInt(Number.MAX_SAFE_INTEGER))
 *
 * @remarks Since 1.9.0
 * @public
 */
declare function bigInt(min: bigint, max: bigint): Arbitrary<bigint>;
/**
 * For bigint between min (included) and max (included)
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.6.0
 * @public
 */
declare function bigInt(constraints: BigIntConstraints): Arbitrary<bigint>;
/**
 * For bigint between min (included) and max (included)
 *
 * @param args - Either min/max bounds as an object or constraints to apply when building instances
 *
 * @remarks Since 2.6.0
 * @public
 */
declare function bigInt(...args: [] | [bigint, bigint] | [BigIntConstraints]): Arbitrary<bigint>;
//#endregion
//#region src/arbitrary/boolean.d.ts
/**
 * For boolean values - `true` or `false`
 * @remarks Since 0.0.6
 * @public
 */
declare function boolean(): Arbitrary<boolean>;
//#endregion
//#region src/arbitrary/falsy.d.ts
/**
 * Constraints to be applied on {@link falsy}
 * @remarks Since 1.26.0
 * @public
 */
interface FalsyContraints {
  /**
   * Enable falsy bigint value
   * @remarks Since 1.26.0
   */
  withBigInt?: boolean;
}
/**
 * Typing for values generated by {@link falsy}
 * @remarks Since 2.2.0
 * @public
 */
type FalsyValue<TConstraints extends FalsyContraints = object> = false | null | 0 | "" | typeof NaN | undefined | (TConstraints extends {
  withBigInt: true;
} ? 0n : never);
/**
 * For falsy values:
 * - ''
 * - 0
 * - NaN
 * - false
 * - null
 * - undefined
 * - 0n (whenever withBigInt: true)
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 1.26.0
 * @public
 */
export declare function falsy<TConstraints extends FalsyContraints>(constraints?: TConstraints): Arbitrary<FalsyValue<TConstraints>>;
//#endregion
//#region src/arbitrary/constant.d.ts
/**
 * For `value`
 * @param value - The value to produce
 * @remarks Since 0.0.1
 * @public
 */
export declare function constant<const T>(value: T): Arbitrary<T>;
//#endregion
//#region src/arbitrary/constantFrom.d.ts
/**
 * For one `...values` values - all equiprobable
 *
 * **WARNING**: It expects at least one value, otherwise it should throw
 *
 * @param values - Constant values to be produced (all values shrink to the first one)
 *
 * @remarks Since 0.0.12
 * @public
 */
declare function constantFrom<const T = never>(...values: T[]): Arbitrary<T>;
/**
 * For one `...values` values - all equiprobable
 *
 * **WARNING**: It expects at least one value, otherwise it should throw
 *
 * @param values - Constant values to be produced (all values shrink to the first one)
 *
 * @remarks Since 0.0.12
 * @public
 */
declare function constantFrom<TArgs extends any[] | [any]>(...values: TArgs): Arbitrary<TArgs[number]>;
//#endregion
//#region src/arbitrary/context.d.ts
/**
 * Execution context attached to one predicate run
 * @remarks Since 2.2.0
 * @public
 */
interface ContextValue {
  /**
   * Log execution details during a test.
   * Very helpful when troubleshooting failures
   * @param data - Data to be logged into the current context
   * @remarks Since 1.8.0
   */
  log(data: string): void;
  /**
   * Number of logs already logged into current context
   * @remarks Since 1.8.0
   */
  size(): number;
}
/**
 * Produce a {@link ContextValue} instance
 * @remarks Since 1.8.0
 * @public
 */
export declare function context(): Arbitrary<ContextValue>;
//#endregion
//#region src/arbitrary/date.d.ts
/**
 * Constraints to be applied on {@link date}
 * @remarks Since 3.3.0
 * @public
 */
interface DateConstraints {
  /**
   * Lower bound of the range (included)
   * @defaultValue new Date(-8640000000000000)
   * @remarks Since 1.17.0
   */
  min?: Date;
  /**
   * Upper bound of the range (included)
   * @defaultValue new Date(8640000000000000)
   * @remarks Since 1.17.0
   */
  max?: Date;
  /**
   * When set to true, no more "Invalid Date" can be generated.
   * @defaultValue false
   * @remarks Since 3.13.0
   */
  noInvalidDate?: boolean;
}
/**
 * For date between constraints.min or new Date(-8640000000000000) (included) and constraints.max or new Date(8640000000000000) (included)
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 1.17.0
 * @public
 */
export declare function date(constraints?: DateConstraints): Arbitrary<Date>;
//#endregion
//#region src/arbitrary/clone.d.ts
/**
 * Type of the value produced by {@link clone}
 * @remarks Since 2.5.0
 * @public
 */
type CloneValue<T, N extends number, Rest extends T[] = []> = [number] extends [N] ? T[] : Rest["length"] extends N ? Rest : CloneValue<T, N, [T, ...Rest]>;
/**
 * Clone the values generated by `arb` in order to produce fully equal values (might not be equal in terms of === or ==)
 *
 * @param arb - Source arbitrary
 * @param numValues - Number of values to produce
 *
 * @remarks Since 2.5.0
 * @public
 */
declare function clone<T, N extends number>(arb: Arbitrary<T>, numValues: N): Arbitrary<CloneValue<T, N>>;
//#endregion
//#region src/arbitrary/chainUntil.d.ts
/**
 * Build an arbitrary by iteratively chaining arbitraries until the chainer returns undefined.
 *
 * Starting from a value produced by `startArb`, the `chainer` function is called with the current value
 * to produce the next arbitrary. This process repeats until `chainer` returns `undefined`.
 * The final value in the chain is the one produced by this arbitrary.
 *
 * The implementation is fully iterative (non-recursive) and supports shrinking.
 *
 * @param startArb - The starting arbitrary producing the initial value
 * @param chainer - A function called with the current value that returns either the next arbitrary to generate from or undefined to stop the chain
 * @returns An arbitrary producing the last value in the chain
 *
 * @remarks Since 4.8.0
 * @public
 */
export declare function chainUntil<T>(startArb: Arbitrary<T>, chainer: (prev: T) => Arbitrary<T> | undefined): Arbitrary<T>;
//#endregion
//#region src/arbitrary/dictionary.d.ts
/**
 * Constraints to be applied on {@link dictionary}
 * @remarks Since 2.22.0
 * @public
 */
interface DictionaryConstraints {
  /**
   * Lower bound for the number of keys defined into the generated instance
   * @defaultValue 0
   * @remarks Since 2.22.0
   */
  minKeys?: number;
  /**
   * Upper bound for the number of keys defined into the generated instance
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.22.0
   */
  maxKeys?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
  /**
   * Depth identifier can be used to share the current depth between several instances.
   *
   * By default, if not specified, each instance of dictionary will have its own depth.
   * In other words: you can have depth=1 in one while you have depth=100 in another one.
   *
   * @remarks Since 3.15.0
   */
  depthIdentifier?: DepthIdentifier | string;
  /**
   * Do not generate objects with null prototype
   * @defaultValue false
   * @remarks Since 3.13.0
   */
  noNullPrototype?: boolean;
}
/**
 * For dictionaries with keys produced by `keyArb` and values from `valueArb`
 *
 * @param keyArb - Arbitrary used to generate the keys of the object
 * @param valueArb - Arbitrary used to generate the values of the object
 *
 * @remarks Since 1.0.0
 * @public
 */
export declare function dictionary<T>(keyArb: Arbitrary<string>, valueArb: Arbitrary<T>, constraints?: DictionaryConstraints): Arbitrary<Record<string, T>>;
/**
 * For dictionaries with keys produced by `keyArb` and values from `valueArb`
 *
 * @param keyArb - Arbitrary used to generate the keys of the object
 * @param valueArb - Arbitrary used to generate the values of the object
 *
 * @remarks Since 4.4.0
 * @public
 */
export declare function dictionary<K extends PropertyKey, V>(keyArb: Arbitrary<K>, valueArb: Arbitrary<V>, constraints?: DictionaryConstraints): Arbitrary<Record<K, V>>;
//#endregion
//#region src/arbitrary/emailAddress.d.ts
/**
 * Constraints to be applied on {@link emailAddress}
 * @remarks Since 2.22.0
 * @public
 */
interface EmailAddressConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For email address
 *
 * According to {@link https://www.ietf.org/rfc/rfc2821.txt | RFC 2821},
 * {@link https://www.ietf.org/rfc/rfc3696.txt | RFC 3696} and
 * {@link https://www.ietf.org/rfc/rfc5322.txt | RFC 5322}
 *
 * @param constraints - Constraints to apply when building instances (since 2.22.0)
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function emailAddress(constraints?: EmailAddressConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/double.d.ts
/**
 * Constraints to be applied on {@link double}
 * @remarks Since 2.6.0
 * @public
 */
interface DoubleConstraints {
  /**
   * Lower bound for the generated 64-bit floats (included, see minExcluded to exclude it)
   * @defaultValue Number.NEGATIVE_INFINITY, -1.7976931348623157e+308 when noDefaultInfinity is true
   * @remarks Since 2.8.0
   */
  min?: number;
  /**
   * Should the lower bound (aka min) be excluded?
   * Note: Excluding min=Number.NEGATIVE_INFINITY would result into having min set to -Number.MAX_VALUE.
   * @defaultValue false
   * @remarks Since 3.12.0
   */
  minExcluded?: boolean;
  /**
   * Upper bound for the generated 64-bit floats (included, see maxExcluded to exclude it)
   * @defaultValue Number.POSITIVE_INFINITY, 1.7976931348623157e+308 when noDefaultInfinity is true
   * @remarks Since 2.8.0
   */
  max?: number;
  /**
   * Should the upper bound (aka max) be excluded?
   * Note: Excluding max=Number.POSITIVE_INFINITY would result into having max set to Number.MAX_VALUE.
   * @defaultValue false
   * @remarks Since 3.12.0
   */
  maxExcluded?: boolean;
  /**
   * By default, lower and upper bounds are -infinity and +infinity.
   * By setting noDefaultInfinity to true, you move those defaults to minimal and maximal finite values.
   * @defaultValue false
   * @remarks Since 2.8.0
   */
  noDefaultInfinity?: boolean;
  /**
   * When set to true, no more Number.NaN can be generated.
   * @defaultValue false
   * @remarks Since 2.8.0
   */
  noNaN?: boolean;
  /**
   * When set to true, Number.isInteger(value) will be false for any generated value.
   * Note: -infinity and +infinity, or NaN can stil be generated except if you rejected them via another constraint.
   * @defaultValue false
   * @remarks Since 3.18.0
   */
  noInteger?: boolean;
}
/**
 * For 64-bit floating point numbers:
 * - sign: 1 bit
 * - significand: 52 bits
 * - exponent: 11 bits
 *
 * @param constraints - Constraints to apply when building instances (since 2.8.0)
 *
 * @remarks Since 0.0.6
 * @public
 */
export declare function double(constraints?: DoubleConstraints): Arbitrary<number>;
//#endregion
//#region src/arbitrary/float.d.ts
/**
 * Constraints to be applied on {@link float}
 * @remarks Since 2.6.0
 * @public
 */
interface FloatConstraints {
  /**
   * Lower bound for the generated 32-bit floats (included)
   * @defaultValue Number.NEGATIVE_INFINITY, -3.4028234663852886e+38 when noDefaultInfinity is true
   * @remarks Since 2.8.0
   */
  min?: number;
  /**
   * Should the lower bound (aka min) be excluded?
   * Note: Excluding min=Number.NEGATIVE_INFINITY would result into having min set to -3.4028234663852886e+38.
   * @defaultValue false
   * @remarks Since 3.12.0
   */
  minExcluded?: boolean;
  /**
   * Upper bound for the generated 32-bit floats (included)
   * @defaultValue Number.POSITIVE_INFINITY, 3.4028234663852886e+38 when noDefaultInfinity is true
   * @remarks Since 2.8.0
   */
  max?: number;
  /**
   * Should the upper bound (aka max) be excluded?
   * Note: Excluding max=Number.POSITIVE_INFINITY would result into having max set to 3.4028234663852886e+38.
   * @defaultValue false
   * @remarks Since 3.12.0
   */
  maxExcluded?: boolean;
  /**
   * By default, lower and upper bounds are -infinity and +infinity.
   * By setting noDefaultInfinity to true, you move those defaults to minimal and maximal finite values.
   * @defaultValue false
   * @remarks Since 2.8.0
   */
  noDefaultInfinity?: boolean;
  /**
   * When set to true, no more Number.NaN can be generated.
   * @defaultValue false
   * @remarks Since 2.8.0
   */
  noNaN?: boolean;
  /**
   * When set to true, Number.isInteger(value) will be false for any generated value.
   * Note: -infinity and +infinity, or NaN can stil be generated except if you rejected them via another constraint.
   * @defaultValue false
   * @remarks Since 3.18.0
   */
  noInteger?: boolean;
}
/**
 * For 32-bit floating point numbers:
 * - sign: 1 bit
 * - significand: 23 bits
 * - exponent: 8 bits
 *
 * The smallest non-zero value (in absolute value) that can be represented by such float is: 2 ** -126 * 2 ** -23.
 * And the largest one is: 2 ** 127 * (1 + (2 ** 23 - 1) / 2 ** 23).
 *
 * @param constraints - Constraints to apply when building instances (since 2.8.0)
 *
 * @remarks Since 0.0.6
 * @public
 */
export declare function float(constraints?: FloatConstraints): Arbitrary<number>;
//#endregion
//#region src/arbitrary/compareBooleanFunc.d.ts
/**
 * For comparison boolean functions
 *
 * A comparison boolean function returns:
 * - `true` whenever `a < b`
 * - `false` otherwise (ie. `a = b` or `a > b`)
 *
 * @remarks Since 1.6.0
 * @public
 */
export declare function compareBooleanFunc<T>(): Arbitrary<(a: T, b: T) => boolean>;
//#endregion
//#region src/arbitrary/compareFunc.d.ts
/**
 * For comparison functions
 *
 * A comparison function returns:
 * - negative value whenever `a < b`
 * - positive value whenever `a > b`
 * - zero whenever `a` and `b` are equivalent
 *
 * Comparison functions are transitive: `a < b and b < c => a < c`
 *
 * They also satisfy: `a < b <=> b > a` and `a = b <=> b = a`
 *
 * @remarks Since 1.6.0
 * @public
 */
export declare function compareFunc<T>(): Arbitrary<(a: T, b: T) => number>;
//#endregion
//#region src/arbitrary/func.d.ts
/**
 * For pure functions
 *
 * @param arb - Arbitrary responsible to produce the values
 *
 * @remarks Since 1.6.0
 * @public
 */
export declare function func<TArgs extends any[], TOut>(arb: Arbitrary<TOut>): Arbitrary<(...args: TArgs) => TOut>;
//#endregion
//#region src/arbitrary/domain.d.ts
/**
 * Constraints to be applied on {@link domain}
 * @remarks Since 2.22.0
 * @public
 */
interface DomainConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For domains
 * having an extension with at least two lowercase characters
 *
 * According to {@link https://www.ietf.org/rfc/rfc1034.txt | RFC 1034},
 * {@link https://www.ietf.org/rfc/rfc1035.txt | RFC 1035},
 * {@link https://www.ietf.org/rfc/rfc1123.txt | RFC 1123} and
 * {@link https://url.spec.whatwg.org/ | WHATWG URL Standard}
 *
 * @param constraints - Constraints to apply when building instances (since 2.22.0)
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function domain(constraints?: DomainConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/integer.d.ts
/**
 * Constraints to be applied on {@link integer}
 * @remarks Since 2.6.0
 * @public
 */
interface IntegerConstraints {
  /**
   * Lower bound for the generated integers (included)
   * @defaultValue -0x80000000
   * @remarks Since 2.6.0
   */
  min?: number;
  /**
   * Upper bound for the generated integers (included)
   * @defaultValue 0x7fffffff
   * @remarks Since 2.6.0
   */
  max?: number;
}
/**
 * For integers between min (included) and max (included)
 *
 * @param constraints - Constraints to apply when building instances (since 2.6.0)
 *
 * @remarks Since 0.0.1
 * @public
 */
export declare function integer(constraints?: IntegerConstraints): Arbitrary<number>;
//#endregion
//#region src/arbitrary/maxSafeInteger.d.ts
/**
 * For integers between Number.MIN_SAFE_INTEGER (included) and Number.MAX_SAFE_INTEGER (included)
 * @remarks Since 1.11.0
 * @public
 */
export declare function maxSafeInteger(): Arbitrary<number>;
//#endregion
//#region src/arbitrary/maxSafeNat.d.ts
/**
 * For positive integers between 0 (included) and Number.MAX_SAFE_INTEGER (included)
 * @remarks Since 1.11.0
 * @public
 */
export declare function maxSafeNat(): Arbitrary<number>;
//#endregion
//#region src/arbitrary/nat.d.ts
/**
 * Constraints to be applied on {@link nat}
 * @remarks Since 2.6.0
 * @public
 */
interface NatConstraints {
  /**
   * Upper bound for the generated postive integers (included)
   * @defaultValue 0x7fffffff
   * @remarks Since 2.6.0
   */
  max?: number;
}
/**
 * For positive integers between 0 (included) and 2147483647 (included)
 * @remarks Since 0.0.1
 * @public
 */
declare function nat(): Arbitrary<number>;
/**
 * For positive integers between 0 (included) and max (included)
 *
 * @param max - Upper bound for the generated integers
 *
 * @remarks You may prefer to use `fc.nat({max})` instead.
 * @remarks Since 0.0.1
 * @public
 */
declare function nat(max: number): Arbitrary<number>;
/**
 * For positive integers between 0 (included) and max (included)
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.6.0
 * @public
 */
declare function nat(constraints: NatConstraints): Arbitrary<number>;
/**
 * For positive integers between 0 (included) and max (included)
 *
 * @param arg - Either a maximum number or constraints to apply when building instances
 *
 * @remarks Since 2.6.0
 * @public
 */
declare function nat(arg?: number | NatConstraints): Arbitrary<number>;
//#endregion
//#region src/arbitrary/ipV4.d.ts
/**
 * For valid IP v4
 *
 * Following {@link https://tools.ietf.org/html/rfc3986#section-3.2.2 | RFC 3986}
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function ipV4(): Arbitrary<string>;
//#endregion
//#region src/arbitrary/ipV4Extended.d.ts
/**
 * For valid IP v4 according to WhatWG
 *
 * Following {@link https://url.spec.whatwg.org/ | WhatWG}, the specification for web-browsers
 *
 * There is no equivalent for IP v6 according to the {@link https://url.spec.whatwg.org/#concept-ipv6-parser | IP v6 parser}
 *
 * @remarks Since 1.17.0
 * @public
 */
export declare function ipV4Extended(): Arbitrary<string>;
//#endregion
//#region src/arbitrary/ipV6.d.ts
/**
 * For valid IP v6
 *
 * Following {@link https://tools.ietf.org/html/rfc3986#section-3.2.2 | RFC 3986}
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function ipV6(): Arbitrary<string>;
//#endregion
//#region src/arbitrary/letrec.d.ts
/**
 * Type of the value produced by {@link letrec}
 * @remarks Since 3.0.0
 * @public
 */
type LetrecValue<T> = { [K in keyof T]: Arbitrary<T[K]>; };
/**
 * Strongly typed type for the `tie` function passed by {@link letrec} to the `builder` function we pass to it.
 * You may want also want to use its loosely typed version {@link LetrecLooselyTypedTie}.
 *
 * @remarks Since 3.0.0
 * @public
 */
interface LetrecTypedTie<T> {
  <K extends keyof T>(key: K): Arbitrary<T[K]>;
  (key: string): Arbitrary<unknown>;
}
/**
 * Strongly typed type for the `builder` function passed to {@link letrec}.
 * You may want also want to use its loosely typed version {@link LetrecLooselyTypedBuilder}.
 *
 * @remarks Since 3.0.0
 * @public
 */
type LetrecTypedBuilder<T> = (tie: LetrecTypedTie<T>) => LetrecValue<T>;
/**
 * Loosely typed type for the `tie` function passed by {@link letrec} to the `builder` function we pass to it.
 * You may want also want to use its strongly typed version {@link LetrecTypedTie}.
 *
 * @remarks Since 3.0.0
 * @public
 */
type LetrecLooselyTypedTie = (key: string) => Arbitrary<unknown>;
/**
 * Loosely typed type for the `builder` function passed to {@link letrec}.
 * You may want also want to use its strongly typed version {@link LetrecTypedBuilder}.
 *
 * @remarks Since 3.0.0
 * @public
 */
type LetrecLooselyTypedBuilder<T> = (tie: LetrecLooselyTypedTie) => LetrecValue<T>;
/**
 * For mutually recursive types
 *
 * @example
 * ```typescript
 * type Leaf = number;
 * type Node = [Tree, Tree];
 * type Tree = Node | Leaf;
 * const { tree } = fc.letrec<{ tree: Tree, node: Node, leaf: Leaf }>(tie => ({
 *   tree: fc.oneof({depthSize: 'small'}, tie('leaf'), tie('node')),
 *   node: fc.tuple(tie('tree'), tie('tree')),
 *   leaf: fc.nat()
 * }));
 * // tree is 50% of node, 50% of leaf
 * // the ratio goes in favor of leaves as we go deeper in the tree (thanks to depthSize)
 * ```
 *
 * @param builder - Arbitraries builder based on themselves (through `tie`)
 *
 * @remarks Since 1.16.0
 * @public
 */
export declare function letrec<T>(builder: T extends Record<string, unknown> ? LetrecTypedBuilder<T> : never): LetrecValue<T>;
/**
 * For mutually recursive types
 *
 * @example
 * ```typescript
 * const { tree } = fc.letrec(tie => ({
 *   tree: fc.oneof({depthSize: 'small'}, tie('leaf'), tie('node')),
 *   node: fc.tuple(tie('tree'), tie('tree')),
 *   leaf: fc.nat()
 * }));
 * // tree is 50% of node, 50% of leaf
 * // the ratio goes in favor of leaves as we go deeper in the tree (thanks to depthSize)
 * ```
 *
 * @param builder - Arbitraries builder based on themselves (through `tie`)
 *
 * @remarks Since 1.16.0
 * @public
 */
export declare function letrec<T>(builder: LetrecLooselyTypedBuilder<T>): LetrecValue<T>;
//#endregion
//#region src/arbitrary/_internals/interfaces/EntityGraphTypes.d.ts
/**
 * Defines the shape of a single entity type, where each field is associated with
 * an arbitrary that generates values for that field.
 *
 * @example
 * ```typescript
 * // Employee entity with firstName and lastName fields
 * { firstName: fc.string(), lastName: fc.string() }
 * ```
 *
 * @remarks Since 4.5.0
 * @public
 */
type ArbitraryStructure<TFields> = { [TField in keyof TFields]: Arbitrary<TFields[TField]>; };
/**
 * Defines all entity types and their data fields for {@link entityGraph}.
 *
 * This is the first argument to {@link entityGraph} and specifies the non-relational properties
 * of each entity type. Each key is the name of an entity type and its value defines the
 * arbitraries for that entity.
 *
 * @example
 * ```typescript
 * {
 *   employee: { name: fc.string(), age: fc.nat(100) },
 *   team: { name: fc.string(), size: fc.nat(50) }
 * }
 * ```
 *
 * @remarks Since 4.5.0
 * @public
 */
type Arbitraries<TEntityFields> = { [TEntityName in keyof TEntityFields]: ArbitraryStructure<TEntityFields[TEntityName]>; };
/**
 * Cardinality of a relationship between entities.
 *
 * Determines how many target entities can be referenced:
 * - `'0-1'`: Optional relationship — references zero or one target entity (value or undefined)
 * - `'1'`: Required relationship — always references exactly one target entity
 * - `'many'`: Multi-valued relationship — references an array of target entities (may be empty, no duplicates)
 * - `'inverse'`: Inverse relationship — automatically computed array of entities that reference this entity through a specified forward relationship
 *
 * @remarks Since 4.5.0
 * @public
 */
type Arity = "0-1" | "1" | "many" | "inverse";
/**
 * Defines restrictions on which entities can be targeted by a relationship.
 *
 * - `'any'`: No restrictions — any entity of the target type can be referenced
 * - `'exclusive'`: Each target entity can only be referenced by one relationship (prevents sharing)
 * - `'successor'`: Target must appear later in the entity list (prevents cycles)
 *
 * @defaultValue 'any'
 * @remarks Since 4.5.0
 * @public
 */
type Strategy = "any" | "exclusive" | "successor";
/**
 * Specifies a single relationship between entity types.
 *
 * A relationship defines how one entity type references another (or itself). This configuration
 * determines both the cardinality of the relationship and any restrictions on which entities
 * can be referenced.
 *
 * @example
 * ```typescript
 * // An employee has an optional manager who is also an employee
 * { arity: '0-1', type: 'employee', strategy: 'successor' }
 *
 * // A team has exactly one department
 * { arity: '1', type: 'department' }
 *
 * // An employee can have multiple competencies
 * { arity: 'many', type: 'competency' }
 * ```
 *
 * @remarks Since 4.5.0
 * @public
 */
type Relationship<TTypeNames> = {
  /**
   * Cardinality of the relationship — determines how many target entities can be referenced.
   *
   * - `'0-1'`: Optional — produces undefined or a single instance of the target type
   * - `'1'`: Required — always produces a single instance of the target type
   * - `'many'`: Multi-valued — produces an array of target instances (may be empty, contains no duplicates)
   * - `'inverse'`: Inverse — automatically produces an array of entities that reference this entity via the specified forward relationship
   *
   * @remarks Since 4.5.0
   */
  arity: Arity;
  /**
   * The name of the entity type being referenced by this relationship.
   *
   * Must be one of the entity type names defined in the first argument to {@link entityGraph}.
   *
   * @remarks Since 4.5.0
   */
  type: TTypeNames;
} & ({
  arity: Exclude<Arity, "inverse">;
  /**
   * Constrains which target entities are eligible to be referenced.
   *
   * - `'any'`: No restrictions — any entity of the target type can be selected
   * - `'exclusive'`: Each target can only be used once — prevents multiple relationships from referencing the same entity
   * - `'successor'`: Target must appear after the source in the entity array — prevents self-references and cycles
   *
   * @defaultValue 'any'
   * @remarks Since 4.5.0
   */
  strategy?: Strategy;
} | {
  arity: "inverse";
  /**
   * Name of the forward relationship property in the target type that references this entity type.
   * The inverse relationship will contain all entities that reference this entity through that forward relationship.
   *
   * @example
   * ```typescript
   * // If 'employee' has 'team: { arity: "1", type: "team" }'
   * // Then 'team' can have 'members: { arity: "inverse", type: "employee", forwardRelationship: "team" }'
   * ```
   *
   * @remarks Since 4.5.0
   */
  forwardRelationship: string;
});
/**
 * Defines all relationships between entity types for {@link entityGraph}.
 *
 * This is the second argument to {@link entityGraph} and specifies how entities reference each other.
 * Each entity type can have zero or more relationship fields, where each field defines a link
 * to other entities.
 *
 * @example
 * ```typescript
 * {
 *   employee: {
 *     manager: { arity: '0-1', type: 'employee' },
 *     team: { arity: '1', type: 'team' }
 *   },
 *   team: {}
 * }
 * ```
 *
 * @remarks Since 4.5.0
 * @public
 */
type EntityRelations<TEntityFields> = { [TEntityName in keyof TEntityFields]: { [TField in string]: Relationship<keyof TEntityFields>; }; };
type RelationsToValue<TRelations, TValues> = { [TField in keyof TRelations]: TRelations[TField] extends {
  arity: "0-1";
  type: infer TTypeName extends keyof TValues;
} ? TValues[TTypeName] | undefined : TRelations[TField] extends {
  arity: "1";
  type: infer TTypeName extends keyof TValues;
} ? TValues[TTypeName] : TRelations[TField] extends {
  arity: "many";
  type: infer TTypeName extends keyof TValues;
} ? TValues[TTypeName][] : TRelations[TField] extends {
  arity: "inverse";
  type: infer TTypeName extends keyof TValues;
} ? TValues[TTypeName][] : never; };
type Prettify$1<T> = { [K in keyof T]: T[K]; } & {};
type EntityGraphSingleValue<TEntityFields, TEntityRelations extends EntityRelations<TEntityFields>> = { [TEntityName in keyof TEntityFields]: Prettify$1<TEntityFields[TEntityName] & RelationsToValue<TEntityRelations[TEntityName], EntityGraphSingleValue<TEntityFields, TEntityRelations>>>; };
/**
 * Type of the values generated by {@link entityGraph}.
 *
 * The output is an object where each key is an entity type name and each value is an array
 * of entities of that type. Each entity contains both its data fields (from arbitraries) and
 * relationship fields (from relations), with relationships resolved to actual entity references.
 *
 * @remarks Since 4.5.0
 * @public
 */
type EntityGraphValue<TEntityFields, TEntityRelations extends EntityRelations<TEntityFields>> = { [TEntityName in keyof EntityGraphSingleValue<TEntityFields, TEntityRelations>]: EntityGraphSingleValue<TEntityFields, TEntityRelations>[TEntityName][]; };
//#endregion
//#region src/arbitrary/uniqueArray.d.ts
/**
 * Shared constraints to be applied on {@link uniqueArray}
 * @remarks Since 2.23.0
 * @public
 */
type UniqueArraySharedConstraints = {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 2.23.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.23.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.23.0
   */
  size?: SizeForArbitrary;
  /**
   * When receiving a depth identifier, the arbitrary will impact the depth
   * attached to it to avoid going too deep if it already generated lots of items.
   *
   * In other words, if the number of generated values within the collection is large
   * then the generated items will tend to be less deep to avoid creating structures a lot
   * larger than expected.
   *
   * For the moment, the depth is not taken into account to compute the number of items to
   * define for a precise generate call of the array. Just applied onto eligible items.
   *
   * @remarks Since 2.25.0
   */
  depthIdentifier?: DepthIdentifier | string;
};
/**
 * Constraints implying known and optimized comparison function
 * to be applied on {@link uniqueArray}
 *
 * @remarks Since 2.23.0
 * @public
 */
type UniqueArrayConstraintsRecommended<T, U> = UniqueArraySharedConstraints & {
  /**
   * The operator to be used to compare the values after having applied the selector (if any):
   * - SameValue behaves like `Object.is` — {@link https://tc39.es/ecma262/multipage/abstract-operations.html#sec-samevalue}
   * - SameValueZero behaves like `Set` or `Map` — {@link https://tc39.es/ecma262/multipage/abstract-operations.html#sec-samevaluezero}
   * - IsStrictlyEqual behaves like `===` — {@link https://tc39.es/ecma262/multipage/abstract-operations.html#sec-isstrictlyequal}
   * - Fully custom comparison function: it implies performance costs for large arrays
   *
   * @defaultValue 'SameValue'
   * @remarks Since 2.23.0
   */
  comparator?: "SameValue" | "SameValueZero" | "IsStrictlyEqual";
  /**
   * How we should project the values before comparing them together
   * @defaultValue (v =&gt; v)
   * @remarks Since 2.23.0
   */
  selector?: (v: T) => U;
};
/**
 * Constraints implying a fully custom comparison function
 * to be applied on {@link uniqueArray}
 *
 * WARNING - Imply an extra performance cost whenever you want to generate large arrays
 *
 * @remarks Since 2.23.0
 * @public
 */
type UniqueArrayConstraintsCustomCompare<T> = UniqueArraySharedConstraints & {
  /**
   * The operator to be used to compare the values after having applied the selector (if any)
   * @remarks Since 2.23.0
   */
  comparator: (a: T, b: T) => boolean;
  /**
   * How we should project the values before comparing them together
   * @remarks Since 2.23.0
   */
  selector?: undefined;
};
/**
 * Constraints implying fully custom comparison function and selector
 * to be applied on {@link uniqueArray}
 *
 * WARNING - Imply an extra performance cost whenever you want to generate large arrays
 *
 * @remarks Since 2.23.0
 * @public
 */
type UniqueArrayConstraintsCustomCompareSelect<T, U> = UniqueArraySharedConstraints & {
  /**
   * The operator to be used to compare the values after having applied the selector (if any)
   * @remarks Since 2.23.0
   */
  comparator: (a: U, b: U) => boolean;
  /**
   * How we should project the values before comparing them together
   * @remarks Since 2.23.0
   */
  selector: (v: T) => U;
};
/**
 * Constraints implying known and optimized comparison function
 * to be applied on {@link uniqueArray}
 *
 * The defaults relies on the defaults specified by {@link UniqueArrayConstraintsRecommended}
 *
 * @remarks Since 2.23.0
 * @public
 */
type UniqueArrayConstraints<T, U> = UniqueArrayConstraintsRecommended<T, U> | UniqueArrayConstraintsCustomCompare<T> | UniqueArrayConstraintsCustomCompareSelect<T, U>;
/**
 * For arrays of unique values coming from `arb`
 *
 * @param arb - Arbitrary used to generate the values inside the array
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.23.0
 * @public
 */
export declare function uniqueArray<T, U>(arb: Arbitrary<T>, constraints?: UniqueArrayConstraintsRecommended<T, U>): Arbitrary<T[]>;
/**
 * For arrays of unique values coming from `arb`
 *
 * @param arb - Arbitrary used to generate the values inside the array
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.23.0
 * @public
 */
export declare function uniqueArray<T>(arb: Arbitrary<T>, constraints: UniqueArrayConstraintsCustomCompare<T>): Arbitrary<T[]>;
/**
 * For arrays of unique values coming from `arb`
 *
 * @param arb - Arbitrary used to generate the values inside the array
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.23.0
 * @public
 */
export declare function uniqueArray<T, U>(arb: Arbitrary<T>, constraints: UniqueArrayConstraintsCustomCompareSelect<T, U>): Arbitrary<T[]>;
/**
 * For arrays of unique values coming from `arb`
 *
 * @param arb - Arbitrary used to generate the values inside the array
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 2.23.0
 * @public
 */
export declare function uniqueArray<T, U>(arb: Arbitrary<T>, constraints: UniqueArrayConstraints<T, U>): Arbitrary<T[]>;
//#endregion
//#region src/arbitrary/entityGraph.d.ts
/**
 * Constraints to be applied on {@link entityGraph}
 * @remarks Since 4.5.0
 * @public
 */
type EntityGraphConstraints<TEntityFields> = {
  /**
   * Controls the minimum number of entities generated for each entity type in the initial pool.
   *
   * The initial pool defines the baseline set of entities that are created before any relationships
   * are established. Other entities may be created later to satisfy relationship requirements.
   *
   * @example
   * ```typescript
   * // Ensure at least 2 employees and at most 5 teams in the initial pool
   * // But possibly more than 5 teams at the end
   * { initialPoolConstraints: { employee: { minLength: 2 }, team: { maxLength: 5 } } }
   * ```
   *
   * @defaultValue When unspecified, defaults from {@link array} are used for each entity type
   * @remarks Since 4.5.0
   */
  initialPoolConstraints?: { [EntityName in keyof TEntityFields]?: ArrayConstraints; };
  /**
   * Defines uniqueness criteria for entities of each type to prevent duplicate values.
   *
   * The selector function extracts a key from each entity. Entities with identical keys
   * (compared using `Object.is`) are considered duplicates and only one instance will be kept.
   *
   * @example
   * ```typescript
   * // Ensure employees have unique names
   * { unicityConstraints: { employee: (emp) => emp.name } }
   * ```
   *
   * @defaultValue All entities are considered unique (no deduplication is performed)
   * @remarks Since 4.5.0
   */
  unicityConstraints?: { [EntityName in keyof TEntityFields]?: UniqueArrayConstraintsRecommended<TEntityFields[EntityName], unknown>["selector"]; };
  /**
   * Do not generate values with null prototype
   * @defaultValue false
   * @remarks Since 4.5.0
   */
  noNullPrototype?: boolean;
};
/**
 * Constraints to be applied on {@link entityGraph}
 * @remarks Since 4.5.0
 * @public
 * @deprecated This type has a typo. Use `EntityGraphConstraints` instead.
 */
type EntityGraphContraints<TEntityFields> = EntityGraphConstraints<TEntityFields>;
/**
 * Generates interconnected entities with relationships based on a schema definition.
 *
 * This arbitrary creates structured data where entities can reference each other through defined
 * relationships. The generated values automatically include links between entities, making it
 * ideal for testing graph structures, relational data, or interconnected object models.
 *
 * The output is an object where each key corresponds to an entity type and the value is an array
 * of entities of that type. Entities contain both their data fields and relationship links.
 *
 * @example
 * ```typescript
 * // Generate a simple directed graph where nodes link to other nodes
 * fc.entityGraph(
 *   { node: { id: fc.stringMatching(/^[A-Z][a-z]*$/) } },
 *   { node: { linkTo: { arity: 'many', type: 'node' } } },
 * )
 * // Produces: { node: [{ id: "Abc", linkTo: [<node#1>, <node#0>] }, ...] }
 * ```
 *
 * @example
 * ```typescript
 * // Generate employees with managers and teams
 * fc.entityGraph(
 *   {
 *     employee: { name: fc.string() },
 *     team: { name: fc.string() }
 *   },
 *   {
 *     employee: {
 *       manager: { arity: '0-1', type: 'employee' },  // Optional manager
 *       team: { arity: '1', type: 'team' }           // Required team
 *     },
 *     team: {}
 *   }
 * )
 * ```
 *
 * @param arbitraries - Defines the data fields for each entity type (non-relational properties)
 * @param relations - Defines how entities reference each other (relational properties)
 * @param constraints - Optional configuration to customize generation behavior
 *
 * @remarks Since 4.5.0
 * @public
 */
export declare function entityGraph<TEntityFields, TEntityRelations extends EntityRelations<TEntityFields>>(arbitraries: Arbitraries<TEntityFields>, relations: TEntityRelations, constraints?: EntityGraphConstraints<TEntityFields>): Arbitrary<EntityGraphValue<TEntityFields, TEntityRelations>>;
//#endregion
//#region src/arbitrary/lorem.d.ts
/**
 * Constraints to be applied on {@link lorem}
 * @remarks Since 2.5.0
 * @public
 */
interface LoremConstraints {
  /**
   * Maximal number of entities:
   * - maximal number of words in case mode is 'words'
   * - maximal number of sentences in case mode is 'sentences'
   *
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.5.0
   */
  maxCount?: number;
  /**
   * Type of strings that should be produced by {@link lorem}:
   * - words: multiple words
   * - sentences: multiple sentences
   *
   * @defaultValue 'words'
   * @remarks Since 2.5.0
   */
  mode?: "words" | "sentences";
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
}
/**
 * For lorem ipsum string of words or sentences with maximal number of words or sentences
 *
 * @param constraints - Constraints to be applied onto the generated value (since 2.5.0)
 *
 * @remarks Since 0.0.1
 * @public
 */
export declare function lorem(constraints?: LoremConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/map.d.ts
/**
 * Constraints to be applied on {@link map}
 * @remarks Since 4.4.0
 * @public
 */
interface MapConstraints {
  /**
   * Lower bound for the number of entries defined into the generated instance
   * @defaultValue 0
   * @remarks Since 4.4.0
   */
  minKeys?: number;
  /**
   * Upper bound for the number of entries defined into the generated instance
   * @defaultValue 0x7fffffff
   * @remarks Since 4.4.0
   */
  maxKeys?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 4.4.0
   */
  size?: SizeForArbitrary;
  /**
   * Depth identifier can be used to share the current depth between several instances.
   *
   * By default, if not specified, each instance of map will have its own depth.
   * In other words: you can have depth=1 in one while you have depth=100 in another one.
   *
   * @remarks Since 4.4.0
   */
  depthIdentifier?: DepthIdentifier | string;
}
/**
 * For Maps with keys produced by `keyArb` and values from `valueArb`
 *
 * @param keyArb - Arbitrary used to generate the keys of the Map
 * @param valueArb - Arbitrary used to generate the values of the Map
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 4.4.0
 * @public
 */
export declare function map<K, V>(keyArb: Arbitrary<K>, valueArb: Arbitrary<V>, constraints?: MapConstraints): Arbitrary<Map<K, V>>;
//#endregion
//#region src/arbitrary/mapToConstant.d.ts
/**
 * Generate non-contiguous ranges of values
 * by mapping integer values to constant
 *
 * @param options - Builders to be called to generate the values
 *
 * @example
 * ```
 * // generate alphanumeric values (a-z0-9)
 * mapToConstant(
 *   { num: 26, build: v => String.fromCharCode(v + 0x61) },
 *   { num: 10, build: v => String.fromCharCode(v + 0x30) },
 * )
 * ```
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function mapToConstant<T>(...entries: {
  num: number;
  build: (idInGroup: number) => T;
}[]): Arbitrary<T>;
//#endregion
//#region src/arbitrary/memo.d.ts
/**
 * Output type for {@link memo}
 * @remarks Since 1.16.0
 * @public
 */
type Memo<T> = (maxDepth?: number) => Arbitrary<T>;
/**
 * For mutually recursive types
 *
 * @example
 * ```typescript
 * // tree is 1 / 3 of node, 2 / 3 of leaf
 * const tree: fc.Memo<Tree> = fc.memo(n => fc.oneof(node(n), leaf(), leaf()));
 * const node: fc.Memo<Tree> = fc.memo(n => {
 *   if (n <= 1) return fc.record({ left: leaf(), right: leaf() });
 *   return fc.record({ left: tree(), right: tree() }); // tree() is equivalent to tree(n-1)
 * });
 * const leaf = fc.nat;
 * ```
 *
 * @param builder - Arbitrary builder taken the maximal depth allowed as input (parameter `n`)
 *
 * @remarks Since 1.16.0
 * @public
 */
export declare function memo<T>(builder: (maxDepth: number) => Arbitrary<T>): Memo<T>;
//#endregion
//#region src/arbitrary/mixedCase.d.ts
/**
 * Constraints to be applied on {@link mixedCase}
 * @remarks Since 1.17.0
 * @public
 */
interface MixedCaseConstraints {
  /**
   * Transform a character to its upper and/or lower case version
   * @defaultValue try `toUpperCase` on the received code-point, if no effect try `toLowerCase`
   * @remarks Since 1.17.0
   */
  toggleCase?: (rawChar: string) => string;
  /**
   * In order to be fully reversable (only in case you want to shrink user definable values)
   * you should provide a function taking a string containing possibly toggled items and returning its
   * untoggled version.
   */
  untoggleAll?: (toggledString: string) => string;
}
/**
 * Randomly switch the case of characters generated by `stringArb` (upper/lower)
 *
 * WARNING:
 * Require bigint support.
 * Under-the-hood the arbitrary relies on bigint to compute the flags that should be toggled or not.
 *
 * @param stringArb - Arbitrary able to build string values
 * @param constraints - Constraints to be applied when computing upper/lower case version
 *
 * @remarks Since 1.17.0
 * @public
 */
export declare function mixedCase(stringArb: Arbitrary<string>, constraints?: MixedCaseConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/_shared/StringSharedConstraints.d.ts
/**
 * Constraints to be applied on arbitraries for strings
 * @remarks Since 2.4.0
 * @public
 */
interface StringSharedConstraints {
  /**
   * Lower bound of the generated string length (included)
   * @defaultValue 0
   * @remarks Since 2.4.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated string length (included)
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.4.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
}
//#endregion
//#region src/arbitrary/string.d.ts
/**
 * Constraints to be applied on arbitrary {@link string}
 * @remarks Since 3.22.0
 * @public
 */
type StringConstraints = StringSharedConstraints & {
  /**
   * A string results from the join between several unitary strings produced by the Arbitrary instance defined by `unit`.
   * The `minLength` and `maxLength` refers to the number of these units composing the string. In other words it does not have to be confound with `.length` on an instance of string.
   *
   * A unit can either be a fully custom Arbitrary or one of the pre-defined options:
   * - `'grapheme'` - Any printable grapheme as defined by the Unicode standard. This unit includes graphemes that may:
   *   - Span multiple code points (e.g., `'\u{0061}\u{0300}'`)
   *   - Consist of multiple characters (e.g., `'\u{1f431}'`)
   *   - Include non-European and non-ASCII characters.
   *   - **Note:** Graphemes produced by this unit are designed to remain visually distinct when joined together.
   *   - **Note:** We are relying on the specifications of Unicode 15.
   * - `'grapheme-composite'` - Any printable grapheme limited to a single code point. This option produces graphemes limited to a single code point.
   *   - **Note:** Graphemes produced by this unit are designed to remain visually distinct when joined together.
   *   - **Note:** We are relying on the specifications of Unicode 15.
   * - `'grapheme-ascii'` - Any printable ASCII character.
   * - `'binary'` - Any possible code point (except half surrogate pairs), regardless of how it may combine with subsequent code points in the produced string. This unit produces a single code point within the full Unicode range (0000-10FFFF).
   * - `'binary-ascii'` - Any possible ASCII character, including control characters. This unit produces any code point in the range 0000-00FF.
   *
   * @defaultValue 'grapheme-ascii'
   * @remarks Since 3.22.0
   */
  unit?: "grapheme" | "grapheme-composite" | "grapheme-ascii" | "binary" | "binary-ascii" | Arbitrary<string>;
};
/**
 * For strings of {@link char}
 *
 * @param constraints - Constraints to apply when building instances (since 2.4.0)
 *
 * @remarks Since 0.0.1
 * @public
 */
export declare function string(constraints?: StringConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/_internals/helpers/QualifiedObjectConstraints.d.ts
/**
 * Constraints for {@link anything} and {@link object}
 * @public
 */
interface ObjectConstraints {
  /**
   * Limit the depth of the object by increasing the probability to generate simple values (defined via values)
   * as we go deeper in the object.
   * @remarks Since 2.20.0
   */
  depthSize?: DepthSize;
  /**
   * Maximal depth allowed
   * @defaultValue Number.POSITIVE_INFINITY — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 0.0.7
   */
  maxDepth?: number;
  /**
   * Maximal number of keys
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 1.13.0
   */
  maxKeys?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
  /**
   * Arbitrary for keys
   * @defaultValue {@link string}
   * @remarks Since 0.0.7
   */
  key?: Arbitrary<string>;
  /**
   * Arbitrary for values
   * @defaultValue {@link boolean}, {@link integer}, {@link double}, {@link string}, null, undefined, Number.NaN, +0, -0, Number.EPSILON, Number.MIN_VALUE, Number.MAX_VALUE, Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY
   * @remarks Since 0.0.7
   */
  values?: Arbitrary<unknown>[];
  /**
   * Also generate boxed versions of values
   * @defaultValue false
   * @remarks Since 1.11.0
   */
  withBoxedValues?: boolean;
  /**
   * Also generate Set
   * @defaultValue false
   * @remarks Since 1.11.0
   */
  withSet?: boolean;
  /**
   * Also generate Map
   * @defaultValue false
   * @remarks Since 1.11.0
   */
  withMap?: boolean;
  /**
   * Also generate string representations of object instances
   * @defaultValue false
   * @remarks Since 1.17.0
   */
  withObjectString?: boolean;
  /**
   * Also generate object with null prototype
   * @defaultValue false
   * @remarks Since 1.23.0
   */
  withNullPrototype?: boolean;
  /**
   * Also generate BigInt
   * @defaultValue false
   * @remarks Since 1.26.0
   */
  withBigInt?: boolean;
  /**
   * Also generate Date
   * @defaultValue false
   * @remarks Since 2.5.0
   */
  withDate?: boolean;
  /**
   * Also generate typed arrays in: (Uint|Int)(8|16|32)Array and Float(32|64)Array
   * Remark: no typed arrays made of bigint
   * @defaultValue false
   * @remarks Since 2.9.0
   */
  withTypedArray?: boolean;
  /**
   * Also generate sparse arrays (arrays with holes)
   * @defaultValue false
   * @remarks Since 2.13.0
   */
  withSparseArray?: boolean;
  /**
   * Replace the arbitrary of strings defaulted for key and values by one able to generate unicode strings with non-ascii characters.
   * If you override key and/or values constraint, this flag will not apply to your override.
   * @deprecated Prefer using `stringUnit` to customize the kind of strings that will be generated by default.
   * @defaultValue false
   * @remarks Since 3.19.0
   */
  withUnicodeString?: boolean;
  /**
   * Replace the default unit for strings.
   * @defaultValue undefined
   * @remarks Since 3.23.0
   */
  stringUnit?: StringConstraints["unit"];
}
//#endregion
//#region src/arbitrary/object.d.ts
/**
 * For any objects
 *
 * You may use {@link sample} to preview the values that will be generated
 *
 * @example
 * ```javascript
 * {}, {k: [{}, 1, 2]}
 * ```
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function object(): Arbitrary<Record<string, unknown>>;
/**
 * For any objects following the constraints defined by `settings`
 *
 * You may use {@link sample} to preview the values that will be generated
 *
 * @example
 * ```javascript
 * {}, {k: [{}, 1, 2]}
 * ```
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function object(constraints: ObjectConstraints): Arbitrary<Record<string, unknown>>;
//#endregion
//#region src/arbitrary/_internals/helpers/JsonConstraintsBuilder.d.ts
/**
 * Shared constraints for:
 * - {@link json},
 * - {@link jsonValue},
 *
 * @remarks Since 2.5.0
 * @public
 */
interface JsonSharedConstraints {
  /**
   * Limit the depth of the object by increasing the probability to generate simple values (defined via values)
   * as we go deeper in the object.
   *
   * @remarks Since 2.20.0
   */
  depthSize?: DepthSize;
  /**
   * Maximal depth allowed
   * @defaultValue Number.POSITIVE_INFINITY — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.5.0
   */
  maxDepth?: number;
  /**
   * Only generate instances having keys and values made of ascii strings (when true)
   * @deprecated Prefer using `stringUnit` to customize the kind of strings that will be generated by default.
   * @defaultValue true
   * @remarks Since 3.19.0
   */
  noUnicodeString?: boolean;
  /**
   * Replace the default unit for strings.
   * @defaultValue undefined
   * @remarks Since 3.23.0
   */
  stringUnit?: StringConstraints["unit"];
}
/**
 * Typings for a Json array
 * @remarks Since 2.20.0
 * @public
 */
type JsonArray = Array<JsonValue>;
/**
 * Typings for a Json object
 * @remarks Since 2.20.0
 * @public
 */
type JsonObject = { [key in string]?: JsonValue; };
/**
 * Typings for a Json value
 * @remarks Since 2.20.0
 * @public
 */
type JsonValue = boolean | number | string | null | JsonArray | JsonObject;
//#endregion
//#region src/arbitrary/json.d.ts
/**
 * For any JSON strings
 *
 * Keys and string values rely on {@link string}
 *
 * @param constraints - Constraints to be applied onto the generated instance (since 2.5.0)
 *
 * @remarks Since 0.0.7
 * @public
 */
export declare function json(constraints?: JsonSharedConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/anything.d.ts
/**
 * For any type of values
 *
 * You may use {@link sample} to preview the values that will be generated
 *
 * @example
 * ```javascript
 * null, undefined, 42, 6.5, 'Hello', {}, {k: [{}, 1, 2]}
 * ```
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function anything(): Arbitrary<unknown>;
/**
 * For any type of values following the constraints defined by `settings`
 *
 * You may use {@link sample} to preview the values that will be generated
 *
 * @example
 * ```javascript
 * null, undefined, 42, 6.5, 'Hello', {}, {k: [{}, 1, 2]}
 * ```
 *
 * @example
 * ```typescript
 * // Using custom settings
 * fc.anything({
 *     key: fc.string(),
 *     values: [fc.integer(10,20), fc.constant(42)],
 *     maxDepth: 2
 * });
 * // Can build entries such as:
 * // - 19
 * // - [{"2":12,"k":15,"A":42}]
 * // - {"4":[19,13,14,14,42,11,20,11],"6":42,"7":16,"L":10,"'":[20,11],"e":[42,20,42,14,13,17]}
 * // - [42,42,42]...
 * ```
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 0.0.7
 * @public
 */
declare function anything(constraints: ObjectConstraints): Arbitrary<unknown>;
//#endregion
//#region src/arbitrary/jsonValue.d.ts
/**
 * For any JSON compliant values
 *
 * Keys and string values rely on {@link string}
 *
 * As `JSON.parse` preserves `-0`, `jsonValue` can also have `-0` as a value.
 * `jsonValue` must be seen as: any value that could have been built by doing a `JSON.parse` on a given string.
 *
 * @param constraints - Constraints to be applied onto the generated instance
 *
 * @remarks Since 2.20.0
 * @public
 */
export declare function jsonValue(constraints?: JsonSharedConstraints): Arbitrary<JsonValue>;
//#endregion
//#region src/arbitrary/oneof.d.ts
/**
 * Conjonction of a weight and an arbitrary used by {@link oneof}
 * in order to generate values
 *
 * @remarks Since 1.18.0
 * @public
 */
interface WeightedArbitrary<T> {
  /**
   * Weight to be applied when selecting which arbitrary should be used
   * @remarks Since 0.0.7
   */
  weight: number;
  /**
   * Instance of Arbitrary
   * @remarks Since 0.0.7
   */
  arbitrary: Arbitrary<T>;
}
/**
 * Either an `Arbitrary<T>` or a `WeightedArbitrary<T>`
 * @remarks Since 3.0.0
 * @public
 */
type MaybeWeightedArbitrary<T> = Arbitrary<T> | WeightedArbitrary<T>;
/**
 * Infer the type of the Arbitrary produced by {@link oneof}
 * given the type of the source arbitraries
 *
 * @remarks Since 2.2.0
 * @public
 */
type OneOfValue<Ts extends MaybeWeightedArbitrary<unknown>[]> = { [K in keyof Ts]: Ts[K] extends MaybeWeightedArbitrary<infer U> ? U : never; }[number];
/**
 * Constraints to be applied on {@link oneof}
 * @remarks Since 2.14.0
 * @public
 */
type OneOfConstraints = {
  /**
   * When set to true, the shrinker of oneof will try to check if the first arbitrary
   * could have been used to discover an issue. It allows to shrink trees.
   *
   * Warning: First arbitrary must be the one resulting in the smallest structures
   * for usages in deep tree-like structures.
   *
   * @defaultValue false
   * @remarks Since 2.14.0
   */
  withCrossShrink?: boolean;
  /**
   * While going deeper and deeper within a recursive structure (see {@link letrec}),
   * this factor will be used to increase the probability to generate instances
   * of the first passed arbitrary.
   *
   * @remarks Since 2.14.0
   */
  depthSize?: DepthSize;
  /**
   * Maximal authorized depth.
   * Once this depth has been reached only the first arbitrary will be used.
   *
   * @defaultValue Number.POSITIVE_INFINITY — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.14.0
   */
  maxDepth?: number;
  /**
   * Depth identifier can be used to share the current depth between several instances.
   *
   * By default, if not specified, each instance of oneof will have its own depth.
   * In other words: you can have depth=1 in one while you have depth=100 in another one.
   *
   * @remarks Since 2.14.0
   */
  depthIdentifier?: DepthIdentifier | string;
};
/**
 * For one of the values generated by `...arbs` - with all `...arbs` equiprobable
 *
 * **WARNING**: It expects at least one arbitrary
 *
 * @param arbs - Arbitraries that might be called to produce a value
 *
 * @remarks Since 0.0.1
 * @public
 */
declare function oneof<Ts extends MaybeWeightedArbitrary<unknown>[]>(...arbs: Ts): Arbitrary<OneOfValue<Ts>>;
/**
 * For one of the values generated by `...arbs` - with all `...arbs` equiprobable
 *
 * **WARNING**: It expects at least one arbitrary
 *
 * @param constraints - Constraints to be applied when generating the values
 * @param arbs - Arbitraries that might be called to produce a value
 *
 * @remarks Since 2.14.0
 * @public
 */
declare function oneof<Ts extends MaybeWeightedArbitrary<unknown>[]>(constraints: OneOfConstraints, ...arbs: Ts): Arbitrary<OneOfValue<Ts>>;
//#endregion
//#region src/arbitrary/option.d.ts
/**
 * Constraints to be applied on {@link option}
 * @remarks Since 2.2.0
 * @public
 */
interface OptionConstraints<TNil = null> {
  /**
   * The probability to build a nil value is of `1 / freq`.
   * @defaultValue 6
   * @remarks Since 1.17.0
   */
  freq?: number;
  /**
   * The nil value
   * @defaultValue null
   * @remarks Since 1.17.0
   */
  nil?: TNil;
  /**
   * While going deeper and deeper within a recursive structure (see {@link letrec}),
   * this factor will be used to increase the probability to generate nil.
   *
   * @remarks Since 2.14.0
   */
  depthSize?: DepthSize;
  /**
   * Maximal authorized depth. Once this depth has been reached only nil will be used.
   * @defaultValue Number.POSITIVE_INFINITY — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.14.0
   */
  maxDepth?: number;
  /**
   * Depth identifier can be used to share the current depth between several instances.
   *
   * By default, if not specified, each instance of option will have its own depth.
   * In other words: you can have depth=1 in one while you have depth=100 in another one.
   *
   * @remarks Since 2.14.0
   */
  depthIdentifier?: DepthIdentifier | string;
}
/**
 * For either nil or a value coming from `arb` with custom frequency
 *
 * @param arb - Arbitrary that will be called to generate a non nil value
 * @param constraints - Constraints on the option(since 1.17.0)
 *
 * @remarks Since 0.0.6
 * @public
 */
export declare function option<T, TNil = null>(arb: Arbitrary<T>, constraints?: OptionConstraints<TNil>): Arbitrary<T | TNil>;
//#endregion
//#region src/arbitrary/record.d.ts
type Prettify<T> = { [K in keyof T]: T[K]; } & {};
/**
 * Constraints to be applied on {@link record}
 * @remarks Since 0.0.12
 * @public
 */
type RecordConstraints<T = unknown> = {
  /**
   * List keys that should never be deleted.
   *
   * Remark:
   * You might need to use an explicit typing in case you need to declare symbols as required (not needed when required keys are simple strings).
   * With something like `{ requiredKeys: [mySymbol1, 'a'] as [typeof mySymbol1, 'a'] }` when both `mySymbol1` and `a` are required.
   *
   * @defaultValue Array containing all keys of recordModel
   * @remarks Since 2.11.0
   */
  requiredKeys?: T[];
  /**
   * Do not generate records with null prototype
   * @defaultValue false
   * @remarks Since 3.13.0
   */
  noNullPrototype?: boolean;
};
/**
 * Infer the type of the Arbitrary produced by record
 * given the type of the source arbitrary and constraints to be applied
 *
 * @remarks Since 2.2.0
 * @public
 */
type RecordValue<T, K> = Prettify<Partial<T> & Pick<T, K & keyof T>>;
/**
 * For records following the `recordModel` schema
 *
 * @example
 * ```typescript
 * record({ x: someArbitraryInt, y: someArbitraryInt }, {requiredKeys: []}): Arbitrary<{x?:number,y?:number}>
 * // merge two integer arbitraries to produce a {x, y}, {x}, {y} or {} record
 * ```
 *
 * @param recordModel - Schema of the record
 * @param constraints - Contraints on the generated record
 *
 * @remarks Since 0.0.12
 * @public
 */
declare function record<T, K extends keyof T = keyof T>(model: { [K in keyof T]: Arbitrary<T[K]>; }, constraints?: RecordConstraints<K>): Arbitrary<RecordValue<T, K>>;
//#endregion
//#region src/arbitrary/set.d.ts
/**
 * Constraints to be applied on {@link set}
 * @remarks Since 4.4.0
 * @public
 */
type SetConstraints = {
  /**
   * Lower bound of the generated set size
   * @defaultValue 0
   * @remarks Since 4.4.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated set size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 4.4.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 4.4.0
   */
  size?: SizeForArbitrary;
  /**
   * When receiving a depth identifier, the arbitrary will impact the depth
   * attached to it to avoid going too deep if it already generated lots of items.
   *
   * In other words, if the number of generated values within the collection is large
   * then the generated items will tend to be less deep to avoid creating structures a lot
   * larger than expected.
   *
   * For the moment, the depth is not taken into account to compute the number of items to
   * define for a precise generate call of the set. Just applied onto eligible items.
   *
   * @remarks Since 4.4.0
   */
  depthIdentifier?: DepthIdentifier | string;
};
/**
 * For sets of values coming from `arb`
 *
 * All the values in the set are unique. Comparison of values relies on `SameValueZero`
 * which is the same comparison algorithm used by `Set`.
 *
 * @param arb - Arbitrary used to generate the values inside the set
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 4.4.0
 * @public
 */
export declare function set<T>(arb: Arbitrary<T>, constraints?: SetConstraints): Arbitrary<Set<T>>;
//#endregion
//#region src/arbitrary/infiniteStream.d.ts
/**
 * Constraints to be applied on {@link infiniteStream}
 * @remarks Since 4.3.0
 * @public
 */
interface InfiniteStreamConstraints {
  /**
   * Do not save items emitted by this arbitrary and print count instead.
   * Recommended for very large tests.
   *
   * @defaultValue false
   */
  noHistory?: boolean;
}
/**
 * Produce an infinite stream of values
 *
 * WARNING: By default, infiniteStream remembers all values it has ever
 * generated. This causes unbounded memory growth during large tests.
 * Set noHistory to disable.
 *
 * WARNING: Requires Object.assign
 *
 * @param arb - Arbitrary used to generate the values
 * @param constraints - Constraints to apply when building instances (since 4.3.0)
 *
 * @remarks Since 1.8.0
 * @public
 */
declare function infiniteStream<T>(arb: Arbitrary<T>, constraints?: InfiniteStreamConstraints): Arbitrary<Stream<T>>;
//#endregion
//#region src/arbitrary/base64String.d.ts
/**
 * For base64 strings
 *
 * A base64 string will always have a length multiple of 4 (padded with =)
 *
 * @param constraints - Constraints to apply when building instances (since 2.4.0)
 *
 * @remarks Since 0.0.1
 * @public
 */
declare function base64String(constraints?: StringSharedConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/subarray.d.ts
/**
 * Constraints to be applied on {@link subarray}
 * @remarks Since 2.4.0
 * @public
 */
interface SubarrayConstraints {
  /**
   * Lower bound of the generated subarray size (included)
   * @defaultValue 0
   * @remarks Since 2.4.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated subarray size (included)
   * @defaultValue The length of the original array itself
   * @remarks Since 2.4.0
   */
  maxLength?: number;
}
/**
 * For subarrays of `originalArray` (keeps ordering)
 *
 * @param originalArray - Original array
 * @param constraints - Constraints to apply when building instances (since 2.4.0)
 *
 * @remarks Since 1.5.0
 * @public
 */
export declare function subarray<T>(originalArray: T[], constraints?: SubarrayConstraints): Arbitrary<T[]>;
//#endregion
//#region src/arbitrary/shuffledSubarray.d.ts
/**
 * Constraints to be applied on {@link shuffledSubarray}
 * @remarks Since 2.18.0
 * @public
 */
interface ShuffledSubarrayConstraints {
  /**
   * Lower bound of the generated subarray size (included)
   * @defaultValue 0
   * @remarks Since 2.4.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated subarray size (included)
   * @defaultValue The length of the original array itself
   * @remarks Since 2.4.0
   */
  maxLength?: number;
}
/**
 * For subarrays of `originalArray`
 *
 * @param originalArray - Original array
 * @param constraints - Constraints to apply when building instances (since 2.4.0)
 *
 * @remarks Since 1.5.0
 * @public
 */
export declare function shuffledSubarray<T>(originalArray: T[], constraints?: ShuffledSubarrayConstraints): Arbitrary<T[]>;
//#endregion
//#region src/arbitrary/tuple.d.ts
/**
 * For tuples produced using the provided `arbs`
 *
 * @param arbs - Ordered list of arbitraries
 *
 * @remarks Since 0.0.1
 * @public
 */
export declare function tuple<Ts extends unknown[]>(...arbs: { [K in keyof Ts]: Arbitrary<Ts[K]>; }): Arbitrary<Ts>;
//#endregion
//#region src/arbitrary/ulid.d.ts
/**
 * For ulid
 *
 * According to {@link https://github.com/ulid/spec | ulid spec}
 *
 * No mixed case, only upper case digits (0-9A-Z except for: I,L,O,U)
 *
 * @remarks Since 3.11.0
 * @public
 */
export declare function ulid(): Arbitrary<string>;
//#endregion
//#region src/arbitrary/uuid.d.ts
/**
 * Constraints to be applied on {@link uuid}
 * @remarks Since 3.21.0
 * @public
 */
interface UuidConstraints {
  /**
   * Define accepted versions in the [1-15] according to {@link https://datatracker.ietf.org/doc/html/rfc9562#name-version-field | RFC 9562}
   * @defaultValue [1,2,3,4,5,6,7,8]
   * @remarks Since 3.21.0
   */
  version?: (1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15) | (1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15)[];
}
/**
 * For UUID from v1 to v5
 *
 * According to {@link https://tools.ietf.org/html/rfc4122 | RFC 4122}
 *
 * No mixed case, only lower case digits (0-9a-f)
 *
 * @remarks Since 1.17.0
 * @public
 */
export declare function uuid(constraints?: UuidConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webAuthority.d.ts
/**
 * Constraints to be applied on {@link webAuthority}
 * @remarks Since 1.14.0
 * @public
 */
interface WebAuthorityConstraints {
  /**
   * Enable IPv4 in host
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withIPv4?: boolean;
  /**
   * Enable IPv6 in host
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withIPv6?: boolean;
  /**
   * Enable extended IPv4 format
   * @defaultValue false
   * @remarks Since 1.17.0
   */
  withIPv4Extended?: boolean;
  /**
   * Enable user information prefix
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withUserInfo?: boolean;
  /**
   * Enable port suffix
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withPort?: boolean;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For web authority
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986} - `authority = [ userinfo "@" ] host [ ":" port ]`
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function webAuthority(constraints?: WebAuthorityConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webFragments.d.ts
/**
 * Constraints to be applied on {@link webFragments}
 * @remarks Since 2.22.0
 * @public
 */
interface WebFragmentsConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For fragments of an URI (web included)
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986}
 *
 * eg.: In the url `https://domain/plop?page=1#hello=1&world=2`, `?hello=1&world=2` are query parameters
 *
 * @param constraints - Constraints to apply when building instances (since 2.22.0)
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function webFragments(constraints?: WebFragmentsConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webPath.d.ts
/**
 * Constraints to be applied on {@link webPath}
 * @remarks Since 3.3.0
 * @public
 */
interface WebPathConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 3.3.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For web path
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986} and
 * {@link https://url.spec.whatwg.org/ | WHATWG URL Standard}
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 3.3.0
 * @public
 */
export declare function webPath(constraints?: WebPathConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webQueryParameters.d.ts
/**
 * Constraints to be applied on {@link webQueryParameters}
 * @remarks Since 2.22.0
 * @public
 */
interface WebQueryParametersConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For query parameters of an URI (web included)
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986}
 *
 * eg.: In the url `https://domain/plop/?hello=1&world=2`, `?hello=1&world=2` are query parameters
 *
 * @param constraints - Constraints to apply when building instances (since 2.22.0)
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function webQueryParameters(constraints?: WebQueryParametersConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webSegment.d.ts
/**
 * Constraints to be applied on {@link webSegment}
 * @remarks Since 2.22.0
 * @public
 */
interface WebSegmentConstraints {
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For internal segment of an URI (web included)
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986}
 *
 * eg.: In the url `https://github.com/dubzzz/fast-check/`, `dubzzz` and `fast-check` are segments
 *
 * @param constraints - Constraints to apply when building instances (since 2.22.0)
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function webSegment(constraints?: WebSegmentConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/webUrl.d.ts
/**
 * Constraints to be applied on {@link webUrl}
 * @remarks Since 1.14.0
 * @public
 */
interface WebUrlConstraints {
  /**
   * Enforce specific schemes, eg.: http, https
   * @defaultValue ['http', 'https']
   * @remarks Since 1.14.0
   */
  validSchemes?: string[];
  /**
   * Settings for {@link webAuthority}
   * @defaultValue &#123;&#125;
   * @remarks Since 1.14.0
   */
  authoritySettings?: WebAuthorityConstraints;
  /**
   * Enable query parameters in the generated url
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withQueryParameters?: boolean;
  /**
   * Enable fragments in the generated url
   * @defaultValue false
   * @remarks Since 1.14.0
   */
  withFragments?: boolean;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: Exclude<SizeForArbitrary, "max">;
}
/**
 * For web url
 *
 * According to {@link https://www.ietf.org/rfc/rfc3986.txt | RFC 3986} and
 * {@link https://url.spec.whatwg.org/ | WHATWG URL Standard}
 *
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 1.14.0
 * @public
 */
export declare function webUrl(constraints?: WebUrlConstraints): Arbitrary<string>;
//#endregion
//#region src/check/model/command/ICommand.d.ts
/**
 * Interface that should be implemented in order to define a command
 * @remarks Since 1.5.0
 * @public
 */
interface ICommand<Model extends object, Real, RunResult, CheckAsync extends boolean = false> {
  /**
   * Check if the model is in the right state to apply the command
   *
   * WARNING: does not change the model
   *
   * @param m - Model, simplified or schematic representation of real system
   *
   * @remarks Since 1.5.0
   */
  check(m: Readonly<Model>): CheckAsync extends false ? boolean : Promise<boolean>;
  /**
   * Receive the non-updated model and the real or system under test.
   * Perform the checks post-execution - Throw in case of invalid state.
   * Update the model accordingly
   *
   * @param m - Model, simplified or schematic representation of real system
   * @param r - Sytem under test
   *
   * @remarks Since 1.5.0
   */
  run(m: Model, r: Real): RunResult;
  /**
   * Name of the command
   * @remarks Since 1.5.0
   */
  toString(): string;
}
//#endregion
//#region src/check/model/command/AsyncCommand.d.ts
/**
 * Interface that should be implemented in order to define
 * an asynchronous command
 *
 * @remarks Since 1.5.0
 * @public
 */
interface AsyncCommand<Model extends object, Real, CheckAsync extends boolean = false> extends ICommand<Model, Real, Promise<void>, CheckAsync> {}
//#endregion
//#region src/check/model/command/Command.d.ts
/**
 * Interface that should be implemented in order to define
 * a synchronous command
 *
 * @remarks Since 1.5.0
 * @public
 */
interface Command<Model extends object, Real> extends ICommand<Model, Real, void> {}
//#endregion
//#region src/check/model/commands/CommandsContraints.d.ts
/**
 * Parameters for {@link commands}
 * @remarks Since 2.2.0
 * @public
 */
interface CommandsContraints {
  /**
   * Maximal number of commands to generate per run
   *
   * You probably want to use `size` instead.
   *
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 1.11.0
   */
  maxCommands?: number;
  /**
   * Define how large the generated values (number of commands) should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
  /**
   * Do not show replayPath in the output
   * @defaultValue false
   * @remarks Since 1.11.0
   */
  disableReplayLog?: boolean;
  /**
   * Hint for replay purposes only
   *
   * Should be used in conjonction with `{ seed, path }` of {@link assert}
   *
   * @remarks Since 1.11.0
   */
  replayPath?: string;
}
//#endregion
//#region src/arbitrary/commands.d.ts
/**
 * For arrays of {@link AsyncCommand} to be executed by {@link asyncModelRun}
 *
 * This implementation comes with a shrinker adapted for commands.
 * It should shrink more efficiently than {@link array} for {@link AsyncCommand} arrays.
 *
 * @param commandArbs - Arbitraries responsible to build commands
 * @param constraints - Constraints to be applied when generating the commands (since 1.11.0)
 *
 * @remarks Since 1.5.0
 * @public
 */
declare function commands<Model extends object, Real, CheckAsync extends boolean>(commandArbs: Arbitrary<AsyncCommand<Model, Real, CheckAsync>>[], constraints?: CommandsContraints): Arbitrary<Iterable<AsyncCommand<Model, Real, CheckAsync>>>;
/**
 * For arrays of {@link Command} to be executed by {@link modelRun}
 *
 * This implementation comes with a shrinker adapted for commands.
 * It should shrink more efficiently than {@link array} for {@link Command} arrays.
 *
 * @param commandArbs - Arbitraries responsible to build commands
 * @param constraints - Constraints to be applied when generating the commands (since 1.11.0)
 *
 * @remarks Since 1.5.0
 * @public
 */
declare function commands<Model extends object, Real>(commandArbs: Arbitrary<Command<Model, Real>>[], constraints?: CommandsContraints): Arbitrary<Iterable<Command<Model, Real>>>;
//#endregion
//#region src/arbitrary/_internals/interfaces/Scheduler.d.ts
/**
 * Function responsible to run the passed function and surround it with whatever needed.
 * The name has been inspired from the `act` function coming with React.
 *
 * This wrapper function is not supposed to throw. The received function f will never throw.
 *
 * Wrapping order in the following:
 *
 * - global act defined on `fc.scheduler` wraps wait level one
 * - wait act defined on `s.waitX` wraps local one
 * - local act defined on `s.scheduleX(...)` wraps the trigger function
 *
 * @remarks Since 3.9.0
 * @public
 */
type SchedulerAct = (f: () => Promise<void>) => Promise<void>;
/**
 * Instance able to reschedule the ordering of promises for a given app
 * @remarks Since 1.20.0
 * @public
 */
interface Scheduler<TMetaData = unknown> {
  /**
   * Wrap a new task using the Scheduler
   * @remarks Since 1.20.0
   */
  schedule: <T>(task: Promise<T>, label?: string, metadata?: TMetaData, customAct?: SchedulerAct) => Promise<T>;
  /**
   * Automatically wrap function output using the Scheduler
   * @remarks Since 1.20.0
   */
  scheduleFunction: <TArgs extends any[], T>(asyncFunction: (...args: TArgs) => Promise<T>, customAct?: SchedulerAct) => (...args: TArgs) => Promise<T>;
  /**
   * Schedule a sequence of Promise to be executed sequencially.
   * Items within the sequence might be interleaved by other scheduled operations.
   *
   * Please note that whenever an item from the sequence has started,
   * the scheduler will wait until its end before moving to another scheduled task.
   *
   * A handle is returned by the function in order to monitor the state of the sequence.
   * Sequence will be marked:
   * - done if all the promises have been executed properly
   * - faulty if one of the promises within the sequence throws
   *
   * @remarks Since 1.20.0
   */
  scheduleSequence(sequenceBuilders: SchedulerSequenceItem<TMetaData>[], customAct?: SchedulerAct): {
    done: boolean;
    faulty: boolean;
    task: Promise<{
      done: boolean;
      faulty: boolean;
    }>;
  };
  /**
   * Count of pending scheduled tasks
   * @remarks Since 1.20.0
   */
  count(): number;
  /**
   * Wait one scheduled task to be executed
   * @throws Whenever there is no task scheduled
   * @remarks Since 1.20.0
   * @deprecated Use `waitNext(1)` instead, it comes with a more predictable behavior
   */
  waitOne: (customAct?: SchedulerAct) => Promise<void>;
  /**
   * Wait all scheduled tasks,
   * including the ones that might be created by one of the resolved task
   * @remarks Since 1.20.0
   * @deprecated Use `waitIdle()` instead, it comes with a more predictable behavior awaiting all scheduled and reachable tasks to be completed
   */
  waitAll: (customAct?: SchedulerAct) => Promise<void>;
  /**
   * Wait and schedule exactly `count` scheduled tasks.
   * @remarks Since 4.2.0
   */
  waitNext: (count: number, customAct?: SchedulerAct) => Promise<void>;
  /**
   * Wait until the scheduler becomes idle: all scheduled and reachable tasks have completed.
   *
   * It will include tasks scheduled by other tasks, recursively.
   *
   * Note: Tasks triggered by uncontrolled sources (like `fetch` or external events) cannot be detected
   * or awaited and may lead to incomplete waits.
   *
   * If you want to wait for a precise event to happen you should rather opt for `waitFor` or `waitNext`
   * given they offer you a more granular control on what you are exactly waiting for.
   *
   * @remarks Since 4.2.0
   */
  waitIdle: (customAct?: SchedulerAct) => Promise<void>;
  /**
   * Wait as many scheduled tasks as need to resolve the received Promise
   *
   * Some tests frameworks like `supertest` are not triggering calls to subsequent queries in a synchronous way,
   * some are waiting an explicit call to `then` to trigger them (either synchronously or asynchronously)...
   * As a consequence, none of `waitOne` or `waitAll` cannot wait for them out-of-the-box.
   *
   * This helper is responsible to wait as many scheduled tasks as needed (but the bare minimal) to get
   * `unscheduledTask` resolved. Once resolved it returns its output either success or failure.
   *
   * Be aware that while this helper will wait eveything to be ready for `unscheduledTask` to resolve,
   * having uncontrolled tasks triggering stuff required for `unscheduledTask` might be a source a uncontrollable
   * and not reproducible randomness as those triggers cannot be handled and scheduled by fast-check.
   *
   * @remarks Since 2.24.0
   */
  waitFor: <T>(unscheduledTask: Promise<T>, customAct?: SchedulerAct) => Promise<T>;
  /**
   * Produce an array containing all the scheduled tasks so far with their execution status.
   * If the task has been executed, it includes a string representation of the associated output or error produced by the task if any.
   *
   * Tasks will be returned in the order they get executed by the scheduler.
   *
   * @remarks Since 1.25.0
   */
  report: () => SchedulerReportItem<TMetaData>[];
}
/**
 * Define an item to be passed to `scheduleSequence`
 * @remarks Since 1.20.0
 * @public
 */
type SchedulerSequenceItem<TMetaData = unknown> = {
  /**
   * Builder to start the task
   * @remarks Since 1.20.0
   */
  builder: () => Promise<any>;
  /**
   * Label
   * @remarks Since 1.20.0
   */
  label: string;
  /**
   * Metadata to be attached into logs
   * @remarks Since 1.25.0
   */
  metadata?: TMetaData;
} | (() => Promise<any>);
/**
 * Describe a task for the report produced by the scheduler
 * @remarks Since 1.25.0
 * @public
 */
interface SchedulerReportItem<TMetaData = unknown> {
  /**
   * Execution status for this task
   * - resolved: task released by the scheduler and successful
   * - rejected: task released by the scheduler but with errors
   * - pending:  task still pending in the scheduler, not released yet
   *
   * @remarks Since 1.25.0
   */
  status: "resolved" | "rejected" | "pending";
  /**
   * How was this task scheduled?
   * - promise: schedule
   * - function: scheduleFunction
   * - sequence: scheduleSequence
   *
   * @remarks Since 1.25.0
   */
  schedulingType: "promise" | "function" | "sequence";
  /**
   * Incremental id for the task, first received task has taskId = 1
   * @remarks Since 1.25.0
   */
  taskId: number;
  /**
   * Label of the task
   * @remarks Since 1.25.0
   */
  label: string;
  /**
   * Metadata linked when scheduling the task
   * @remarks Since 1.25.0
   */
  metadata?: TMetaData;
  /**
   * Stringified version of the output or error computed using fc.stringify
   * @remarks Since 1.25.0
   */
  outputValue?: string;
}
//#endregion
//#region src/arbitrary/scheduler.d.ts
/**
 * Constraints to be applied on {@link scheduler}
 * @remarks Since 2.2.0
 * @public
 */
interface SchedulerConstraints {
  /**
   * Ensure that all scheduled tasks will be executed in the right context (for instance it can be the `act` of React)
   * @remarks Since 1.21.0
   */
  act: (f: () => Promise<void>) => Promise<unknown>;
}
/**
 * For scheduler of promises
 * @remarks Since 1.20.0
 * @public
 */
export declare function scheduler<TMetaData = unknown>(constraints?: SchedulerConstraints): Arbitrary<Scheduler<TMetaData>>;
/**
 * For custom scheduler with predefined resolution order
 *
 * Ordering is defined by using a template string like the one generated in case of failure of a {@link scheduler}
 *
 * It may be something like:
 *
 * @example
 * ```typescript
 * fc.schedulerFor()`
 *   -> [task\${2}] promise pending
 *   -> [task\${3}] promise pending
 *   -> [task\${1}] promise pending
 * `
 * ```
 *
 * Or more generally:
 * ```typescript
 * fc.schedulerFor()`
 *   This scheduler will resolve task ${2} first
 *   followed by ${3} and only then task ${1}
 * `
 * ```
 *
 * WARNING:
 * Custom scheduler will
 * neither check that all the referred promises have been scheduled
 * nor that they resolved with the same status and value.
 *
 *
 * WARNING:
 * If one the promises is wrongly defined it will fail - for instance asking to resolve 5 while 5 does not exist.
 *
 * @remarks Since 1.25.0
 * @public
 */
declare function schedulerFor<TMetaData = unknown>(constraints?: SchedulerConstraints): (_strs: TemplateStringsArray, ...ordering: number[]) => Scheduler<TMetaData>;
/**
 * For custom scheduler with predefined resolution order
 *
 * WARNING:
 * Custom scheduler will not check that all the referred promises have been scheduled.
 *
 *
 * WARNING:
 * If one the promises is wrongly defined it will fail - for instance asking to resolve 5 while 5 does not exist.
 *
 * @param customOrdering - Array defining in which order the promises will be resolved.
 * Id of the promises start at 1. 1 means first scheduled promise, 2 second scheduled promise and so on.
 *
 * @remarks Since 1.25.0
 * @public
 */
declare function schedulerFor<TMetaData = unknown>(customOrdering: number[], constraints?: SchedulerConstraints): Scheduler<TMetaData>;
//#endregion
//#region src/check/model/ModelRunner.d.ts
/**
 * Synchronous definition of model and real
 * @remarks Since 2.2.0
 * @public
 */
type ModelRunSetup<Model, Real> = () => {
  model: Model;
  real: Real;
};
/**
 * Asynchronous definition of model and real
 * @remarks Since 2.2.0
 * @public
 */
type ModelRunAsyncSetup<Model, Real> = () => Promise<{
  model: Model;
  real: Real;
}>;
/**
 * Run synchronous commands over a `Model` and the `Real` system
 *
 * Throw in case of inconsistency
 *
 * @param s - Initial state provider
 * @param cmds - Synchronous commands to be executed
 *
 * @remarks Since 1.5.0
 * @public
 */
export declare function modelRun<Model extends object, Real, InitialModel extends Model>(s: ModelRunSetup<InitialModel, Real>, cmds: Iterable<Command<Model, Real>>): void;
/**
 * Run asynchronous commands over a `Model` and the `Real` system
 *
 * Throw in case of inconsistency
 *
 * @param s - Initial state provider
 * @param cmds - Asynchronous commands to be executed
 *
 * @remarks Since 1.5.0
 * @public
 */
export declare function asyncModelRun<Model extends object, Real, CheckAsync extends boolean, InitialModel extends Model>(s: ModelRunSetup<InitialModel, Real> | ModelRunAsyncSetup<InitialModel, Real>, cmds: Iterable<AsyncCommand<Model, Real, CheckAsync>>): Promise<void>;
/**
 * Run asynchronous and scheduled commands over a `Model` and the `Real` system
 *
 * Throw in case of inconsistency
 *
 * @param scheduler - Scheduler
 * @param s - Initial state provider
 * @param cmds - Asynchronous commands to be executed
 *
 * @remarks Since 1.24.0
 * @public
 */
export declare function scheduledModelRun<Model extends object, Real, CheckAsync extends boolean, InitialModel extends Model>(scheduler: Scheduler, s: ModelRunSetup<InitialModel, Real> | ModelRunAsyncSetup<InitialModel, Real>, cmds: Iterable<AsyncCommand<Model, Real, CheckAsync>>): Promise<void>;
//#endregion
//#region src/check/symbols.d.ts
/**
 * Generated instances having a method [cloneMethod]
 * will be automatically cloned whenever necessary
 *
 * This is pretty useful for statefull generated values.
 * For instance, whenever you use a Stream you directly impact it.
 * Implementing [cloneMethod] on the generated Stream would force
 * the framework to clone it whenever it has to re-use it
 * (mainly required for chrinking process)
 *
 * @remarks Since 1.8.0
 * @public
 */
export declare const cloneMethod: unique symbol;
/**
 * Object instance that should be cloned from one generation/shrink to another
 * @remarks Since 2.15.0
 * @public
 */
interface WithCloneMethod<T> {
  [cloneMethod]: () => T;
}
/**
 * Check if an instance has to be clone
 * @remarks Since 2.15.0
 * @public
 */
export declare function hasCloneMethod<T>(instance: T | WithCloneMethod<T>): instance is WithCloneMethod<T>;
/**
 * Clone an instance if needed
 * @remarks Since 2.15.0
 * @public
 */
export declare function cloneIfNeeded<T>(instance: T): T;
//#endregion
//#region src/utils/hash.d.ts
/**
 * CRC-32 based hash function
 *
 * Used internally by fast-check in {@link func}, {@link compareFunc} or even {@link compareBooleanFunc}.
 *
 * @param repr - String value to be hashed
 *
 * @remarks Since 2.1.0
 * @public
 */
export declare function hash(repr: string): number;
//#endregion
//#region src/utils/stringify.d.ts
/**
 * Use this symbol to define a custom serializer for your instances.
 * Serializer must be a function returning a string (see {@link WithToStringMethod}).
 *
 * @remarks Since 2.17.0
 * @public
 */
export declare const toStringMethod: unique symbol;
/**
 * Interface to implement for {@link toStringMethod}
 *
 * @remarks Since 2.17.0
 * @public
 */
type WithToStringMethod = {
  [toStringMethod]: () => string;
};
/**
 * Check if an instance implements {@link WithToStringMethod}
 *
 * @remarks Since 2.17.0
 * @public
 */
export declare function hasToStringMethod<T>(instance: T): instance is T & WithToStringMethod;
/**
 * Use this symbol to define a custom serializer for your instances.
 * Serializer must be a function returning a promise of string (see {@link WithAsyncToStringMethod}).
 *
 * Please note that:
 * 1. It will only be useful for asynchronous properties.
 * 2. It has to return barely instantly.
 *
 * @remarks Since 2.17.0
 * @public
 */
export declare const asyncToStringMethod: unique symbol;
/**
 * Interface to implement for {@link asyncToStringMethod}
 *
 * @remarks Since 2.17.0
 * @public
 */
type WithAsyncToStringMethod = {
  [asyncToStringMethod]: () => Promise<string>;
};
/**
 * Check if an instance implements {@link WithAsyncToStringMethod}
 *
 * @remarks Since 2.17.0
 * @public
 */
export declare function hasAsyncToStringMethod<T>(instance: T): instance is T & WithAsyncToStringMethod;
/**
 * Convert any value to its fast-check string representation
 *
 * @param value - Value to be converted into a string
 *
 * @remarks Since 1.15.0
 * @public
 */
export declare function stringify<Ts>(value: Ts): string;
/**
 * Convert any value to its fast-check string representation
 *
 * This asynchronous version is also able to dig into the status of Promise
 *
 * @param value - Value to be converted into a string
 *
 * @remarks Since 2.17.0
 * @public
 */
export declare function asyncStringify<Ts>(value: Ts): Promise<string>;
//#endregion
//#region src/check/runner/utils/RunDetailsFormatter.d.ts
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 1.25.0
 * @public
 */
declare function defaultReportMessage<Ts>(out: RunDetails<Ts> & {
  failed: false;
}): undefined;
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 1.25.0
 * @public
 */
declare function defaultReportMessage<Ts>(out: RunDetails<Ts> & {
  failed: true;
}): string;
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 1.25.0
 * @public
 */
declare function defaultReportMessage<Ts>(out: RunDetails<Ts>): string | undefined;
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 2.17.0
 * @public
 */
declare function asyncDefaultReportMessage<Ts>(out: RunDetails<Ts> & {
  failed: false;
}): Promise<undefined>;
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 2.17.0
 * @public
 */
declare function asyncDefaultReportMessage<Ts>(out: RunDetails<Ts> & {
  failed: true;
}): Promise<string>;
/**
 * Format output of {@link check} using the default error reporting of {@link assert}
 *
 * Produce a string containing the formated error in case of failed run,
 * undefined otherwise.
 *
 * @remarks Since 2.17.0
 * @public
 */
declare function asyncDefaultReportMessage<Ts>(out: RunDetails<Ts>): Promise<string | undefined>;
//#endregion
//#region src/arbitrary/_internals/builders/TypedIntArrayArbitraryBuilder.d.ts
/**
 * Constraints to be applied on typed arrays for integer values
 * @remarks Since 2.9.0
 * @public
 */
type IntArrayConstraints = {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 2.9.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.9.0
   */
  maxLength?: number;
  /**
   * Lower bound for the generated int (included)
   * @defaultValue smallest possible value for this type
   * @remarks Since 2.9.0
   */
  min?: number;
  /**
   * Upper bound for the generated int (included)
   * @defaultValue highest possible value for this type
   * @remarks Since 2.9.0
   */
  max?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
};
/**
 * Constraints to be applied on typed arrays for big int values
 * @remarks Since 3.0.0
 * @public
 */
type BigIntArrayConstraints = {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 3.0.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 3.0.0
   */
  maxLength?: number;
  /**
   * Lower bound for the generated int (included)
   * @defaultValue smallest possible value for this type
   * @remarks Since 3.0.0
   */
  min?: bigint;
  /**
   * Upper bound for the generated int (included)
   * @defaultValue highest possible value for this type
   * @remarks Since 3.0.0
   */
  max?: bigint;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 3.0.0
   */
  size?: SizeForArbitrary;
};
//#endregion
//#region src/arbitrary/int8Array.d.ts
/**
 * For Int8Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function int8Array(constraints?: IntArrayConstraints): Arbitrary<Int8Array>;
//#endregion
//#region src/arbitrary/int16Array.d.ts
/**
 * For Int16Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function int16Array(constraints?: IntArrayConstraints): Arbitrary<Int16Array>;
//#endregion
//#region src/arbitrary/int32Array.d.ts
/**
 * For Int32Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function int32Array(constraints?: IntArrayConstraints): Arbitrary<Int32Array>;
//#endregion
//#region src/arbitrary/uint8Array.d.ts
/**
 * For Uint8Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function uint8Array(constraints?: IntArrayConstraints): Arbitrary<Uint8Array>;
//#endregion
//#region src/arbitrary/uint8ClampedArray.d.ts
/**
 * For Uint8ClampedArray
 * @remarks Since 2.9.0
 * @public
 */
export declare function uint8ClampedArray(constraints?: IntArrayConstraints): Arbitrary<Uint8ClampedArray>;
//#endregion
//#region src/arbitrary/uint16Array.d.ts
/**
 * For Uint16Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function uint16Array(constraints?: IntArrayConstraints): Arbitrary<Uint16Array>;
//#endregion
//#region src/arbitrary/uint32Array.d.ts
/**
 * For Uint32Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function uint32Array(constraints?: IntArrayConstraints): Arbitrary<Uint32Array>;
//#endregion
//#region src/arbitrary/float32Array.d.ts
/**
 * Constraints to be applied on {@link float32Array}
 * @remarks Since 2.9.0
 * @public
 */
type Float32ArrayConstraints = {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 2.9.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.9.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
} & FloatConstraints;
/**
 * For Float32Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function float32Array(constraints?: Float32ArrayConstraints): Arbitrary<Float32Array>;
//#endregion
//#region src/arbitrary/float64Array.d.ts
/**
 * Constraints to be applied on {@link float64Array}
 * @remarks Since 2.9.0
 * @public
 */
type Float64ArrayConstraints = {
  /**
   * Lower bound of the generated array size
   * @defaultValue 0
   * @remarks Since 2.9.0
   */
  minLength?: number;
  /**
   * Upper bound of the generated array size
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.9.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
} & DoubleConstraints;
/**
 * For Float64Array
 * @remarks Since 2.9.0
 * @public
 */
export declare function float64Array(constraints?: Float64ArrayConstraints): Arbitrary<Float64Array>;
//#endregion
//#region src/arbitrary/sparseArray.d.ts
/**
 * Constraints to be applied on {@link sparseArray}
 * @remarks Since 2.13.0
 * @public
 */
interface SparseArrayConstraints {
  /**
   * Upper bound of the generated array size (maximal size: 4294967295)
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.13.0
   */
  maxLength?: number;
  /**
   * Lower bound of the number of non-hole elements
   * @defaultValue 0
   * @remarks Since 2.13.0
   */
  minNumElements?: number;
  /**
   * Upper bound of the number of non-hole elements
   * @defaultValue 0x7fffffff — _defaulting seen as "max non specified" when `defaultSizeToMaxWhenMaxSpecified=true`_
   * @remarks Since 2.13.0
   */
  maxNumElements?: number;
  /**
   * When enabled, all generated arrays will either be the empty array or end by a non-hole
   * @defaultValue false
   * @remarks Since 2.13.0
   */
  noTrailingHole?: boolean;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 2.22.0
   */
  size?: SizeForArbitrary;
  /**
   * When receiving a depth identifier, the arbitrary will impact the depth
   * attached to it to avoid going too deep if it already generated lots of items.
   *
   * In other words, if the number of generated values within the collection is large
   * then the generated items will tend to be less deep to avoid creating structures a lot
   * larger than expected.
   *
   * For the moment, the depth is not taken into account to compute the number of items to
   * define for a precise generate call of the array. Just applied onto eligible items.
   *
   * @remarks Since 2.25.0
   */
  depthIdentifier?: DepthIdentifier | string;
}
/**
 * For sparse arrays of values coming from `arb`
 * @param arb - Arbitrary used to generate the values inside the sparse array
 * @param constraints - Constraints to apply when building instances
 * @remarks Since 2.13.0
 * @public
 */
export declare function sparseArray<T>(arb: Arbitrary<T>, constraints?: SparseArrayConstraints): Arbitrary<T[]>;
//#endregion
//#region src/arbitrary/bigInt64Array.d.ts
/**
 * For BigInt64Array
 * @remarks Since 3.0.0
 * @public
 */
export declare function bigInt64Array(constraints?: BigIntArrayConstraints): Arbitrary<BigInt64Array>;
//#endregion
//#region src/arbitrary/bigUint64Array.d.ts
/**
 * For BigUint64Array
 * @remarks Since 3.0.0
 * @public
 */
export declare function bigUint64Array(constraints?: BigIntArrayConstraints): Arbitrary<BigUint64Array>;
//#endregion
//#region src/arbitrary/stringMatching.d.ts
/**
 * Constraints to be applied on the arbitrary {@link stringMatching}
 * @remarks Since 3.10.0
 * @public
 */
type StringMatchingConstraints = {
  /**
   * Upper bound of the generated string length (included)
   * @defaultValue 0x7fffffff
   * @remarks Since 4.6.0
   */
  maxLength?: number;
  /**
   * Define how large the generated values should be (at max)
   * @remarks Since 3.10.0
   */
  size?: SizeForArbitrary;
};
/**
 * For strings matching the provided regex
 *
 * @param regex - Arbitrary able to generate random strings (possibly multiple characters)
 * @param constraints - Constraints to apply when building instances
 *
 * @remarks Since 3.10.0
 * @public
 */
export declare function stringMatching(regex: RegExp, constraints?: StringMatchingConstraints): Arbitrary<string>;
//#endregion
//#region src/arbitrary/noShrink.d.ts
/**
 * Build an arbitrary without shrinking capabilities.
 *
 * NOTE:
 * In most cases, users should avoid disabling shrinking capabilities.
 * If the concern is the shrinking process taking too long or being unnecessary in CI environments,
 * consider using alternatives like `endOnFailure` or `interruptAfterTimeLimit` instead.
 *
 * @param arb - The original arbitrary used for generating values. This arbitrary remains unchanged, but its shrinking capabilities will not be included in the new arbitrary.
 *
 * @remarks Since 3.20.0
 * @public
 */
export declare function noShrink<T>(arb: Arbitrary<T>): Arbitrary<T>;
//#endregion
//#region src/arbitrary/noBias.d.ts
/**
 * Build an arbitrary without any bias.
 *
 * The produced instance wraps the source one and ensures the bias factor will always be passed to undefined meaning bias will be deactivated.
 * All the rest stays unchanged.
 *
 * @param arb - The original arbitrary used for generating values. This arbitrary remains unchanged.
 *
 * @remarks Since 3.20.0
 * @public
 */
export declare function noBias<T>(arb: Arbitrary<T>): Arbitrary<T>;
//#endregion
//#region src/arbitrary/limitShrink.d.ts
/**
 * Create another Arbitrary with a limited (or capped) number of shrink values
 *
 * @example
 * ```typescript
 * const dataGenerator: Arbitrary<string> = ...;
 * const limitedShrinkableDataGenerator: Arbitrary<string> = fc.limitShrink(dataGenerator, 10);
 * // up to 10 shrunk values could be extracted from the resulting arbitrary
 * ```
 *
 * NOTE: Although limiting the shrinking capabilities can speed up your CI when failures occur, we do not recommend this approach.
 * Instead, if you want to reduce the shrinking time for automated jobs or local runs, consider using `endOnFailure` or `interruptAfterTimeLimit`.
 *
 * @param arbitrary - Instance of arbitrary responsible to generate and shrink values
 * @param maxShrinks - Maximal number of shrunk values that can be pulled from the resulting arbitrary
 *
 * @returns Create another arbitrary with limited number of shrink values
 * @remarks Since 3.20.0
 * @public
 */
export declare function limitShrink<T>(arbitrary: Arbitrary<T>, maxShrinks: number): Arbitrary<T>;
//#endregion
//#region src/check/runner/configuration/GlobalPlugins.d.ts
/**
 * Install a plugin to be used by all the runners
 * Installed plugins come before the ones passed via the `plugins` option of the run.
 *
 * In other words, they are the outermost ones: they are entered first when running the predicate.
 * Think of: `outer(inner(predicate))`.
 *
 * @example
 * ```typescript
 * fc.installGlobalPlugin(myPlugin());
 * //...
 * fc.assert(myProp, { plugins: [myOtherPlugin()] })
 * // equivalent to { plugins: [myPlugin(), myOtherPlugin()] }
 * // myPlugin will wrap myOtherPlugin, itself wrapping the default behavior
 * ```
 *
 * @param plugin - Plugin to be installed globally
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function installGlobalPlugin(plugin: Plugin<unknown>): void;
//#endregion
//#region src/check/plugin/LifeCyclePlugins.d.ts
type TeardownFunction = () => Promise<void> | void;
type AfterEachHook = () => Promise<void> | void;
type BeforeEachHook = () => Promise<void | TeardownFunction> | void | TeardownFunction;
/**
 * Register a callback to be called before each run of your predicate.
 * If the function returns a promise, we wait until the promise resolves before running anything else.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.property(..., (...) => {...}),
 *   { plugins: [fc.beforeEach(() => {...})] }
 * )
 * ```
 *
 * @param fn - Hook to be executed before each execution of the predicate
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function beforeEach(fn: BeforeEachHook): Plugin<unknown>;
/**
 * Register a callback to be called after each run of your predicate.
 * If the function returns a promise, we wait until the promise resolves before running anything else.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.property(..., (...) => {...}),
 *   { plugins: [fc.afterEach(() => {...})] }
 * )
 * ```
 *
 * @param fn - Hook to be executed after each execution of the predicate
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function afterEach(fn: AfterEachHook): Plugin<unknown>;
//#endregion
//#region src/check/plugin/UnbiasedPlugin.d.ts
/**
 * Forces values passed to the predicate to be generated without bias.
 * By default, arbitraries tasked to generate biased values.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.property(..., (...) => {...}),
 *   { plugins: [fc.unbiased()] }
 * )
 * ```
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function unbiased(): Plugin<unknown>;
//#endregion
//#region src/check/plugin/EqualValuesPlugins.d.ts
/**
 * Never execute the predicate twice on the same value and replay the outcome of the first execution instead.
 * Discarded runs still count as runs.
 *
 * Close to {@link skipEqualValues} except we replay the output of the first passing, meaning the replay counts as a run.
 *
 * WARNING: Detecting equal values is based on stringifying them. It may result in false positives and false negatives.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.property(..., (...) => {...}),
 *   { plugins: [fc.ignoreEqualValues()] }
 * )
 * ```
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function ignoreEqualValues(): Plugin<unknown>;
/**
 * Never execute the predicate twice on the same value.
 *
 * A duplicated run whose first execution succeeded is marked as skipped instead of successful.
 * If too many runs get skipped the run will be marked as failed.
 *
 * Close to {@link ignoreEqualValues} except we skip runs having the same value.
 *
 * WARNING: Detecting equal values is based on stringifying them. It may result in false positives and false negatives.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.property(..., (...) => {...}),
 *   { plugins: [fc.skipEqualValues()] }
 * )
 * ```
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function skipEqualValues(): Plugin<unknown>;
//#endregion
//#region src/check/plugin/InterruptAfterTimeLimitPlugin.d.ts
/**
 * Options for {@link interruptAfterTimeLimit}
 * @remarks Since 4.10.0
 * @public
 */
type InterruptAfterTimeLimitOptions = {
  /**
   * Whether an interruption triggered by this plugin should be reported as a failure.
   * When set to `true`, a property interrupted before reaching `numRuns` is reported as a failure.
   *
   * @defaultValue `false`
   * @remarks Since 4.10.0
   */
  failOnInterrupt?: boolean;
};
/**
 * Interrupt test execution after a given time limit.
 *
 * NOTE: Useful to avoid having too long running processes in your CI while preserving replay capabilities if needed.
 *
 * WARNING: A test interrupted before any failure counts as a success, even if it did not
 * reach `numRuns` runs, unless `failOnInterrupt` is set to `true`.
 *
 * As predicates cannot be stopped, the underlying execution keeps running but its outcome gets ignored.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.asyncProperty(..., async (...) => {...}),
 *   { plugins: [fc.interruptAfterTimeLimit(1000)] }
 * )
 * ```
 *
 * @param timeLimitMs - Delay in milliseconds after which runs gets interrupted
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function interruptAfterTimeLimit(timeLimitMs: number, options?: InterruptAfterTimeLimitOptions): Plugin<unknown>;
//#endregion
//#region src/check/plugin/TimeoutPlugin.d.ts
/**
 * Mark the execution of a predicate as failed if it exceeds `timeMs` milliseconds to complete.
 *
 * WARNING: It cannot stop a running predicate.
 * It mainly returns earlier so the test runner can move forward.
 *
 * NOTE: It has no effect on a synchronously running predicate.
 *
 * @example
 * ```ts
 * fc.assert(
 *   fc.asyncProperty(..., async (...) => {...}),
 *   { plugins: [fc.timeout(1000)] }
 * )
 * ```
 *
 * @param timeMs - Maximal number of milliseconds granted to an execution of the predicate
 *
 * @remarks Since 4.10.0
 * @public
 */
export declare function timeout(timeMs: number): Plugin<unknown>;
/** @public */ declare namespace fc {
  export { Arbitrary, ArrayConstraints, AsyncCommand, AsyncPropertyHookFunction, BigIntArrayConstraints, BigIntConstraints, CloneValue, Command, CommandsContraints, ContextValue, DateConstraints, DepthContext, DepthIdentifier, DepthSize, DictionaryConstraints, DomainConstraints, DoubleConstraints, EmailAddressConstraints, Arbitraries as EntityGraphArbitraries, EntityGraphConstraints, EntityGraphContraints, EntityRelations as EntityGraphRelations, EntityGraphValue, ExecutionStatus, ExecutionTree, FalsyContraints, FalsyValue, Float32ArrayConstraints, Float64ArrayConstraints, FloatConstraints, GeneratorValue, GlobalAsyncPropertyHookFunction, GlobalParameters, GlobalPropertyHookFunction, IAsyncProperty, IAsyncPropertyWithHooks, ICommand, IProperty, IPropertyWithHooks, IRawProperty, IntArrayConstraints, IntegerConstraints, InterruptAfterTimeLimitOptions, JsonSharedConstraints, JsonValue, LetrecLooselyTypedBuilder, LetrecLooselyTypedTie, LetrecTypedBuilder, LetrecTypedTie, LetrecValue, LoremConstraints, MapConstraints, MaybeWeightedArbitrary, Memo, MixedCaseConstraints, ModelRunAsyncSetup, ModelRunSetup, NatConstraints, ObjectConstraints, OneOfConstraints, OneOfValue, OptionConstraints, Parameters, Plugin, PluginInstance, PluginStore, PreconditionFailure, PropertyFailure, PropertyHookFunction, Random, RandomGenerator, RandomType, RecordConstraints, RecordValue, RunDetails, RunDetailsCommon, RunDetailsFailureInterrupted, RunDetailsFailureProperty, RunDetailsFailureTooManySkips, RunDetailsSuccess, Scheduler, SchedulerAct, SchedulerConstraints, SchedulerReportItem, SchedulerSequenceItem, SetConstraints, ShuffledSubarrayConstraints, Size, SizeForArbitrary, SparseArrayConstraints, Stream, StringConstraints, StringMatchingConstraints, StringSharedConstraints, SubarrayConstraints, UniqueArrayConstraints, UniqueArrayConstraintsCustomCompare, UniqueArrayConstraintsCustomCompareSelect, UniqueArrayConstraintsRecommended, UniqueArraySharedConstraints, UuidConstraints, Value, VerbosityLevel, WebAuthorityConstraints, WebFragmentsConstraints, WebPathConstraints, WebQueryParametersConstraints, WebSegmentConstraints, WebUrlConstraints, WeightedArbitrary, WithAsyncToStringMethod, WithCloneMethod, WithToStringMethod, __commitHash, __type, __version, afterEach, anything, array, assert, asyncDefaultReportMessage, asyncModelRun, asyncProperty, asyncStringify, asyncToStringMethod, base64String, beforeEach, bigInt, bigInt64Array, bigUint64Array, boolean, chainUntil, check, clone, cloneIfNeeded, cloneMethod, commands, compareBooleanFunc, compareFunc, configureGlobal, constant, constantFrom, context, createDepthIdentifier, date, defaultReportMessage, dictionary, domain, double, emailAddress, entityGraph, falsy, float, float32Array, float64Array, func, gen, getDepthContextFor, hasAsyncToStringMethod, hasCloneMethod, hasToStringMethod, hash, ignoreEqualValues, infiniteStream, installGlobalPlugin, int16Array, int32Array, int8Array, integer, interruptAfterTimeLimit, ipV4, ipV4Extended, ipV6, json, jsonValue, letrec, limitShrink, lorem, map, mapToConstant, maxSafeInteger, maxSafeNat, memo, mixedCase, modelRun, nat, noBias, noShrink, object, oneof, option, pre, property, readConfigureGlobal, record, resetConfigureGlobal, sample, scheduledModelRun, scheduler, schedulerFor, set, shuffledSubarray, skipEqualValues, sparseArray, statistics, stream, string, stringMatching, stringify, subarray, timeout, toStringMethod, tuple, uint16Array, uint32Array, uint8Array, uint8ClampedArray, ulid, unbiased, uniqueArray, uuid, webAuthority, webFragments, webPath, webQueryParameters, webSegment, webUrl };
}
/**
 * Type of module (commonjs or module)
 * @remarks Since 1.22.0
 * @public
 */
declare const __type: string;
/**
 * Version of fast-check used by your project (eg.: "4.10.2")
 * @remarks Since 1.22.0
 * @public
 */
declare const __version: string;
/**
 * Commit hash of the current code (eg.: "c77afa8277a67250d798c52e61343b8ed5fd268b")
 * @remarks Since 2.7.0
 * @public
 */
declare const __commitHash: string;
//#endregion
export { type ArrayConstraints, type AsyncCommand, type AsyncPropertyHookFunction, type BigIntArrayConstraints, type BigIntConstraints, type CloneValue, type Command, type CommandsContraints, type ContextValue, type DateConstraints, type DepthContext, type DepthIdentifier, type DepthSize, type DictionaryConstraints, type DomainConstraints, type DoubleConstraints, type EmailAddressConstraints, type Arbitraries as EntityGraphArbitraries, type EntityGraphConstraints, type EntityGraphContraints, type EntityRelations as EntityGraphRelations, type EntityGraphValue, type ExecutionTree, type FalsyContraints, type FalsyValue, type Float32ArrayConstraints, type Float64ArrayConstraints, type FloatConstraints, type GeneratorValue, type GlobalAsyncPropertyHookFunction, type GlobalParameters, type GlobalPropertyHookFunction, type IAsyncProperty, type IAsyncPropertyWithHooks, type ICommand, type IProperty, type IPropertyWithHooks, type IRawProperty, type IntArrayConstraints, type IntegerConstraints, type InterruptAfterTimeLimitOptions, type JsonSharedConstraints, type JsonValue, type LetrecLooselyTypedBuilder, type LetrecLooselyTypedTie, type LetrecTypedBuilder, type LetrecTypedTie, type LetrecValue, type LoremConstraints, type MapConstraints, type MaybeWeightedArbitrary, type Memo, type MixedCaseConstraints, type ModelRunAsyncSetup, type ModelRunSetup, type NatConstraints, type ObjectConstraints, type OneOfConstraints, type OneOfValue, type OptionConstraints, type Parameters, type Plugin, type PluginInstance, type PluginStore, type PropertyFailure, type PropertyHookFunction, type RandomGenerator, type RandomType, type RecordConstraints, type RecordValue, type RunDetails, type RunDetailsCommon, type RunDetailsFailureInterrupted, type RunDetailsFailureProperty, type RunDetailsFailureTooManySkips, type RunDetailsSuccess, type Scheduler, type SchedulerAct, type SchedulerConstraints, type SchedulerReportItem, type SchedulerSequenceItem, type SetConstraints, type ShuffledSubarrayConstraints, type Size, type SizeForArbitrary, type SparseArrayConstraints, type StringConstraints, type StringMatchingConstraints, type StringSharedConstraints, type SubarrayConstraints, type UniqueArrayConstraints, type UniqueArrayConstraintsCustomCompare, type UniqueArrayConstraintsCustomCompareSelect, type UniqueArrayConstraintsRecommended, type UniqueArraySharedConstraints, type UuidConstraints, type WebAuthorityConstraints, type WebFragmentsConstraints, type WebPathConstraints, type WebQueryParametersConstraints, type WebSegmentConstraints, type WebUrlConstraints, type WeightedArbitrary, type WithAsyncToStringMethod, type WithCloneMethod, type WithToStringMethod, __commitHash, __type, __version, anything, array, assert, asyncDefaultReportMessage, asyncProperty, base64String, bigInt, boolean, check, clone, commands, constantFrom, fc as default, defaultReportMessage, infiniteStream, nat, object, oneof, property, record, sample, schedulerFor, statistics };