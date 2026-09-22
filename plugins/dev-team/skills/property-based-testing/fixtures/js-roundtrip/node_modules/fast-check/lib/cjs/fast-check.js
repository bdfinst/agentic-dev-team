Object.defineProperties(exports, {
	__esModule: { value: true },
	[Symbol.toStringTag]: { value: "Module" }
});
//#region \0rolldown/runtime.js
var __defProp = Object.defineProperty;
var __exportAll = (all, no_symbols) => {
	let target = {};
	for (var name in all) __defProp(target, name, {
		get: all[name],
		enumerable: true
	});
	if (!no_symbols) __defProp(target, Symbol.toStringTag, { value: "Module" });
	return target;
};
//#endregion
let pure_rand_generator_congruential32 = require("pure-rand/generator/congruential32");
let pure_rand_generator_mersenne = require("pure-rand/generator/mersenne");
let pure_rand_generator_xorshift128plus = require("pure-rand/generator/xorshift128plus");
let pure_rand_generator_xoroshiro128plus = require("pure-rand/generator/xoroshiro128plus");
let pure_rand_utils_skipN = require("pure-rand/utils/skipN");
let pure_rand_distribution_uniformBigInt = require("pure-rand/distribution/uniformBigInt");
let pure_rand_distribution_uniformInt = require("pure-rand/distribution/uniformInt");
//#region src/check/precondition/PreconditionFailure.ts
/** @internal */
const SharedFootPrint = Symbol.for("fast-check/PreconditionFailure");
/**
* Error type produced whenever a precondition fails
* @remarks Since 2.2.0
* @public
*/
var PreconditionFailure = class extends Error {
	constructor(interruptExecution = false) {
		super();
		this.interruptExecution = interruptExecution;
		this.footprint = SharedFootPrint;
	}
	static isFailure(err) {
		return err !== null && err !== void 0 && err.footprint === SharedFootPrint;
	}
};
//#endregion
//#region src/check/precondition/Pre.ts
/**
* Add pre-condition checks inside a property execution
* @param expectTruthy - cancel the run whenever this value is falsy
* @remarks Since 1.3.0
* @public
*/
function pre(expectTruthy) {
	if (!expectTruthy) throw new PreconditionFailure();
}
//#endregion
//#region src/stream/StreamHelpers.ts
var Nil = class {
	[Symbol.iterator]() {
		return this;
	}
	next(value) {
		return {
			value,
			done: true
		};
	}
};
/** @internal */
const nil = new Nil();
/** @internal */
function nilHelper() {
	return nil;
}
/** @internal */
function* mapHelper(g, f) {
	for (const v of g) yield f(v);
}
/** @internal */
function* flatMapHelper(g, f) {
	for (const v of g) yield* f(v);
}
/** @internal */
function* filterHelper(g, f) {
	for (const v of g) if (f(v)) yield v;
}
/** @internal */
function* takeNHelper(g, n) {
	for (let i = 0; i < n; ++i) {
		const cur = g.next();
		if (cur.done) break;
		yield cur.value;
	}
}
/** @internal */
function* takeWhileHelper(g, f) {
	let cur = g.next();
	while (!cur.done && f(cur.value)) {
		yield cur.value;
		cur = g.next();
	}
}
/** @internal */
function* joinHelper(g, others) {
	for (let cur = g.next(); !cur.done; cur = g.next()) yield cur.value;
	for (const s of others) for (let cur = s.next(); !cur.done; cur = s.next()) yield cur.value;
}
//#endregion
//#region src/stream/Stream.ts
const safeSymbolIterator$1 = Symbol.iterator;
/**
* Wrapper around `IterableIterator` interface
* offering a set of helpers to deal with iterations in a simple way
*
* @remarks Since 0.0.7
* @public
*/
var Stream = class Stream {
	/**
	* Create an empty stream of T
	* @remarks Since 0.0.1
	*/
	static nil() {
		return new Stream(nilHelper());
	}
	/**
	* Create a stream of T from a variable number of elements
	*
	* @param elements - Elements used to create the Stream
	* @remarks Since 2.12.0
	*/
	static of(...elements) {
		return new Stream(elements[safeSymbolIterator$1]());
	}
	/**
	* Create a Stream based on `g`
	* @param g - Underlying data of the Stream
	*/
	constructor(g) {
		this.g = g;
	}
	next() {
		return this.g.next();
	}
	[Symbol.iterator]() {
		return this.g;
	}
	/**
	* Map all elements of the Stream using `f`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Mapper function
	* @remarks Since 0.0.1
	*/
	map(f) {
		return new Stream(mapHelper(this.g, f));
	}
	/**
	* Flat map all elements of the Stream using `f`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Mapper function
	* @remarks Since 0.0.1
	*/
	flatMap(f) {
		return new Stream(flatMapHelper(this.g, f));
	}
	/**
	* Drop elements from the Stream while `f(element) === true`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Drop condition
	* @remarks Since 0.0.1
	*/
	dropWhile(f) {
		let foundEligible = false;
		function* helper(v) {
			if (foundEligible || !f(v)) {
				foundEligible = true;
				yield v;
			}
		}
		return this.flatMap(helper);
	}
	/**
	* Drop `n` first elements of the Stream
	*
	* WARNING: It closes the current stream
	*
	* @param n - Number of elements to drop
	* @remarks Since 0.0.1
	*/
	drop(n) {
		if (n <= 0) return this;
		let idx = 0;
		function helper() {
			return idx++ < n;
		}
		return this.dropWhile(helper);
	}
	/**
	* Take elements from the Stream while `f(element) === true`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Take condition
	* @remarks Since 0.0.1
	*/
	takeWhile(f) {
		return new Stream(takeWhileHelper(this.g, f));
	}
	/**
	* Take `n` first elements of the Stream
	*
	* WARNING: It closes the current stream
	*
	* @param n - Number of elements to take
	* @remarks Since 0.0.1
	*/
	take(n) {
		return new Stream(takeNHelper(this.g, n));
	}
	filter(f) {
		return new Stream(filterHelper(this.g, f));
	}
	/**
	* Check whether all elements of the Stream are successful for `f`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Condition to check
	* @remarks Since 0.0.1
	*/
	every(f) {
		for (const v of this.g) if (!f(v)) return false;
		return true;
	}
	/**
	* Check whether one of the elements of the Stream is successful for `f`
	*
	* WARNING: It closes the current stream
	*
	* @param f - Condition to check
	* @remarks Since 0.0.1
	*/
	has(f) {
		for (const v of this.g) if (f(v)) return [true, v];
		return [false, null];
	}
	/**
	* Join `others` Stream to the current Stream
	*
	* WARNING: It closes the current stream and the other ones (as soon as it iterates over them)
	*
	* @param others - Streams to join to the current Stream
	* @remarks Since 0.0.1
	*/
	join(...others) {
		return new Stream(joinHelper(this.g, others));
	}
	/**
	* Take the `nth` element of the Stream of the last (if it does not exist)
	*
	* WARNING: It closes the current stream
	*
	* @param nth - Position of the element to extract
	* @remarks Since 0.0.12
	*/
	getNthOrLast(nth) {
		let remaining = nth;
		let last = null;
		for (const v of this.g) {
			if (remaining-- === 0) return v;
			last = v;
		}
		return last;
	}
};
/**
* Create a Stream based on `g`
*
* @param g - Underlying data of the Stream
*
* @remarks Since 0.0.7
* @public
*/
function stream(g) {
	return new Stream(g);
}
//#endregion
//#region src/check/symbols.ts
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
const cloneMethod = Symbol.for("fast-check/cloneMethod");
/**
* Check if an instance has to be clone
* @remarks Since 2.15.0
* @public
*/
function hasCloneMethod(instance) {
	return instance !== null && (typeof instance === "object" || typeof instance === "function") && cloneMethod in instance && typeof instance[cloneMethod] === "function";
}
/**
* Clone an instance if needed
* @remarks Since 2.15.0
* @public
*/
function cloneIfNeeded(instance) {
	return hasCloneMethod(instance) ? instance[cloneMethod]() : instance;
}
//#endregion
//#region src/check/arbitrary/definition/Value.ts
const safeObjectDefineProperty$4 = Object.defineProperty;
/**
* A `Value<T, TShrink = T>` holds an internal value of type `T`
* and its associated context
*
* @remarks Since 3.0.0 (previously called `NextValue` in 2.15.0)
* @public
*/
var Value = class {
	/**
	* @param value_ - Internal value of the shrinkable
	* @param context - Context associated to the generated value (useful for shrink)
	* @param customGetValue - Limited to internal usages (to ease migration to next), it will be removed on next major
	*/
	constructor(value_, context, customGetValue) {
		this.value_ = value_;
		this.context = context;
		this.hasToBeCloned = customGetValue !== void 0 || hasCloneMethod(value_);
		this.readOnce = false;
		this.value = value_;
		if (this.hasToBeCloned) safeObjectDefineProperty$4(this, "value", {
			get: customGetValue !== void 0 ? customGetValue : this.getValue,
			enumerable: false,
			configurable: false
		});
	}
	/** @internal */
	getValue() {
		if (this.hasToBeCloned) {
			if (!this.readOnce) {
				this.readOnce = true;
				return this.value_;
			}
			return this.value_[cloneMethod]();
		}
		return this.value_;
	}
};
//#endregion
//#region src/check/arbitrary/definition/Arbitrary.ts
/**
* Abstract class able to generate values on type `T`
*
* The values generated by an instance of Arbitrary can be previewed - with {@link sample} - or classified - with {@link statistics}.
*
* @remarks Since 0.0.7
* @public
*/
var Arbitrary = class {
	filter(refinement) {
		return new FilterArbitrary(this, refinement);
	}
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
	map(mapper, unmapper) {
		return new MapArbitrary(this, mapper, unmapper);
	}
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
	chain(chainer) {
		return new ChainArbitrary(this, chainer);
	}
};
/** @internal */
var ChainArbitrary = class extends Arbitrary {
	constructor(arb, chainer) {
		super();
		this.arb = arb;
		this.chainer = chainer;
	}
	generate(mrng, biasFactor) {
		const clonedMrng = mrng.clone();
		const src = this.arb.generate(mrng, biasFactor);
		return this.valueChainer(src, mrng, clonedMrng, biasFactor);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	shrink(value, context) {
		if (this.isSafeContext(context)) return (!context.stoppedForOriginal ? this.arb.shrink(context.originalValue, context.originalContext).map((v) => this.valueChainer(v, context.clonedMrng.clone(), context.clonedMrng, context.originalBias)) : Stream.nil()).join(context.chainedArbitrary.shrink(value, context.chainedContext).map((dst) => {
			const newContext = {
				...context,
				chainedContext: dst.context,
				stoppedForOriginal: true
			};
			return new Value(dst.value_, newContext);
		}));
		return Stream.nil();
	}
	valueChainer(v, generateMrng, clonedMrng, biasFactor) {
		const chainedArbitrary = this.chainer(v.value_);
		const dst = chainedArbitrary.generate(generateMrng, biasFactor);
		const context = {
			originalBias: biasFactor,
			originalValue: v.value_,
			originalContext: v.context,
			stoppedForOriginal: false,
			chainedArbitrary,
			chainedContext: dst.context,
			clonedMrng
		};
		return new Value(dst.value_, context);
	}
	isSafeContext(context) {
		return context !== null && context !== void 0 && typeof context === "object" && "originalBias" in context && "originalValue" in context && "originalContext" in context && "stoppedForOriginal" in context && "chainedArbitrary" in context && "chainedContext" in context && "clonedMrng" in context;
	}
};
/** @internal */
function mapperWithCloneIfNeeded(v, mapper) {
	const sourceValue = v.value;
	const mappedValue = mapper(sourceValue);
	if (v.hasToBeCloned && (typeof mappedValue === "object" && mappedValue !== null || typeof mappedValue === "function") && Object.isExtensible(mappedValue) && !hasCloneMethod(mappedValue)) Object.defineProperty(mappedValue, cloneMethod, { get: () => () => mapperWithCloneIfNeeded(v, mapper)[0] });
	return [mappedValue, sourceValue];
}
/** @internal */
function valueMapper(v, mapper) {
	const [mappedValue, sourceValue] = mapperWithCloneIfNeeded(v, mapper);
	return new Value(mappedValue, {
		originalValue: sourceValue,
		originalContext: v.context
	});
}
/** @internal */
var MapArbitrary = class extends Arbitrary {
	constructor(arb, mapper, unmapper) {
		super();
		this.arb = arb;
		this.mapper = mapper;
		this.unmapper = unmapper;
		this.bindValueMapper = (v) => valueMapper(v, mapper);
	}
	generate(mrng, biasFactor) {
		const g = this.arb.generate(mrng, biasFactor);
		if (!g.hasToBeCloned) {
			const sourceValue = g.value;
			return new Value(this.mapper(sourceValue), {
				originalValue: sourceValue,
				originalContext: g.context
			});
		}
		return valueMapper(g, this.mapper);
	}
	canShrinkWithoutContext(value) {
		if (this.unmapper !== void 0) try {
			const unmapped = this.unmapper(value);
			return this.arb.canShrinkWithoutContext(unmapped);
		} catch {
			return false;
		}
		return false;
	}
	shrink(value, context) {
		if (this.isSafeContext(context)) return this.arb.shrink(context.originalValue, context.originalContext).map(this.bindValueMapper);
		if (this.unmapper !== void 0) {
			const unmapped = this.unmapper(value);
			return this.arb.shrink(unmapped, void 0).map(this.bindValueMapper);
		}
		return Stream.nil();
	}
	isSafeContext(context) {
		return context !== null && context !== void 0 && typeof context === "object" && "originalValue" in context && "originalContext" in context;
	}
};
/** @internal */
var FilterArbitrary = class extends Arbitrary {
	constructor(arb, refinement) {
		super();
		this.arb = arb;
		this.refinement = refinement;
		this.bindRefinementOnValue = (v) => this.refinementOnValue(v);
	}
	generate(mrng, biasFactor) {
		while (true) {
			const g = this.arb.generate(mrng, biasFactor);
			if (this.refinementOnValue(g)) return g;
		}
	}
	canShrinkWithoutContext(value) {
		return this.arb.canShrinkWithoutContext(value) && this.refinement(value);
	}
	shrink(value, context) {
		return this.arb.shrink(value, context).filter(this.bindRefinementOnValue);
	}
	refinementOnValue(v) {
		return this.refinement(v.value);
	}
};
/**
* Ensure an instance is an instance of Arbitrary
* @param instance - The instance to be checked
* @internal
*/
function isArbitrary(instance) {
	return typeof instance === "object" && instance !== null && "generate" in instance && "shrink" in instance && "canShrinkWithoutContext" in instance;
}
/**
* Ensure an instance is an instance of Arbitrary
* @param instance - The instance to be checked
* @internal
*/
function assertIsArbitrary(instance) {
	if (!isArbitrary(instance)) throw new Error("Unexpected value received: not an instance of Arbitrary");
}
//#endregion
//#region src/utils/apply.ts
const untouchedApply = Function.prototype.apply;
const ApplySymbol = Symbol("apply");
/**
* Extract apply or return undefined
* @param f - Function to extract apply from
* @internal
*/
function safeExtractApply(f) {
	try {
		return f.apply;
	} catch {
		return;
	}
}
/**
* Equivalent to `f.apply(instance, args)` but temporary altering the instance
* @internal
*/
function safeApplyHacky(f, instance, args) {
	const ff = f;
	ff[ApplySymbol] = untouchedApply;
	const out = ff[ApplySymbol](instance, args);
	delete ff[ApplySymbol];
	return out;
}
/**
* Equivalent to `f.apply(instance, args)`
* @internal
*/
function safeApply(f, instance, args) {
	if (safeExtractApply(f) === untouchedApply) return f.apply(instance, args);
	return safeApplyHacky(f, instance, args);
}
//#endregion
//#region src/utils/globals.ts
const SArray = Array;
const SBigInt = BigInt;
const SBigInt64Array = BigInt64Array;
const SBigUint64Array = BigUint64Array;
const SBoolean = Boolean;
const SDate = Date;
const SError = Error;
const SFloat32Array = Float32Array;
const SFloat64Array = Float64Array;
const SInt8Array = Int8Array;
const SInt16Array = Int16Array;
const SInt32Array = Int32Array;
const SNumber = Number;
const SString = String;
const SSet = Set;
const SUint8Array = Uint8Array;
const SUint8ClampedArray = Uint8ClampedArray;
const SUint16Array = Uint16Array;
const SUint32Array = Uint32Array;
const SencodeURIComponent = encodeURIComponent;
const SMap$2 = Map;
const SSymbol = Symbol;
const untouchedForEach = Array.prototype.forEach;
const untouchedIndexOf = Array.prototype.indexOf;
const untouchedJoin = Array.prototype.join;
const untouchedMap = Array.prototype.map;
const untouchedFlat = Array.prototype.flat;
const untouchedFilter = Array.prototype.filter;
const untouchedPush = Array.prototype.push;
const untouchedPop = Array.prototype.pop;
const untouchedSplice = Array.prototype.splice;
const untouchedSlice = Array.prototype.slice;
const untouchedSort = Array.prototype.sort;
const untouchedEvery = Array.prototype.every;
function extractForEach(instance) {
	try {
		return instance.forEach;
	} catch {
		return;
	}
}
function extractIndexOf(instance) {
	try {
		return instance.indexOf;
	} catch {
		return;
	}
}
function extractJoin(instance) {
	try {
		return instance.join;
	} catch {
		return;
	}
}
function extractMap(instance) {
	try {
		return instance.map;
	} catch {
		return;
	}
}
function extractFlat(instance) {
	try {
		return instance.flat;
	} catch {
		return;
	}
}
function extractFilter(instance) {
	try {
		return instance.filter;
	} catch {
		return;
	}
}
function extractPush(instance) {
	try {
		return instance.push;
	} catch {
		return;
	}
}
function extractPop(instance) {
	try {
		return instance.pop;
	} catch {
		return;
	}
}
function extractSplice(instance) {
	try {
		return instance.splice;
	} catch {
		return;
	}
}
function extractSlice(instance) {
	try {
		return instance.slice;
	} catch {
		return;
	}
}
function extractSort(instance) {
	try {
		return instance.sort;
	} catch {
		return;
	}
}
function extractEvery(instance) {
	try {
		return instance.every;
	} catch {
		return;
	}
}
function safeForEach(instance, fn) {
	if (extractForEach(instance) === untouchedForEach) return instance.forEach(fn);
	return safeApply(untouchedForEach, instance, [fn]);
}
function safeIndexOf(instance, ...args) {
	if (extractIndexOf(instance) === untouchedIndexOf) return instance.indexOf(...args);
	return safeApply(untouchedIndexOf, instance, args);
}
function safeJoin(instance, ...args) {
	if (extractJoin(instance) === untouchedJoin) return instance.join(...args);
	return safeApply(untouchedJoin, instance, args);
}
function safeMap(instance, fn) {
	if (extractMap(instance) === untouchedMap) return instance.map(fn);
	return safeApply(untouchedMap, instance, [fn]);
}
function safeFlat(instance, depth) {
	if (extractFlat(instance) === untouchedFlat) {
		[].flat();
		return instance.flat(depth);
	}
	return safeApply(untouchedFlat, instance, [depth]);
}
function safeFilter(instance, predicate) {
	if (extractFilter(instance) === untouchedFilter) return instance.filter(predicate);
	return safeApply(untouchedFilter, instance, [predicate]);
}
function safePush(instance, ...args) {
	if (extractPush(instance) === untouchedPush) return instance.push(...args);
	return safeApply(untouchedPush, instance, args);
}
function safePop$1(instance) {
	if (extractPop(instance) === untouchedPop) return instance.pop();
	return safeApply(untouchedPop, instance, []);
}
function safeSplice(instance, ...args) {
	if (extractSplice(instance) === untouchedSplice) return instance.splice(...args);
	return safeApply(untouchedSplice, instance, args);
}
function safeSlice(instance, ...args) {
	if (extractSlice(instance) === untouchedSlice) return instance.slice(...args);
	return safeApply(untouchedSlice, instance, args);
}
function safeSort(instance, ...args) {
	if (extractSort(instance) === untouchedSort) return instance.sort(...args);
	return safeApply(untouchedSort, instance, args);
}
function safeEvery(instance, ...args) {
	if (extractEvery(instance) === untouchedEvery) return instance.every(...args);
	return safeApply(untouchedEvery, instance, args);
}
const untouchedGetTime = Date.prototype.getTime;
const untouchedToISOString = Date.prototype.toISOString;
function extractGetTime(instance) {
	try {
		return instance.getTime;
	} catch {
		return;
	}
}
function extractToISOString(instance) {
	try {
		return instance.toISOString;
	} catch {
		return;
	}
}
function safeGetTime(instance) {
	if (extractGetTime(instance) === untouchedGetTime) return instance.getTime();
	return safeApply(untouchedGetTime, instance, []);
}
function safeToISOString(instance) {
	if (extractToISOString(instance) === untouchedToISOString) return instance.toISOString();
	return safeApply(untouchedToISOString, instance, []);
}
const untouchedAdd = Set.prototype.add;
const untouchedHas = Set.prototype.has;
function extractAdd(instance) {
	try {
		return instance.add;
	} catch {
		return;
	}
}
function extractHas(instance) {
	try {
		return instance.has;
	} catch (err) {
		return;
	}
}
function safeAdd(instance, value) {
	if (extractAdd(instance) === untouchedAdd) return instance.add(value);
	return safeApply(untouchedAdd, instance, [value]);
}
function safeHas(instance, value) {
	if (extractHas(instance) === untouchedHas) return instance.has(value);
	return safeApply(untouchedHas, instance, [value]);
}
const untouchedSet = WeakMap.prototype.set;
const untouchedGet = WeakMap.prototype.get;
function extractSet(instance) {
	try {
		return instance.set;
	} catch (err) {
		return;
	}
}
function extractGet(instance) {
	try {
		return instance.get;
	} catch (err) {
		return;
	}
}
function safeSet(instance, key, value) {
	if (extractSet(instance) === untouchedSet) return instance.set(key, value);
	return safeApply(untouchedSet, instance, [key, value]);
}
function safeGet(instance, key) {
	if (extractGet(instance) === untouchedGet) return instance.get(key);
	return safeApply(untouchedGet, instance, [key]);
}
const untouchedMapSet = Map.prototype.set;
const untouchedMapGet = Map.prototype.get;
const untouchedMapHas = Map.prototype.has;
function extractMapSet(instance) {
	try {
		return instance.set;
	} catch (err) {
		return;
	}
}
function extractMapGet(instance) {
	try {
		return instance.get;
	} catch (err) {
		return;
	}
}
function extractMapHas(instance) {
	try {
		return instance.has;
	} catch (err) {
		return;
	}
}
function safeMapSet(instance, key, value) {
	if (extractMapSet(instance) === untouchedMapSet) return instance.set(key, value);
	return safeApply(untouchedMapSet, instance, [key, value]);
}
function safeMapGet(instance, key) {
	if (extractMapGet(instance) === untouchedMapGet) return instance.get(key);
	return safeApply(untouchedMapGet, instance, [key]);
}
function safeMapHas(instance, key) {
	if (extractMapHas(instance) === untouchedMapHas) return instance.has(key);
	return safeApply(untouchedMapHas, instance, [key]);
}
const untouchedSplit = String.prototype.split;
const untouchedStartsWith = String.prototype.startsWith;
const untouchedEndsWith = String.prototype.endsWith;
const untouchedSubstring = String.prototype.substring;
const untouchedToLowerCase = String.prototype.toLowerCase;
const untouchedToUpperCase = String.prototype.toUpperCase;
const untouchedPadStart = String.prototype.padStart;
const untouchedCharCodeAt = String.prototype.charCodeAt;
const untouchedNormalize = String.prototype.normalize;
const untouchedReplace = String.prototype.replace;
function extractSplit(instance) {
	try {
		return instance.split;
	} catch {
		return;
	}
}
function extractStartsWith(instance) {
	try {
		return instance.startsWith;
	} catch {
		return;
	}
}
function extractEndsWith(instance) {
	try {
		return instance.endsWith;
	} catch {
		return;
	}
}
function extractSubstring(instance) {
	try {
		return instance.substring;
	} catch {
		return;
	}
}
function extractToLowerCase(instance) {
	try {
		return instance.toLowerCase;
	} catch {
		return;
	}
}
function extractToUpperCase(instance) {
	try {
		return instance.toUpperCase;
	} catch {
		return;
	}
}
function extractPadStart(instance) {
	try {
		return instance.padStart;
	} catch {
		return;
	}
}
function extractCharCodeAt(instance) {
	try {
		return instance.charCodeAt;
	} catch {
		return;
	}
}
function extractNormalize(instance) {
	try {
		return instance.normalize;
	} catch (err) {
		return;
	}
}
function extractReplace(instance) {
	try {
		return instance.replace;
	} catch {
		return;
	}
}
function safeSplit(instance, ...args) {
	if (extractSplit(instance) === untouchedSplit) return instance.split(...args);
	return safeApply(untouchedSplit, instance, args);
}
function safeStartsWith(instance, ...args) {
	if (extractStartsWith(instance) === untouchedStartsWith) return instance.startsWith(...args);
	return safeApply(untouchedStartsWith, instance, args);
}
function safeEndsWith(instance, ...args) {
	if (extractEndsWith(instance) === untouchedEndsWith) return instance.endsWith(...args);
	return safeApply(untouchedEndsWith, instance, args);
}
function safeSubstring(instance, ...args) {
	if (extractSubstring(instance) === untouchedSubstring) return instance.substring(...args);
	return safeApply(untouchedSubstring, instance, args);
}
function safeToLowerCase(instance) {
	if (extractToLowerCase(instance) === untouchedToLowerCase) return instance.toLowerCase();
	return safeApply(untouchedToLowerCase, instance, []);
}
function safeToUpperCase(instance) {
	if (extractToUpperCase(instance) === untouchedToUpperCase) return instance.toUpperCase();
	return safeApply(untouchedToUpperCase, instance, []);
}
function safePadStart(instance, ...args) {
	if (extractPadStart(instance) === untouchedPadStart) return instance.padStart(...args);
	return safeApply(untouchedPadStart, instance, args);
}
function safeCharCodeAt(instance, index) {
	if (extractCharCodeAt(instance) === untouchedCharCodeAt) return instance.charCodeAt(index);
	return safeApply(untouchedCharCodeAt, instance, [index]);
}
function safeNormalize(instance, form) {
	if (extractNormalize(instance) === untouchedNormalize) return instance.normalize(form);
	return safeApply(untouchedNormalize, instance, [form]);
}
function safeReplace(instance, pattern, replacement) {
	if (extractReplace(instance) === untouchedReplace) return instance.replace(pattern, replacement);
	return safeApply(untouchedReplace, instance, [pattern, replacement]);
}
const untouchedNumberToString = Number.prototype.toString;
function extractNumberToString(instance) {
	try {
		return instance.toString;
	} catch {
		return;
	}
}
function safeNumberToString(instance, ...args) {
	if (extractNumberToString(instance) === untouchedNumberToString) return instance.toString(...args);
	return safeApply(untouchedNumberToString, instance, args);
}
const untouchedHasOwnProperty = Object.prototype.hasOwnProperty;
const untouchedToString = Object.prototype.toString;
function safeHasOwnProperty(instance, v) {
	return safeApply(untouchedHasOwnProperty, instance, [v]);
}
function safeToString(instance) {
	return safeApply(untouchedToString, instance, []);
}
const untouchedErrorToString = Error.prototype.toString;
function safeErrorToString(instance) {
	return safeApply(untouchedErrorToString, instance, []);
}
//#endregion
//#region src/stream/LazyIterableIterator.ts
/** @internal */
var LazyIterableIterator = class {
	constructor(producer) {
		this.producer = producer;
	}
	[Symbol.iterator]() {
		if (this.it === void 0) this.it = this.producer();
		return this.it;
	}
	next() {
		if (this.it === void 0) this.it = this.producer();
		return this.it.next();
	}
};
/**
* Create an IterableIterator based on a function that will only be called once if needed
*
* @param producer - Function to instanciate the underlying IterableIterator
*
* @internal
*/
function makeLazy(producer) {
	return new LazyIterableIterator(producer);
}
//#endregion
//#region src/arbitrary/_internals/TupleArbitrary.ts
const safeArrayIsArray$4 = Array.isArray;
const safeObjectDefineProperty$3 = Object.defineProperty;
/** @internal */
function tupleMakeItCloneable(vs, ctxs, values) {
	return safeObjectDefineProperty$3(vs, cloneMethod, { value: () => {
		const cloned = [];
		for (let idx = 0; idx !== values.length; ++idx) {
			let current = values[idx];
			if (current === void 0) current = new Value(vs[idx], ctxs[idx]);
			safePush(cloned, current.value);
		}
		tupleMakeItCloneable(cloned, ctxs, values);
		return cloned;
	} });
}
/** @internal */
function tupleShrink(arbs, value, context) {
	const shrinks = [];
	const safeContext = safeArrayIsArray$4(context) ? context : [];
	for (let idx = 0; idx !== arbs.length; ++idx) safePush(shrinks, makeLazy(() => arbs[idx].shrink(value[idx], safeContext[idx]).map((v) => {
		let cloneable = false;
		const vs = [];
		const ctxs = [];
		const mapped = [];
		for (let nestedIdx = 0; nestedIdx !== arbs.length; ++nestedIdx) {
			const nestedV = nestedIdx === idx ? v : new Value(cloneIfNeeded(value[nestedIdx]), safeContext[nestedIdx]);
			if (nestedV.hasToBeCloned) {
				cloneable = true;
				mapped[nestedIdx] = nestedV;
			}
			safePush(vs, nestedV.value);
			safePush(ctxs, nestedV.context);
		}
		if (cloneable) tupleMakeItCloneable(vs, ctxs, mapped);
		return new Value(vs, ctxs);
	})));
	return Stream.nil().join(...shrinks);
}
/** @internal */
var TupleArbitrary = class extends Arbitrary {
	constructor(arbs) {
		super();
		this.arbs = arbs;
		for (let idx = 0; idx !== arbs.length; ++idx) {
			const arb = arbs[idx];
			if (arb === null || arb === void 0 || arb.generate === null || arb.generate === void 0) throw new Error(`Invalid parameter encountered at index ${idx}: expecting an Arbitrary`);
		}
	}
	generate(mrng, biasFactor) {
		let cloneable = false;
		const vs = [];
		const ctxs = [];
		const mapped = [];
		for (let idx = 0; idx !== this.arbs.length; ++idx) {
			const v = this.arbs[idx].generate(mrng, biasFactor);
			if (v.hasToBeCloned) {
				cloneable = true;
				mapped[idx] = v;
			}
			safePush(vs, v.value);
			safePush(ctxs, v.context);
		}
		if (cloneable) tupleMakeItCloneable(vs, ctxs, mapped);
		return new Value(vs, ctxs);
	}
	canShrinkWithoutContext(value) {
		if (!safeArrayIsArray$4(value) || value.length !== this.arbs.length) return false;
		for (let index = 0; index !== this.arbs.length; ++index) if (!this.arbs[index].canShrinkWithoutContext(value[index])) return false;
		return true;
	}
	shrink(value, context) {
		return tupleShrink(this.arbs, value, context);
	}
};
//#endregion
//#region src/arbitrary/tuple.ts
/**
* For tuples produced using the provided `arbs`
*
* @param arbs - Ordered list of arbitraries
*
* @remarks Since 0.0.1
* @public
*/
function tuple(...arbs) {
	return new TupleArbitrary(arbs);
}
//#endregion
//#region src/check/property/IRawProperty.ts
const safeMathLog$3 = Math.log;
/**
* Convert runId (IProperty) into a frequency (Arbitrary)
*
* @param runId - Id of the run starting at 0
* @returns Frequency of bias starting at 2
*
* @internal
*/
function runIdToFrequency(runId) {
	return 2 + ~~(safeMathLog$3(runId + 1) * .4342944819032518);
}
//#endregion
//#region src/check/runner/configuration/GlobalParameters.ts
/** @internal */
let globalParameters = {};
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
function configureGlobal(parameters) {
	globalParameters = parameters;
}
/**
* Read global parameters that will be used by runners
* @remarks Since 1.18.0
* @public
*/
function readConfigureGlobal() {
	return globalParameters;
}
/**
* Reset global parameters
* @remarks Since 1.18.0
* @public
*/
function resetConfigureGlobal() {
	globalParameters = {};
}
//#endregion
//#region src/arbitrary/_internals/helpers/NoUndefinedAsContext.ts
/** @internal */
const UndefinedContextPlaceholder = Symbol("UndefinedContextPlaceholder");
/** @internal */
function noUndefinedAsContext(value) {
	if (value.context !== void 0) return value;
	if (value.hasToBeCloned) return new Value(value.value_, UndefinedContextPlaceholder, () => value.value);
	return new Value(value.value_, UndefinedContextPlaceholder);
}
//#endregion
//#region src/check/property/AsyncProperty.generic.ts
const dummyHook$1 = () => {};
/**
* Asynchronous property, see {@link IAsyncProperty}
*
* Prefer using {@link asyncProperty} instead
*
* @internal
*/
var AsyncProperty = class {
	constructor(arb, predicate) {
		this.arb = arb;
		this.predicate = predicate;
		const { asyncBeforeEach, asyncAfterEach, beforeEach, afterEach } = readConfigureGlobal() || {};
		if (asyncBeforeEach !== void 0 && beforeEach !== void 0) throw SError("Global \"asyncBeforeEach\" and \"beforeEach\" parameters can't be set at the same time when running async properties");
		if (asyncAfterEach !== void 0 && afterEach !== void 0) throw SError("Global \"asyncAfterEach\" and \"afterEach\" parameters can't be set at the same time when running async properties");
		this.beforeEachHook = asyncBeforeEach || beforeEach || dummyHook$1;
		this.afterEachHook = asyncAfterEach || afterEach || dummyHook$1;
	}
	isAsync() {
		return true;
	}
	generate(mrng, runId) {
		return noUndefinedAsContext(this.arb.generate(mrng, runId !== void 0 ? runIdToFrequency(runId) : void 0));
	}
	shrink(value) {
		if (value.context === void 0 && !this.arb.canShrinkWithoutContext(value.value_)) return Stream.nil();
		const safeContext = value.context !== UndefinedContextPlaceholder ? value.context : void 0;
		return this.arb.shrink(value.value_, safeContext).map(noUndefinedAsContext);
	}
	async runBeforeEach() {
		await this.beforeEachHook();
	}
	async runAfterEach() {
		await this.afterEachHook();
	}
	async run(v) {
		try {
			const output = await this.predicate(v);
			return output === void 0 || output === true ? null : { error: new SError("Property failed by returning false") };
		} catch (err) {
			if (PreconditionFailure.isFailure(err)) return err;
			return { error: err };
		}
	}
	/**
	* Define a function that should be called before all calls to the predicate
	* @param hookFunction - Function to be called
	* @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.beforeEach(fn)] })`
	*/
	beforeEach(hookFunction) {
		const previousBeforeEachHook = this.beforeEachHook;
		this.beforeEachHook = () => hookFunction(previousBeforeEachHook);
		return this;
	}
	/**
	* Define a function that should be called after all calls to the predicate
	* @param hookFunction - Function to be called
	* @deprecated Prefer the life-cycle plugins: `fc.assert(property, { plugins: [fc.afterEach(fn)] })`
	*/
	afterEach(hookFunction) {
		const previousAfterEachHook = this.afterEachHook;
		this.afterEachHook = () => hookFunction(previousAfterEachHook);
		return this;
	}
};
//#endregion
//#region src/arbitrary/_internals/AlwaysShrinkableArbitrary.ts
/**
* Arbitrary considering any value as shrinkable whatever the received context.
* In case the context corresponds to nil, it will be checked when calling shrink:
* valid would mean stream coming from shrink, otherwise empty stream
* @internal
*/
var AlwaysShrinkableArbitrary = class extends Arbitrary {
	constructor(arb) {
		super();
		this.arb = arb;
	}
	generate(mrng, biasFactor) {
		return noUndefinedAsContext(this.arb.generate(mrng, biasFactor));
	}
	canShrinkWithoutContext(_value) {
		return true;
	}
	shrink(value, context) {
		if (context === void 0 && !this.arb.canShrinkWithoutContext(value)) return Stream.nil();
		const safeContext = context !== UndefinedContextPlaceholder ? context : void 0;
		return this.arb.shrink(value, safeContext).map(noUndefinedAsContext);
	}
};
//#endregion
//#region src/check/property/AsyncProperty.ts
/**
* Instantiate a new {@link fast-check#IAsyncProperty}
* @param predicate - Assess the success of the property. Would be considered falsy if it throws or if its output evaluates to false
* @remarks Since 0.0.7
* @public
*/
function asyncProperty(...args) {
	if (args.length < 2) throw new Error("asyncProperty expects at least two parameters");
	const arbs = safeSlice(args, 0, args.length - 1);
	const p = args[args.length - 1];
	safeForEach(arbs, assertIsArbitrary);
	return new AsyncProperty(tuple(...safeMap(arbs, (arb) => new AlwaysShrinkableArbitrary(arb))), (t) => p(...t));
}
//#endregion
//#region src/check/property/Property.generic.ts
const dummyHook = () => {};
/**
* Property, see {@link IProperty}
*
* Prefer using {@link property} instead
*
* @internal
*/
var Property = class {
	constructor(arb, predicate) {
		this.arb = arb;
		this.predicate = predicate;
		const { beforeEach = dummyHook, afterEach = dummyHook, asyncBeforeEach, asyncAfterEach } = readConfigureGlobal() || {};
		if (asyncBeforeEach !== void 0) throw SError("\"asyncBeforeEach\" can't be set when running synchronous properties");
		if (asyncAfterEach !== void 0) throw SError("\"asyncAfterEach\" can't be set when running synchronous properties");
		this.beforeEachHook = beforeEach;
		this.afterEachHook = afterEach;
	}
	isAsync() {
		return false;
	}
	generate(mrng, runId) {
		return noUndefinedAsContext(this.arb.generate(mrng, runId !== void 0 ? runIdToFrequency(runId) : void 0));
	}
	shrink(value) {
		if (value.context === void 0 && !this.arb.canShrinkWithoutContext(value.value_)) return Stream.nil();
		const safeContext = value.context !== UndefinedContextPlaceholder ? value.context : void 0;
		return this.arb.shrink(value.value_, safeContext).map(noUndefinedAsContext);
	}
	runBeforeEach() {
		this.beforeEachHook();
	}
	runAfterEach() {
		this.afterEachHook();
	}
	run(v) {
		try {
			const output = this.predicate(v);
			return output === void 0 || output === true ? null : { error: new SError("Property failed by returning false") };
		} catch (err) {
			if (PreconditionFailure.isFailure(err)) return err;
			return { error: err };
		}
	}
	beforeEach(hookFunction) {
		const previousBeforeEachHook = this.beforeEachHook;
		this.beforeEachHook = () => hookFunction(previousBeforeEachHook);
		return this;
	}
	afterEach(hookFunction) {
		const previousAfterEachHook = this.afterEachHook;
		this.afterEachHook = () => hookFunction(previousAfterEachHook);
		return this;
	}
};
//#endregion
//#region src/check/property/Property.ts
/**
* Instantiate a new {@link fast-check#IProperty}
* @param predicate - Assess the success of the property. Would be considered falsy if it throws or if its output evaluates to false
* @remarks Since 0.0.1
* @public
*/
function property(...args) {
	if (args.length < 2) throw new Error("property expects at least two parameters");
	const arbs = safeSlice(args, 0, args.length - 1);
	const p = args[args.length - 1];
	safeForEach(arbs, assertIsArbitrary);
	return new Property(tuple(...safeMap(arbs, (arb) => new AlwaysShrinkableArbitrary(arb))), (t) => p(...t));
}
//#endregion
//#region src/check/runner/configuration/VerbosityLevel.ts
/**
* Verbosity level
* @remarks Since 1.9.1
* @public
*/
let VerbosityLevel = /* @__PURE__ */ function(VerbosityLevel) {
	/**
	* Level 0 (default)
	*
	* Minimal reporting:
	* - minimal failing case
	* - error log corresponding to the minimal failing case
	*
	* @remarks Since 1.9.1
	*/
	VerbosityLevel[VerbosityLevel["None"] = 0] = "None";
	/**
	* Level 1
	*
	* Failures reporting:
	* - same as `VerbosityLevel.None`
	* - list all the failures encountered during the shrinking process
	*
	* @remarks Since 1.9.1
	*/
	VerbosityLevel[VerbosityLevel["Verbose"] = 1] = "Verbose";
	/**
	* Level 2
	*
	* Execution flow reporting:
	* - same as `VerbosityLevel.None`
	* - all runs with their associated status displayed as a tree
	*
	* @remarks Since 1.9.1
	*/
	VerbosityLevel[VerbosityLevel["VeryVerbose"] = 2] = "VeryVerbose";
	return VerbosityLevel;
}({});
//#endregion
//#region src/random/generator/RandomGenerator.ts
/** @internal */
function adaptRandomGeneratorTo8x(rng) {
	if ("unsafeNext" in rng) {
		if (rng.unsafeJump === void 0) return {
			clone: () => adaptRandomGeneratorTo8x(rng),
			next: () => rng.unsafeNext(),
			getState: () => rng.getState()
		};
		return {
			clone: () => adaptRandomGeneratorTo8x(rng),
			next: () => rng.unsafeNext(),
			jump: () => rng.unsafeJump(),
			getState: () => rng.getState()
		};
	}
	return rng;
}
/** @internal */
function adaptRandomGeneratorToInternal(rng) {
	if ("jump" in rng && typeof rng.jump === "function") return rng;
	return {
		clone: () => adaptRandomGeneratorToInternal(rng),
		next: () => rng.next(),
		jump: () => (0, pure_rand_utils_skipN.skipN)(rng, 42),
		getState: () => rng.getState()
	};
}
/** @internal */
function adaptRandomGenerator(rng) {
	return adaptRandomGeneratorToInternal(adaptRandomGeneratorTo8x(rng));
}
//#endregion
//#region src/check/runner/configuration/QualifiedParameters.ts
const safeDateNow$1 = Date.now;
const safeMathMin$6 = Math.min;
const safeMathRandom = Math.random;
/**
* Configuration extracted from incoming Parameters
*
* It handles and set the default settings that will be used by runners.
*
* @internal
*/
var QualifiedParameters = class {
	constructor(op) {
		const p = op || {};
		this.seed = readSeed(p);
		this.randomType = readRandomType(p);
		this.numRuns = readNumRuns(p);
		this.verbose = readVerbose(p);
		this.maxSkipsPerRun = p.maxSkipsPerRun !== void 0 ? p.maxSkipsPerRun : 100;
		this.timeout = safeTimeout(p.timeout);
		this.skipAllAfterTimeLimit = safeTimeout(p.skipAllAfterTimeLimit);
		this.interruptAfterTimeLimit = safeTimeout(p.interruptAfterTimeLimit);
		this.markInterruptAsFailure = p.markInterruptAsFailure === true;
		this.skipEqualValues = p.skipEqualValues === true;
		this.ignoreEqualValues = p.ignoreEqualValues === true;
		this.logger = p.logger !== void 0 ? p.logger : (v) => {
			console.log(v);
		};
		this.path = p.path !== void 0 ? p.path : "";
		this.unbiased = p.unbiased === true;
		this.examples = p.examples !== void 0 ? p.examples : [];
		this.endOnFailure = p.endOnFailure === true;
		this.reporter = p.reporter;
		this.asyncReporter = p.asyncReporter;
		this.includeErrorInReport = p.includeErrorInReport === true;
		this.plugins = p.plugins !== void 0 ? p.plugins : [];
	}
	toParameters() {
		return {
			seed: this.seed,
			randomType: this.randomType,
			numRuns: this.numRuns,
			maxSkipsPerRun: this.maxSkipsPerRun,
			timeout: this.timeout,
			skipAllAfterTimeLimit: this.skipAllAfterTimeLimit,
			interruptAfterTimeLimit: this.interruptAfterTimeLimit,
			markInterruptAsFailure: this.markInterruptAsFailure,
			skipEqualValues: this.skipEqualValues,
			ignoreEqualValues: this.ignoreEqualValues,
			path: this.path,
			logger: this.logger,
			unbiased: this.unbiased,
			verbose: this.verbose,
			examples: this.examples,
			endOnFailure: this.endOnFailure,
			reporter: this.reporter,
			asyncReporter: this.asyncReporter,
			includeErrorInReport: this.includeErrorInReport,
			plugins: this.plugins
		};
	}
};
/** @internal */
function createQualifiedRandomGenerator(random) {
	return (seed) => {
		return adaptRandomGenerator(random(seed));
	};
}
/** @internal */
function readSeed(p) {
	if (p.seed === void 0) return safeDateNow$1() ^ safeMathRandom() * 4294967296;
	const seed32 = p.seed | 0;
	if (p.seed === seed32) return seed32;
	return seed32 ^ (p.seed - seed32) * 4294967296;
}
/** @internal */
function readRandomType(p) {
	if (p.randomType === void 0) return pure_rand_generator_xorshift128plus.xorshift128plus;
	if (typeof p.randomType === "string") switch (p.randomType) {
		case "mersenne": return createQualifiedRandomGenerator(pure_rand_generator_mersenne.mersenne);
		case "congruential":
		case "congruential32": return createQualifiedRandomGenerator(pure_rand_generator_congruential32.congruential32);
		case "xorshift128plus": return pure_rand_generator_xorshift128plus.xorshift128plus;
		case "xoroshiro128plus": return pure_rand_generator_xoroshiro128plus.xoroshiro128plus;
		default: throw new Error(`Invalid random specified: '${p.randomType}'`);
	}
	const mrng = p.randomType(0);
	if ("min" in mrng && mrng.min !== -2147483648) throw new Error(`Invalid random number generator: min must equal -0x80000000, got ${String(mrng.min)}`);
	if ("max" in mrng && mrng.max !== 2147483647) throw new Error(`Invalid random number generator: max must equal 0x7fffffff, got ${String(mrng.max)}`);
	if (mrng === adaptRandomGenerator(mrng)) return p.randomType;
	return createQualifiedRandomGenerator(p.randomType);
}
/** @internal */
function readNumRuns(p) {
	const defaultValue = 100;
	if (p.numRuns !== void 0) return p.numRuns;
	if (p.num_runs !== void 0) return p.num_runs;
	return defaultValue;
}
/** @internal */
function readVerbose(p) {
	if (p.verbose === void 0) return 0;
	if (typeof p.verbose === "boolean") return p.verbose === true ? 1 : 0;
	if (p.verbose <= 0) return 0;
	if (p.verbose >= 2) return 2;
	return p.verbose | 0;
}
/** @internal */
function safeTimeout(value) {
	if (value === void 0) return;
	return safeMathMin$6(value, 2147483647);
}
/**
* Extract a runner configuration from Parameters
* @param p - Incoming Parameters
*/
function read(op) {
	return new QualifiedParameters(op);
}
//#endregion
//#region src/check/property/SkipAfterProperty.ts
/** @internal */
function interruptAfter(timeMs, setTimeoutSafe, clearTimeoutSafe) {
	let timeoutHandle = null;
	return {
		clear: () => clearTimeoutSafe(timeoutHandle),
		promise: new Promise((resolve) => {
			timeoutHandle = setTimeoutSafe(() => {
				resolve(new PreconditionFailure(true));
			}, timeMs);
		})
	};
}
/** @internal */
var SkipAfterProperty = class {
	constructor(property, getTime, timeLimit, interruptExecution, setTimeoutSafe, clearTimeoutSafe) {
		this.property = property;
		this.getTime = getTime;
		this.interruptExecution = interruptExecution;
		this.setTimeoutSafe = setTimeoutSafe;
		this.clearTimeoutSafe = clearTimeoutSafe;
		this.skipAfterTime = this.getTime() + timeLimit;
	}
	isAsync() {
		return this.property.isAsync();
	}
	generate(mrng, runId) {
		return this.property.generate(mrng, runId);
	}
	shrink(value) {
		return this.property.shrink(value);
	}
	run(v) {
		const remainingTime = this.skipAfterTime - this.getTime();
		if (remainingTime <= 0) {
			const preconditionFailure = new PreconditionFailure(this.interruptExecution);
			if (this.isAsync()) return Promise.resolve(preconditionFailure);
			else return preconditionFailure;
		}
		if (this.interruptExecution && this.isAsync()) {
			const t = interruptAfter(remainingTime, this.setTimeoutSafe, this.clearTimeoutSafe);
			const propRun = Promise.race([this.property.run(v), t.promise]);
			propRun.then(t.clear, t.clear);
			return propRun;
		}
		return this.property.run(v);
	}
	runBeforeEach() {
		return this.property.runBeforeEach();
	}
	runAfterEach() {
		return this.property.runAfterEach();
	}
};
//#endregion
//#region src/check/property/TimeoutProperty.ts
/** @internal */
const timeoutAfter$1 = (timeMs, setTimeoutSafe, clearTimeoutSafe) => {
	let timeoutHandle = null;
	return {
		clear: () => clearTimeoutSafe(timeoutHandle),
		promise: new Promise((resolve) => {
			timeoutHandle = setTimeoutSafe(() => {
				resolve({ error: new SError(`Property timeout: exceeded limit of ${timeMs} milliseconds`) });
			}, timeMs);
		})
	};
};
/** @internal */
var TimeoutProperty = class {
	constructor(property, timeMs, setTimeoutSafe, clearTimeoutSafe) {
		this.property = property;
		this.timeMs = timeMs;
		this.setTimeoutSafe = setTimeoutSafe;
		this.clearTimeoutSafe = clearTimeoutSafe;
	}
	isAsync() {
		return true;
	}
	generate(mrng, runId) {
		return this.property.generate(mrng, runId);
	}
	shrink(value) {
		return this.property.shrink(value);
	}
	async run(v) {
		const t = timeoutAfter$1(this.timeMs, this.setTimeoutSafe, this.clearTimeoutSafe);
		const propRun = Promise.race([this.property.run(v), t.promise]);
		propRun.then(t.clear, t.clear);
		return propRun;
	}
	runBeforeEach() {
		return Promise.resolve(this.property.runBeforeEach());
	}
	runAfterEach() {
		return Promise.resolve(this.property.runAfterEach());
	}
};
//#endregion
//#region src/check/property/UnbiasedProperty.ts
/** @internal */
var UnbiasedProperty = class {
	constructor(property) {
		this.property = property;
	}
	isAsync() {
		return this.property.isAsync();
	}
	generate(mrng, _runId) {
		return this.property.generate(mrng, void 0);
	}
	shrink(value) {
		return this.property.shrink(value);
	}
	run(v) {
		return this.property.run(v);
	}
	runBeforeEach() {
		return this.property.runBeforeEach();
	}
	runAfterEach() {
		return this.property.runAfterEach();
	}
};
//#endregion
//#region src/utils/stringify.ts
const safeArrayFrom = Array.from;
const safeBufferIsBuffer = typeof Buffer !== "undefined" ? Buffer.isBuffer : void 0;
const safeJsonStringify$1 = JSON.stringify;
const safeNumberIsNaN$5 = Number.isNaN;
const safeObjectKeys$5 = Object.keys;
const safeObjectGetOwnPropertySymbols$2 = Object.getOwnPropertySymbols;
const safeObjectGetOwnPropertyDescriptor$3 = Object.getOwnPropertyDescriptor;
const safeObjectGetPrototypeOf$2 = Object.getPrototypeOf;
const safeNegativeInfinity$7 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$8 = Number.POSITIVE_INFINITY;
/**
* Use this symbol to define a custom serializer for your instances.
* Serializer must be a function returning a string (see {@link WithToStringMethod}).
*
* @remarks Since 2.17.0
* @public
*/
const toStringMethod = Symbol.for("fast-check/toStringMethod");
/**
* Check if an instance implements {@link WithToStringMethod}
*
* @remarks Since 2.17.0
* @public
*/
function hasToStringMethod(instance) {
	return instance !== null && (typeof instance === "object" || typeof instance === "function") && toStringMethod in instance && typeof instance[toStringMethod] === "function";
}
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
const asyncToStringMethod = Symbol.for("fast-check/asyncToStringMethod");
/**
* Check if an instance implements {@link WithAsyncToStringMethod}
*
* @remarks Since 2.17.0
* @public
*/
function hasAsyncToStringMethod(instance) {
	return instance !== null && (typeof instance === "object" || typeof instance === "function") && asyncToStringMethod in instance && typeof instance[asyncToStringMethod] === "function";
}
/** @internal */
const findSymbolNameRegex = /^Symbol\((.*)\)$/;
/**
* Only called with symbol produced by Symbol(string | undefined)
* Not Symbol.for(string)
* @internal
*/
function getSymbolDescription(s) {
	if (s.description !== void 0) return s.description;
	const m = findSymbolNameRegex.exec(SString(s));
	return m && m[1].length ? m[1] : null;
}
/** @internal */
function stringifyNumber(numValue) {
	switch (numValue) {
		case 0: return 1 / numValue === safeNegativeInfinity$7 ? "-0" : "0";
		case safeNegativeInfinity$7: return "Number.NEGATIVE_INFINITY";
		case safePositiveInfinity$8: return "Number.POSITIVE_INFINITY";
		default: return numValue === numValue ? SString(numValue) : "Number.NaN";
	}
}
/** @internal */
function isSparseArray(arr) {
	let previousNumberedIndex = -1;
	for (const index in arr) {
		const numberedIndex = Number(index);
		if (numberedIndex !== previousNumberedIndex + 1) return true;
		previousNumberedIndex = numberedIndex;
	}
	return previousNumberedIndex + 1 !== arr.length;
}
/** @internal */
function stringifyInternal(value, previousValues, getAsyncContent) {
	const currentValues = [...previousValues, value];
	if (typeof value === "object") {
		if (safeIndexOf(previousValues, value) !== -1) return "[cyclic]";
	}
	if (hasAsyncToStringMethod(value)) {
		const content = getAsyncContent(value);
		if (content.state === "fulfilled") return content.value;
	}
	if (hasToStringMethod(value)) try {
		return value[toStringMethod]();
	} catch {}
	switch (safeToString(value)) {
		case "[object Array]": {
			const arr = value;
			if (arr.length >= 50 && isSparseArray(arr)) {
				const assignments = [];
				for (const index in arr) if (!safeNumberIsNaN$5(Number(index))) safePush(assignments, `${index}:${stringifyInternal(arr[index], currentValues, getAsyncContent)}`);
				return assignments.length !== 0 ? `Object.assign(Array(${arr.length}),{${safeJoin(assignments, ",")}})` : `Array(${arr.length})`;
			}
			const stringifiedArray = safeJoin(safeMap(arr, (v) => stringifyInternal(v, currentValues, getAsyncContent)), ",");
			return arr.length === 0 || arr.length - 1 in arr ? `[${stringifiedArray}]` : `[${stringifiedArray},]`;
		}
		case "[object BigInt]": return `${value}n`;
		case "[object Boolean]": {
			const unboxedToString = value == true ? "true" : "false";
			return typeof value === "boolean" ? unboxedToString : `new Boolean(${unboxedToString})`;
		}
		case "[object Date]": {
			const d = value;
			return safeNumberIsNaN$5(safeGetTime(d)) ? `new Date(NaN)` : `new Date(${safeJsonStringify$1(safeToISOString(d))})`;
		}
		case "[object Map]": return `new Map(${stringifyInternal(Array.from(value), currentValues, getAsyncContent)})`;
		case "[object Null]": return `null`;
		case "[object Number]": return typeof value === "number" ? stringifyNumber(value) : `new Number(${stringifyNumber(Number(value))})`;
		case "[object Object]": {
			try {
				const toStringAccessor = value.toString;
				if (typeof toStringAccessor === "function" && toStringAccessor !== Object.prototype.toString) return value.toString();
			} catch {
				return "[object Object]";
			}
			const mapper = (k) => `${k === "__proto__" ? "[\"__proto__\"]" : typeof k === "symbol" ? `[${stringifyInternal(k, currentValues, getAsyncContent)}]` : safeJsonStringify$1(k)}:${stringifyInternal(value[k], currentValues, getAsyncContent)}`;
			return "{" + safeJoin([
				...safeObjectGetPrototypeOf$2(value) === null ? ["__proto__:null"] : [],
				...safeMap(safeObjectKeys$5(value), mapper),
				...safeMap(safeFilter(safeObjectGetOwnPropertySymbols$2(value), (s) => {
					const descriptor = safeObjectGetOwnPropertyDescriptor$3(value, s);
					return descriptor && descriptor.enumerable;
				}), mapper)
			], ",") + "}";
		}
		case "[object Set]": return `new Set(${stringifyInternal(Array.from(value), currentValues, getAsyncContent)})`;
		case "[object String]": return typeof value === "string" ? safeJsonStringify$1(value) : `new String(${safeJsonStringify$1(value)})`;
		case "[object Symbol]": {
			const s = value;
			if (SSymbol.keyFor(s) !== void 0) return `Symbol.for(${safeJsonStringify$1(SSymbol.keyFor(s))})`;
			const desc = getSymbolDescription(s);
			if (desc === null) return "Symbol()";
			return s === (desc.startsWith("Symbol.") && SSymbol[desc.substring(7)]) ? desc : `Symbol(${safeJsonStringify$1(desc)})`;
		}
		case "[object Promise]": {
			const promiseContent = getAsyncContent(value);
			switch (promiseContent.state) {
				case "fulfilled": return `Promise.resolve(${stringifyInternal(promiseContent.value, currentValues, getAsyncContent)})`;
				case "rejected": return `Promise.reject(${stringifyInternal(promiseContent.value, currentValues, getAsyncContent)})`;
				case "pending": return `new Promise(() => {/*pending*/})`;
				default: return `new Promise(() => {/*unknown*/})`;
			}
		}
		case "[object Error]":
			if (value instanceof Error) return `new Error(${stringifyInternal(value.message, currentValues, getAsyncContent)})`;
			break;
		case "[object Undefined]": return `undefined`;
		case "[object Int8Array]":
		case "[object Uint8Array]":
		case "[object Uint8ClampedArray]":
		case "[object Int16Array]":
		case "[object Uint16Array]":
		case "[object Int32Array]":
		case "[object Uint32Array]":
		case "[object Float32Array]":
		case "[object Float64Array]":
		case "[object BigInt64Array]":
		case "[object BigUint64Array]": {
			if (typeof safeBufferIsBuffer === "function" && safeBufferIsBuffer(value)) return `Buffer.from(${value.buffer.detached ? "/*detached ArrayBuffer*/" : stringifyInternal(safeArrayFrom(value.values()), currentValues, getAsyncContent)})`;
			const valuePrototype = safeObjectGetPrototypeOf$2(value);
			const className = valuePrototype && valuePrototype.constructor && valuePrototype.constructor.name;
			if (typeof className === "string") {
				const typedArray = value;
				if (typedArray.buffer.detached) return `${className}.from(/*detached ArrayBuffer*/)`;
				const valuesFromTypedArr = typedArray.values();
				return `${className}.from(${stringifyInternal(safeArrayFrom(valuesFromTypedArr), currentValues, getAsyncContent)})`;
			}
			break;
		}
	}
	try {
		return value.toString();
	} catch {
		return safeToString(value);
	}
}
/**
* Convert any value to its fast-check string representation
*
* @param value - Value to be converted into a string
*
* @remarks Since 1.15.0
* @public
*/
function stringify(value) {
	return stringifyInternal(value, [], () => ({
		state: "unknown",
		value: void 0
	}));
}
/**
* Mid-way between stringify and asyncStringify
*
* If the value can be stringified in a synchronous way then it returns a string.
* Otherwise, it tries to go further in investigations and return a Promise<string>.
*
* Not publicly exposed yet!
*
* @internal
*/
function possiblyAsyncStringify(value) {
	const stillPendingMarker = SSymbol();
	const pendingPromisesForCache = [];
	const cache = new SMap$2();
	function createDelay0() {
		let handleId = null;
		const cancel = () => {
			if (handleId !== null) clearTimeout(handleId);
		};
		return {
			delay: new Promise((resolve) => {
				handleId = setTimeout(() => {
					handleId = null;
					resolve(stillPendingMarker);
				}, 0);
			}),
			cancel
		};
	}
	const unknownState = {
		state: "unknown",
		value: void 0
	};
	const getAsyncContent = function getAsyncContent(data) {
		const cacheKey = data;
		if (cache.has(cacheKey)) return cache.get(cacheKey);
		const delay0 = createDelay0();
		const p = asyncToStringMethod in data ? Promise.resolve().then(() => data[asyncToStringMethod]()) : data;
		p.catch(() => {});
		pendingPromisesForCache.push(Promise.race([p, delay0.delay]).then((successValue) => {
			if (successValue === stillPendingMarker) cache.set(cacheKey, {
				state: "pending",
				value: void 0
			});
			else cache.set(cacheKey, {
				state: "fulfilled",
				value: successValue
			});
			delay0.cancel();
		}, (errorValue) => {
			cache.set(cacheKey, {
				state: "rejected",
				value: errorValue
			});
			delay0.cancel();
		}));
		cache.set(cacheKey, unknownState);
		return unknownState;
	};
	function loop() {
		const stringifiedValue = stringifyInternal(value, [], getAsyncContent);
		if (pendingPromisesForCache.length === 0) return stringifiedValue;
		return Promise.all(pendingPromisesForCache.splice(0)).then(loop);
	}
	return loop();
}
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
async function asyncStringify(value) {
	return Promise.resolve(possiblyAsyncStringify(value));
}
//#endregion
//#region src/check/property/IgnoreEqualValuesProperty.ts
/** @internal */
function fromSyncCached(cachedValue) {
	return cachedValue === null ? new PreconditionFailure() : cachedValue;
}
function fromCached$1(...data) {
	if (data[1]) return data[0].then(fromSyncCached);
	return fromSyncCached(data[0]);
}
/** @internal */
function fromCachedUnsafe(cachedValue, isAsync) {
	return fromCached$1(cachedValue, isAsync);
}
/** @internal */
var IgnoreEqualValuesProperty = class {
	constructor(property, skipRuns) {
		this.property = property;
		this.skipRuns = skipRuns;
		this.coveredCases = /* @__PURE__ */ new Map();
	}
	isAsync() {
		return this.property.isAsync();
	}
	generate(mrng, runId) {
		return this.property.generate(mrng, runId);
	}
	shrink(value) {
		return this.property.shrink(value);
	}
	run(v) {
		const stringifiedValue = stringify(v);
		if (this.coveredCases.has(stringifiedValue)) {
			const lastOutput = this.coveredCases.get(stringifiedValue);
			if (!this.skipRuns) return lastOutput;
			return fromCachedUnsafe(lastOutput, this.property.isAsync());
		}
		const out = this.property.run(v);
		this.coveredCases.set(stringifiedValue, out);
		return out;
	}
	runBeforeEach() {
		return this.property.runBeforeEach();
	}
	runAfterEach() {
		return this.property.runAfterEach();
	}
};
//#endregion
//#region src/check/runner/DecorateProperty.ts
const safeDateNow = Date.now;
const safeSetTimeout$2 = setTimeout;
const safeClearTimeout$2 = clearTimeout;
/** @internal */
function decorateProperty(rawProperty, qParams) {
	let prop = rawProperty;
	if (rawProperty.isAsync() && qParams.timeout !== void 0) prop = new TimeoutProperty(prop, qParams.timeout, safeSetTimeout$2, safeClearTimeout$2);
	if (qParams.unbiased) prop = new UnbiasedProperty(prop);
	if (qParams.skipAllAfterTimeLimit !== void 0) prop = new SkipAfterProperty(prop, safeDateNow, qParams.skipAllAfterTimeLimit, false, safeSetTimeout$2, safeClearTimeout$2);
	if (qParams.interruptAfterTimeLimit !== void 0) prop = new SkipAfterProperty(prop, safeDateNow, qParams.interruptAfterTimeLimit, true, safeSetTimeout$2, safeClearTimeout$2);
	if (qParams.skipEqualValues) prop = new IgnoreEqualValuesProperty(prop, true);
	if (qParams.ignoreEqualValues) prop = new IgnoreEqualValuesProperty(prop, false);
	return prop;
}
//#endregion
//#region src/check/runner/reporter/ExecutionStatus.ts
/**
* Status of the execution of the property
* @remarks Since 1.9.0
* @public
*/
let ExecutionStatus = /* @__PURE__ */ function(ExecutionStatus) {
	ExecutionStatus[ExecutionStatus["Success"] = 0] = "Success";
	ExecutionStatus[ExecutionStatus["Skipped"] = -1] = "Skipped";
	ExecutionStatus[ExecutionStatus["Failure"] = 1] = "Failure";
	return ExecutionStatus;
}({});
//#endregion
//#region src/check/runner/reporter/RunExecution.ts
/**
* Report the status of a run
*
* It receives notification from the runner in case of failures
*
* @internal
*/
var RunExecution = class RunExecution {
	constructor(verbosity, interruptedAsFailure) {
		this.verbosity = verbosity;
		this.interruptedAsFailure = interruptedAsFailure;
		this.rootExecutionTrees = [];
		this.currentLevelExecutionTrees = this.rootExecutionTrees;
		this.failure = null;
		this.numSkips = 0;
		this.numSuccesses = 0;
		this.interrupted = false;
	}
	appendExecutionTree(status, value) {
		const currentTree = {
			status,
			value,
			children: []
		};
		this.currentLevelExecutionTrees.push(currentTree);
		return currentTree;
	}
	fail(value, id, failure) {
		if (this.verbosity >= 1) {
			const currentTree = this.appendExecutionTree(1, value);
			this.currentLevelExecutionTrees = currentTree.children;
		}
		if (this.pathToFailure === void 0) this.pathToFailure = `${id}`;
		else this.pathToFailure += `:${id}`;
		this.value = value;
		this.failure = failure;
	}
	skip(value) {
		if (this.verbosity >= 2) this.appendExecutionTree(-1, value);
		if (this.pathToFailure === void 0) ++this.numSkips;
	}
	success(value) {
		if (this.verbosity >= 2) this.appendExecutionTree(0, value);
		if (this.pathToFailure === void 0) ++this.numSuccesses;
	}
	interrupt() {
		this.interrupted = true;
	}
	isSuccess() {
		return this.pathToFailure === void 0;
	}
	firstFailure() {
		return this.pathToFailure !== void 0 ? +safeSplit(this.pathToFailure, ":")[0] : -1;
	}
	numShrinks() {
		return this.pathToFailure !== void 0 ? safeSplit(this.pathToFailure, ":").length - 1 : 0;
	}
	extractFailures() {
		if (this.isSuccess()) return [];
		const failures = [];
		let cursor = this.rootExecutionTrees;
		while (cursor.length > 0 && cursor[cursor.length - 1].status === 1) {
			const failureTree = cursor[cursor.length - 1];
			failures.push(failureTree.value);
			cursor = failureTree.children;
		}
		return failures;
	}
	static mergePaths(offsetPath, path) {
		if (offsetPath.length === 0) return path;
		const offsetItems = offsetPath.split(":");
		const remainingItems = path.split(":");
		const middle = +offsetItems[offsetItems.length - 1] + +remainingItems[0];
		return [
			...offsetItems.slice(0, offsetItems.length - 1),
			`${middle}`,
			...remainingItems.slice(1)
		].join(":");
	}
	toRunDetails(seed, basePath, maxSkips, qParams) {
		if (!this.isSuccess()) return {
			failed: true,
			interrupted: this.interrupted,
			numRuns: this.firstFailure() + 1 - this.numSkips,
			numSkips: this.numSkips,
			numShrinks: this.numShrinks(),
			seed,
			counterexample: this.value,
			counterexamplePath: RunExecution.mergePaths(basePath, this.pathToFailure),
			errorInstance: this.failure.error,
			failures: this.extractFailures(),
			executionSummary: this.rootExecutionTrees,
			verbose: this.verbosity,
			runConfiguration: qParams.toParameters()
		};
		const considerInterruptedAsFailure = this.interruptedAsFailure || this.numSuccesses === 0;
		return {
			failed: this.numSkips > maxSkips || this.interrupted && considerInterruptedAsFailure,
			interrupted: this.interrupted,
			numRuns: this.numSuccesses,
			numSkips: this.numSkips,
			numShrinks: 0,
			seed,
			counterexample: null,
			counterexamplePath: null,
			error: null,
			errorInstance: null,
			failures: [],
			executionSummary: this.rootExecutionTrees,
			verbose: this.verbosity,
			runConfiguration: qParams.toParameters()
		};
	}
};
//#endregion
//#region src/check/runner/RunnerIterator.ts
/**
* Responsible for the iteration logic
*
* Workflow:
* 1- Call to `next` gives back the value to test
* 2- Call to `handleResult` takes into account the execution status
* 3- Back to 1
*
* @internal
*/
var RunnerIterator = class {
	constructor(sourceValues, shrink, verbose, interruptedAsFailure) {
		this.sourceValues = sourceValues;
		this.shrink = shrink;
		this.runExecution = new RunExecution(verbose, interruptedAsFailure);
		this.currentIdx = -1;
		this.nextValues = sourceValues;
	}
	[Symbol.iterator]() {
		return this;
	}
	next() {
		const nextValue = this.nextValues.next();
		if (nextValue.done || this.runExecution.interrupted) return {
			done: true,
			value: void 0
		};
		this.currentValue = nextValue.value;
		++this.currentIdx;
		return {
			done: false,
			value: nextValue.value.value_
		};
	}
	handleResult(result) {
		if (result !== null && typeof result === "object" && !PreconditionFailure.isFailure(result)) {
			this.runExecution.fail(this.currentValue.value_, this.currentIdx, result);
			this.currentIdx = -1;
			this.nextValues = this.shrink(this.currentValue);
		} else if (result !== null) {
			if (!result.interruptExecution) {
				this.runExecution.skip(this.currentValue.value_);
				this.sourceValues.skippedOne();
			} else this.runExecution.interrupt();
		} else this.runExecution.success(this.currentValue.value_);
	}
};
//#endregion
//#region src/check/runner/SourceValuesIterator.ts
/**
* Try to extract maxInitialIterations non-skipped values
* with a maximal number of remainingSkips skipped values
* from initialValues source
* @internal
*/
var SourceValuesIterator = class {
	constructor(initialValues, maxInitialIterations, remainingSkips) {
		this.initialValues = initialValues;
		this.maxInitialIterations = maxInitialIterations;
		this.remainingSkips = remainingSkips;
	}
	[Symbol.iterator]() {
		return this;
	}
	next() {
		if (--this.maxInitialIterations !== -1 && this.remainingSkips >= 0) {
			const n = this.initialValues.next();
			if (!n.done) return {
				value: n.value,
				done: false
			};
		}
		return {
			value: void 0,
			done: true
		};
	}
	skippedOne() {
		--this.remainingSkips;
		++this.maxInitialIterations;
	}
};
//#endregion
//#region src/random/generator/Random.ts
const MIN_INT = -2147483648;
const MAX_INT = 2147483647;
const DBL_FACTOR = Math.pow(2, 27);
const DBL_DIVISOR = Math.pow(2, -53);
/**
* Wrapper around an instance of a `pure-rand`'s random number generator
* offering a simpler interface to deal with random with impure patterns
*
* @public
*/
var Random = class Random {
	/**
	* Create a mutable random number generator by cloning the passed one and mutate it
	* @param sourceRng - Immutable random generator from pure-rand library, will not be altered (a clone will be)
	*/
	constructor(sourceRng) {
		this.internalRng = adaptRandomGenerator(sourceRng.clone());
	}
	/**
	* Clone the random number generator
	*/
	clone() {
		return new Random(this.internalRng);
	}
	/**
	* Generate an integer having `bits` random bits
	* @param bits - Number of bits to generate
	* @deprecated Prefer {@link nextInt} with explicit bounds: `nextInt(0, (1 << bits) - 1)`
	*/
	next(bits) {
		return (0, pure_rand_distribution_uniformInt.uniformInt)(this.internalRng, 0, (1 << bits) - 1);
	}
	/**
	* Generate a random boolean
	* @deprecated Prefer {@link nextInt} with explicit bounds: `nextInt(0, 1) === 1`
	*/
	nextBoolean() {
		return (0, pure_rand_distribution_uniformInt.uniformInt)(this.internalRng, 0, 1) === 1;
	}
	nextInt(min, max) {
		return (0, pure_rand_distribution_uniformInt.uniformInt)(this.internalRng, min === void 0 ? MIN_INT : min, max === void 0 ? MAX_INT : max);
	}
	/**
	* Generate a random bigint between min (included) and max (included)
	* @param min - Minimal bigint value
	* @param max - Maximal bigint value
	*/
	nextBigInt(min, max) {
		return (0, pure_rand_distribution_uniformBigInt.uniformBigInt)(this.internalRng, min, max);
	}
	/**
	* Generate a random floating point number between 0.0 (included) and 1.0 (excluded)
	* @deprecated Prefer {@link nextInt} with explicit bounds
	*/
	nextDouble() {
		const a = this.next(26);
		const b = this.next(27);
		return (a * DBL_FACTOR + b) * DBL_DIVISOR;
	}
	/**
	* Extract the internal state of the internal RandomGenerator backing the current instance of Random
	*/
	getState() {
		if ("getState" in this.internalRng && typeof this.internalRng.getState === "function") return this.internalRng.getState();
	}
};
//#endregion
//#region src/check/runner/Tosser.ts
/**
* Extracting tossNext out of toss was dropping some bailout reasons on v8 side
* @internal
*/
function tossNext(generator, rng, index) {
	rng.jump();
	return generator.generate(new Random(rng), index);
}
/** @internal */
function* toss(generator, seed, random, examples) {
	for (let idx = 0; idx !== examples.length; ++idx) yield new Value(examples[idx], void 0);
	for (let idx = 0, rng = random(seed);; ++idx) yield tossNext(generator, rng, idx);
}
/** @internal */
function lazyGenerate(generator, rng, idx) {
	return () => generator.generate(new Random(rng), idx);
}
/** @internal */
function* lazyToss(generator, seed, random, examples) {
	yield* safeMap(examples, (e) => () => new Value(e, void 0));
	let idx = 0;
	const rng = adaptRandomGenerator(random(seed));
	for (;;) {
		rng.jump();
		yield lazyGenerate(generator, rng, idx++);
	}
}
//#endregion
//#region src/check/runner/utils/PathWalker.ts
/** @internal */
function produce(producer) {
	return producer();
}
/** @internal */
function pathWalk(path, initialProducers, shrink) {
	const producers = initialProducers;
	const segments = path.split(":").map((text) => +text);
	if (segments.length === 0) return producers.map(produce);
	if (!segments.every((v) => !Number.isNaN(v))) throw new Error(`Unable to replay, got invalid path=${path}`);
	let values = producers.drop(segments[0]).map(produce);
	for (const s of segments.slice(1)) {
		const valueToShrink = values.getNthOrLast(0);
		if (valueToShrink === null) throw new Error(`Unable to replay, got wrong path=${path}`);
		values = shrink(valueToShrink).drop(s);
	}
	return values;
}
//#endregion
//#region src/check/runner/utils/RunDetailsFormatter.ts
const safeObjectAssign$6 = Object.assign;
/** @internal */
function formatHints(hints) {
	if (hints.length === 1) return `Hint: ${hints[0]}`;
	return hints.map((h, idx) => `Hint (${idx + 1}): ${h}`).join("\n");
}
/** @internal */
function formatFailures(failures, stringifyOne) {
	return `Encountered failures were:\n- ${failures.map(stringifyOne).join("\n- ")}`;
}
/** @internal */
function formatExecutionSummary(executionTrees, stringifyOne) {
	const summaryLines = [];
	const remainingTreesAndDepth = [];
	for (let i = executionTrees.length - 1; i >= 0; --i) remainingTreesAndDepth.push({
		depth: 1,
		tree: executionTrees[i]
	});
	while (remainingTreesAndDepth.length !== 0) {
		const currentTreeAndDepth = remainingTreesAndDepth.pop();
		const currentTree = currentTreeAndDepth.tree;
		const currentDepth = currentTreeAndDepth.depth;
		const statusIcon = currentTree.status === 0 ? "\x1B[32m√\x1B[0m" : currentTree.status === 1 ? "\x1B[31m×\x1B[0m" : "\x1B[33m!\x1B[0m";
		const leftPadding = currentDepth !== 0 ? ". ".repeat(currentDepth - 1) : "";
		summaryLines.push(`${leftPadding}${statusIcon} ${stringifyOne(currentTree.value)}`);
		for (let i = currentTree.children.length - 1; i >= 0; --i) remainingTreesAndDepth.push({
			depth: currentDepth + 1,
			tree: currentTree.children[i]
		});
	}
	return `Execution summary:\n${summaryLines.join("\n")}`;
}
/** @internal */
function preFormatTooManySkipped(out, stringifyOne) {
	const message = `Failed to run property, too many pre-condition failures encountered\n{ seed: ${out.seed} }\n\nRan ${out.numRuns} time(s)\nSkipped ${out.numSkips} time(s)`;
	let details = null;
	const hints = ["Try to reduce the number of rejected values by combining map, chain and built-in arbitraries", "Increase failure tolerance by setting maxSkipsPerRun to an higher value"];
	if (out.verbose >= 2) details = formatExecutionSummary(out.executionSummary, stringifyOne);
	else safePush(hints, "Enable verbose mode at level VeryVerbose in order to check all generated values and their associated status");
	return {
		message,
		details,
		hints
	};
}
/** @internal */
function prettyError(errorInstance) {
	if (errorInstance instanceof SError && errorInstance.stack !== void 0) return errorInstance.stack;
	try {
		return SString(errorInstance);
	} catch (_err) {}
	if (errorInstance instanceof SError) try {
		return safeErrorToString(errorInstance);
	} catch (_err) {}
	if (errorInstance !== null && typeof errorInstance === "object") try {
		return safeToString(errorInstance);
	} catch (_err) {}
	return "Failed to serialize errorInstance";
}
/** @internal */
function preFormatFailure(out, stringifyOne) {
	const messageErrorPart = out.runConfiguration.includeErrorInReport ? `\nGot ${safeReplace(prettyError(out.errorInstance), /^Error: /, "error: ")}` : "";
	const message = `Property failed after ${out.numRuns} tests\n{ seed: ${out.seed}, path: "${out.counterexamplePath}", endOnFailure: true }\nCounterexample: ${stringifyOne(out.counterexample)}\nShrunk ${out.numShrinks} time(s)${messageErrorPart}`;
	let details = null;
	const hints = [];
	if (out.verbose >= 2) details = formatExecutionSummary(out.executionSummary, stringifyOne);
	else if (out.verbose === 1) details = formatFailures(out.failures, stringifyOne);
	else safePush(hints, "Enable verbose mode in order to have the list of all failing values encountered during the run");
	return {
		message,
		details,
		hints
	};
}
/** @internal */
function preFormatEarlyInterrupted(out, stringifyOne) {
	const message = `Property interrupted after ${out.numRuns} tests\n{ seed: ${out.seed} }`;
	let details = null;
	const hints = [];
	if (out.verbose >= 2) details = formatExecutionSummary(out.executionSummary, stringifyOne);
	else safePush(hints, "Enable verbose mode at level VeryVerbose in order to check all generated values and their associated status");
	return {
		message,
		details,
		hints
	};
}
/** @internal */
function defaultReportMessageInternal(out, stringifyOne) {
	if (!out.failed) return;
	const { message, details, hints } = out.counterexamplePath === null ? out.interrupted ? preFormatEarlyInterrupted(out, stringifyOne) : preFormatTooManySkipped(out, stringifyOne) : preFormatFailure(out, stringifyOne);
	let errorMessage = message;
	if (details !== null) errorMessage += `\n\n${details}`;
	if (hints.length > 0) errorMessage += `\n\n${formatHints(hints)}`;
	return errorMessage;
}
function defaultReportMessage(out) {
	return defaultReportMessageInternal(out, stringify);
}
async function asyncDefaultReportMessage(out) {
	const pendingStringifieds = [];
	function stringifyOne(value) {
		const stringified = possiblyAsyncStringify(value);
		if (typeof stringified === "string") return stringified;
		pendingStringifieds.push(Promise.all([value, stringified]));
		return "…";
	}
	const firstTryMessage = defaultReportMessageInternal(out, stringifyOne);
	if (pendingStringifieds.length === 0) return firstTryMessage;
	const registeredValues = new SMap$2(await Promise.all(pendingStringifieds));
	function stringifySecond(value) {
		const asyncStringifiedIfRegistered = safeMapGet(registeredValues, value);
		if (asyncStringifiedIfRegistered !== void 0) return asyncStringifiedIfRegistered;
		return stringify(value);
	}
	return defaultReportMessageInternal(out, stringifySecond);
}
/** @internal */
function buildError(errorMessage, out) {
	if (out.runConfiguration.includeErrorInReport) throw new SError(errorMessage);
	const error = new SError(errorMessage, { cause: out.errorInstance });
	if (!("cause" in error)) safeObjectAssign$6(error, { cause: out.errorInstance });
	return error;
}
/** @internal */
function throwIfFailed(out) {
	if (!out.failed) return;
	throw buildError(defaultReportMessage(out), out);
}
/** @internal */
async function asyncThrowIfFailed(out) {
	if (!out.failed) return;
	throw buildError(await asyncDefaultReportMessage(out), out);
}
/**
* In case this code has to be executed synchronously the caller
* has to make sure that no asyncReporter has been defined
* otherwise it might trigger an unchecked promise
* @internal
*/
function reportRunDetails(out) {
	if (out.runConfiguration.asyncReporter) return out.runConfiguration.asyncReporter(out);
	else if (out.runConfiguration.reporter) return out.runConfiguration.reporter(out);
	else return throwIfFailed(out);
}
/**
* In case this code has to be executed synchronously the caller
* has to make sure that no asyncReporter has been defined
* otherwise it might trigger an unchecked promise
* @internal
*/
async function asyncReportRunDetails(out) {
	if (out.runConfiguration.asyncReporter) return out.runConfiguration.asyncReporter(out);
	else if (out.runConfiguration.reporter) return out.runConfiguration.reporter(out);
	else return asyncThrowIfFailed(out);
}
//#endregion
//#region src/check/runner/configuration/GlobalPlugins.ts
const globalPlugins = [];
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
function installGlobalPlugin(plugin) {
	globalPlugins.push(plugin);
}
function readInstalledGlobalPlugins() {
	return globalPlugins;
}
//#endregion
//#region src/check/runner/Runner.ts
const SMap$1 = Map;
/** @internal */
function runIt(run, shrink, sourceValues, verbose, interruptedAsFailure) {
	const runner = new RunnerIterator(sourceValues, shrink, verbose, interruptedAsFailure);
	for (const v of runner) {
		const out = run(v);
		runner.handleResult(out);
	}
	return runner.runExecution;
}
function propertyExecution(property, v) {
	property.runBeforeEach();
	const out = property.run(v);
	property.runAfterEach();
	return out;
}
/** @internal */
async function asyncRunIt(run, shrink, sourceValues, verbose, interruptedAsFailure) {
	const runner = new RunnerIterator(sourceValues, shrink, verbose, interruptedAsFailure);
	for (const v of runner) {
		const out = await run(v);
		runner.handleResult(out);
	}
	return runner.runExecution;
}
async function asyncPropertyExecution(property, v) {
	await property.runBeforeEach();
	const out = await property.run(v);
	await property.runAfterEach();
	return out;
}
function runPluginCompletionHooksSync(pluginInstances, runDetails) {
	let interceptedOnce = false;
	let interceptedError = void 0;
	for (let index = 0; index !== pluginInstances.length; ++index) {
		const instance = pluginInstances[index];
		if (instance.onAllRunsComplete !== void 0) try {
			instance.onAllRunsComplete(runDetails);
		} catch (error) {
			if (!interceptedOnce) {
				interceptedOnce = true;
				interceptedError = error;
			}
		}
	}
	for (let index = pluginInstances.length - 1; index >= 0; --index) {
		const instance = pluginInstances[index];
		if (instance.afterAll !== void 0) try {
			instance.afterAll();
		} catch (error) {
			if (!interceptedOnce) {
				interceptedOnce = true;
				interceptedError = error;
			}
		}
	}
	if (interceptedOnce) throw interceptedError;
}
function runPluginCompletionHooks(pluginInstances, runDetailsPromise) {
	const followUps = [];
	for (let index = 0; index !== pluginInstances.length; ++index) {
		const instance = pluginInstances[index];
		if (instance.onAllRunsComplete !== void 0) followUps.push((runDetails) => instance.onAllRunsComplete(runDetails));
	}
	for (let index = pluginInstances.length - 1; index >= 0; --index) {
		const instance = pluginInstances[index];
		if (instance.afterAll !== void 0) followUps.push(() => instance.afterAll());
	}
	if (followUps.length === 0) return runDetailsPromise;
	return runDetailsPromise.then(async (details) => {
		let interceptedOnce = false;
		let interceptedError = void 0;
		for (const followUp of followUps) try {
			const out = followUp(details);
			if (out !== void 0) await out;
		} catch (error) {
			if (!interceptedOnce) {
				interceptedOnce = true;
				interceptedError = error;
			}
		}
		if (interceptedOnce) throw interceptedError;
		return details;
	});
}
function check(rawProperty, params) {
	if (rawProperty === null || rawProperty === void 0 || rawProperty.generate === null || rawProperty.generate === void 0) throw new Error("Invalid property encountered, please use a valid property");
	if (rawProperty.run === null || rawProperty.run === void 0) throw new Error("Invalid property encountered, please use a valid property not an arbitrary");
	const qParams = read({
		...readConfigureGlobal(),
		...params
	});
	if (qParams.reporter !== void 0 && qParams.asyncReporter !== void 0) throw new Error("Invalid parameters encountered, reporter and asyncReporter cannot be specified together");
	if (qParams.asyncReporter !== void 0 && !rawProperty.isAsync()) throw new Error("Invalid parameters encountered, only asyncProperty can be used when asyncReporter specified");
	const property = decorateProperty(rawProperty, qParams);
	const globalPlugins = readInstalledGlobalPlugins();
	const localPlugins = qParams.plugins;
	const pluginStore = new SMap$1();
	const pluginInstances = [];
	for (let index = 0; index !== globalPlugins.length; ++index) pluginInstances.push(globalPlugins[index](index, pluginStore));
	for (let index = 0; index !== localPlugins.length; ++index) pluginInstances.push(localPlugins[index](globalPlugins.length + index, pluginStore));
	let surchargedGenerate = void 0;
	let run = property.isAsync() ? async (v) => asyncPropertyExecution(property, v) : (v) => propertyExecution(property, v);
	for (let index = pluginInstances.length - 1; index >= 0; --index) {
		const pluginInstance = pluginInstances[index];
		if (pluginInstance.decorateGenerate !== void 0) {
			if (surchargedGenerate === void 0) surchargedGenerate = (mrng, runId) => property.generate(mrng, runId);
			surchargedGenerate = pluginInstance.decorateGenerate(surchargedGenerate);
		}
		if (pluginInstance.decorateRun !== void 0) run = pluginInstance.decorateRun(run);
	}
	const generator = surchargedGenerate === void 0 ? property : { generate: surchargedGenerate };
	const maxInitialIterations = qParams.path.length === 0 || qParams.path.indexOf(":") === -1 ? qParams.numRuns : -1;
	const maxSkips = qParams.numRuns * qParams.maxSkipsPerRun;
	const shrink = (...args) => property.shrink(...args);
	const sourceValues = new SourceValuesIterator(qParams.path.length === 0 ? toss(generator, qParams.seed, qParams.randomType, qParams.examples) : pathWalk(qParams.path, stream(lazyToss(generator, qParams.seed, qParams.randomType, qParams.examples)), shrink), maxInitialIterations, maxSkips);
	const finalShrink = !qParams.endOnFailure ? shrink : Stream.nil;
	if (property.isAsync()) return runPluginCompletionHooks(pluginInstances, asyncRunIt(run, finalShrink, sourceValues, qParams.verbose, qParams.markInterruptAsFailure).then((e) => e.toRunDetails(qParams.seed, qParams.path, maxSkips, qParams)));
	const out = runIt(run, finalShrink, sourceValues, qParams.verbose, qParams.markInterruptAsFailure).toRunDetails(qParams.seed, qParams.path, maxSkips, qParams);
	runPluginCompletionHooksSync(pluginInstances, out);
	return out;
}
function assert(property, params) {
	const out = check(property, params);
	if (property.isAsync()) return out.then(asyncReportRunDetails);
	else reportRunDetails(out);
}
//#endregion
//#region src/check/runner/Sampler.ts
/** @internal */
function toProperty(generator, qParams) {
	const prop = !Object.prototype.hasOwnProperty.call(generator, "isAsync") ? new Property(generator, () => true) : generator;
	return qParams.unbiased === true ? new UnbiasedProperty(prop) : prop;
}
/** @internal */
function streamSample(generator, params) {
	const qParams = read(typeof params === "number" ? {
		...readConfigureGlobal(),
		numRuns: params
	} : {
		...readConfigureGlobal(),
		...params
	});
	const nextProperty = toProperty(generator, qParams);
	const shrink = nextProperty.shrink.bind(nextProperty);
	return (qParams.path.length === 0 ? stream(toss(nextProperty, qParams.seed, qParams.randomType, qParams.examples)) : pathWalk(qParams.path, stream(lazyToss(nextProperty, qParams.seed, qParams.randomType, qParams.examples)), shrink)).take(qParams.numRuns).map((s) => s.value_);
}
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
function sample(generator, params) {
	return [...streamSample(generator, params)];
}
/** @internal */
function round2(n) {
	return (Math.round(n * 100) / 100).toFixed(2);
}
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
function statistics(generator, classify, params) {
	const qParams = read(typeof params === "number" ? {
		...readConfigureGlobal(),
		numRuns: params
	} : {
		...readConfigureGlobal(),
		...params
	});
	const recorded = {};
	for (const g of streamSample(generator, params)) {
		const out = classify(g);
		const categories = Array.isArray(out) ? out : [out];
		for (const c of categories) recorded[c] = (recorded[c] || 0) + 1;
	}
	const data = Object.entries(recorded).sort((a, b) => b[1] - a[1]).map((i) => [i[0], `${round2(i[1] * 100 / qParams.numRuns)}%`]);
	const longestName = data.map((i) => i[0].length).reduce((p, c) => Math.max(p, c), 0);
	const longestPercent = data.map((i) => i[1].length).reduce((p, c) => Math.max(p, c), 0);
	for (const item of data) qParams.logger(`${item[0].padEnd(longestName, ".")}..${item[1].padStart(longestPercent, ".")}`);
}
//#endregion
//#region src/arbitrary/_internals/builders/GeneratorValueBuilder.ts
const safeObjectAssign$5 = Object.assign;
/**
* An internal builder of values of type {@link GeneratorValue}
* @internal
*/
function buildGeneratorValue(mrng, biasFactor, computePreBuiltValues, arbitraryCache) {
	const preBuiltValues = computePreBuiltValues();
	let localMrng = mrng.clone();
	const context = {
		mrng: mrng.clone(),
		biasFactor,
		history: []
	};
	const valueFunction = (arb) => {
		const preBuiltValue = preBuiltValues[context.history.length];
		if (preBuiltValue !== void 0 && preBuiltValue.arb === arb) {
			const value = preBuiltValue.value;
			safePush(context.history, {
				arb,
				value,
				context: preBuiltValue.context,
				mrng: preBuiltValue.mrng
			});
			localMrng = preBuiltValue.mrng.clone();
			return value;
		}
		const g = arb.generate(localMrng, biasFactor);
		safePush(context.history, {
			arb,
			value: g.value_,
			context: g.context,
			mrng: localMrng.clone()
		});
		return g.value;
	};
	const memoedValueFunction = (arb, ...args) => {
		return valueFunction(arbitraryCache(arb, args));
	};
	return new Value(safeObjectAssign$5(memoedValueFunction, {
		values() {
			return safeMap(context.history, (c) => c.value);
		},
		[cloneMethod]() {
			return buildGeneratorValue(mrng, biasFactor, computePreBuiltValues, arbitraryCache).value;
		},
		[toStringMethod]() {
			return stringify(safeMap(context.history, (c) => c.value));
		}
	}), context);
}
//#endregion
//#region src/arbitrary/_internals/builders/StableArbitraryGeneratorCache.ts
const safeArrayIsArray$3 = Array.isArray;
const safeObjectKeys$4 = Object.keys;
const safeObjectIs$7 = Object.is;
function buildStableArbitraryGeneratorCache(isEqual) {
	const previousCallsPerBuilder = new SMap$2();
	return function stableArbitraryGeneratorCache(builder, args) {
		const entriesForBuilder = safeMapGet(previousCallsPerBuilder, builder);
		if (entriesForBuilder === void 0) {
			const newValue = builder(...args);
			safeMapSet(previousCallsPerBuilder, builder, [{
				args,
				value: newValue
			}]);
			return newValue;
		}
		const safeEntriesForBuilder = entriesForBuilder;
		for (const entry of safeEntriesForBuilder) if (isEqual(args, entry.args)) return entry.value;
		const newValue = builder(...args);
		safePush(safeEntriesForBuilder, {
			args,
			value: newValue
		});
		return newValue;
	};
}
function naiveIsEqual(v1, v2) {
	if (v1 !== null && typeof v1 === "object" && v2 !== null && typeof v2 === "object") {
		if (safeArrayIsArray$3(v1)) {
			if (!safeArrayIsArray$3(v2)) return false;
			if (v1.length !== v2.length) return false;
		} else if (safeArrayIsArray$3(v2)) return false;
		if (safeObjectKeys$4(v1).length !== safeObjectKeys$4(v2).length) return false;
		for (const index in v1) {
			if (!(index in v2)) return false;
			if (!naiveIsEqual(v1[index], v2[index])) return false;
		}
		return true;
	} else return safeObjectIs$7(v1, v2);
}
//#endregion
//#region src/arbitrary/_internals/GeneratorArbitrary.ts
/**
* The generator arbitrary is responsible to generate instances of {@link GeneratorValue}.
* These instances can be used to produce "random values" within the tests themselves while still
* providing a bit of shrinking capabilities (not all).
*/
var GeneratorArbitrary = class extends Arbitrary {
	constructor(..._args) {
		super(..._args);
		this.arbitraryCache = buildStableArbitraryGeneratorCache(naiveIsEqual);
	}
	generate(mrng, biasFactor) {
		return buildGeneratorValue(mrng, biasFactor, () => [], this.arbitraryCache);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	shrink(_value, context) {
		if (context === void 0) return Stream.nil();
		const safeContext = context;
		const mrng = safeContext.mrng;
		const biasFactor = safeContext.biasFactor;
		const history = safeContext.history;
		return tupleShrink(history.map((c) => c.arb), history.map((c) => c.value), history.map((c) => c.context)).map((shrink) => {
			function computePreBuiltValues() {
				const subValues = shrink.value;
				const subContexts = shrink.context;
				return safeMap(history, (entry, index) => ({
					arb: entry.arb,
					value: subValues[index],
					context: subContexts[index],
					mrng: entry.mrng
				}));
			}
			return buildGeneratorValue(mrng, biasFactor, computePreBuiltValues, this.arbitraryCache);
		});
	}
};
//#endregion
//#region src/arbitrary/gen.ts
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
function gen() {
	return new GeneratorArbitrary();
}
//#endregion
//#region src/arbitrary/_internals/helpers/BiasNumericRange.ts
const safeMathFloor$6 = Math.floor;
const safeMathLog$2 = Math.log;
/** @internal */
function integerLogLike(v) {
	return safeMathFloor$6(safeMathLog$2(v) / safeMathLog$2(2));
}
/** @internal */
function bigIntLogLike(v) {
	if (v === SBigInt(0)) return SBigInt(0);
	return SBigInt(SString(v).length);
}
function biasNumericRange(min, max, logLike) {
	if (min === max) return [{
		min,
		max
	}];
	if (min < 0 && max > 0) {
		const logMin = logLike(-min);
		const logMax = logLike(max);
		return [
			{
				min: -logMin,
				max: logMax
			},
			{
				min: max - logMax,
				max
			},
			{
				min,
				max: min + logMin
			}
		];
	}
	const logGap = logLike(max - min);
	const arbCloseToMin = {
		min,
		max: min + logGap
	};
	const arbCloseToMax = {
		min: max - logGap,
		max
	};
	return min < 0 ? [arbCloseToMax, arbCloseToMin] : [arbCloseToMin, arbCloseToMax];
}
//#endregion
//#region src/arbitrary/_internals/helpers/ShrinkInteger.ts
const safeMathCeil = Math.ceil;
const safeMathFloor$5 = Math.floor;
/** @internal */
function halvePosInteger(n) {
	return safeMathFloor$5(n / 2);
}
/** @internal */
function halveNegInteger(n) {
	return safeMathCeil(n / 2);
}
/**
* Compute shrunk values to move from current to target
* @internal
*/
function shrinkInteger(current, target, tryTargetAsap) {
	const realGap = current - target;
	function* shrinkDecr() {
		let previous = tryTargetAsap ? void 0 : target;
		const gap = tryTargetAsap ? realGap : halvePosInteger(realGap);
		for (let toremove = gap; toremove > 0; toremove = halvePosInteger(toremove)) {
			const next = toremove === realGap ? target : current - toremove;
			yield new Value(next, previous);
			previous = next;
		}
	}
	function* shrinkIncr() {
		let previous = tryTargetAsap ? void 0 : target;
		const gap = tryTargetAsap ? realGap : halveNegInteger(realGap);
		for (let toremove = gap; toremove < 0; toremove = halveNegInteger(toremove)) {
			const next = toremove === realGap ? target : current - toremove;
			yield new Value(next, previous);
			previous = next;
		}
	}
	return realGap > 0 ? stream(shrinkDecr()) : stream(shrinkIncr());
}
//#endregion
//#region src/arbitrary/_internals/IntegerArbitrary.ts
const safeMathSign = Math.sign;
const safeNumberIsInteger$6 = Number.isInteger;
const safeObjectIs$6 = Object.is;
/** @internal */
var IntegerArbitrary = class IntegerArbitrary extends Arbitrary {
	constructor(min, max) {
		super();
		this.min = min;
		this.max = max;
		this.ranges = biasNumericRange(min, max, integerLogLike);
	}
	generate(mrng, biasFactor) {
		if (biasFactor === void 0 || mrng.nextInt(1, biasFactor) !== 1) return new Value(mrng.nextInt(this.min, this.max), void 0);
		const ranges = this.ranges;
		if (ranges.length === 1) {
			const range = ranges[0];
			return new Value(mrng.nextInt(range.min, range.max), void 0);
		}
		const id = mrng.nextInt(-2 * (ranges.length - 1), ranges.length - 2);
		const range = id < 0 ? ranges[0] : ranges[id + 1];
		return new Value(mrng.nextInt(range.min, range.max), void 0);
	}
	canShrinkWithoutContext(value) {
		return typeof value === "number" && safeNumberIsInteger$6(value) && !safeObjectIs$6(value, -0) && this.min <= value && value <= this.max;
	}
	shrink(current, context) {
		if (!IntegerArbitrary.isValidContext(current, context)) return shrinkInteger(current, this.min <= 0 && this.max >= 0 ? 0 : this.min < 0 ? this.max : this.min, true);
		if (this.isLastChanceTry(current, context)) return Stream.of(new Value(context, void 0));
		return shrinkInteger(current, context, false);
	}
	isLastChanceTry(current, context) {
		if (current > 0) return current === context + 1 && current > this.min;
		if (current < 0) return current === context - 1 && current < this.max;
		return false;
	}
	static isValidContext(current, context) {
		if (context === void 0) return false;
		if (typeof context !== "number") throw new Error(`Invalid context type passed to IntegerArbitrary (#1)`);
		if (context !== 0 && safeMathSign(current) !== safeMathSign(context)) throw new Error(`Invalid context value passed to IntegerArbitrary (#2)`);
		return true;
	}
};
//#endregion
//#region src/arbitrary/integer.ts
const safeNumberIsInteger$5 = Number.isInteger;
/**
* Build fully set IntegerConstraints from a partial data
* @internal
*/
function buildCompleteIntegerConstraints(constraints) {
	return {
		min: constraints.min !== void 0 ? constraints.min : -2147483648,
		max: constraints.max !== void 0 ? constraints.max : 2147483647
	};
}
/**
* For integers between min (included) and max (included)
*
* @param constraints - Constraints to apply when building instances (since 2.6.0)
*
* @remarks Since 0.0.1
* @public
*/
function integer(constraints = {}) {
	const fullConstraints = buildCompleteIntegerConstraints(constraints);
	if (fullConstraints.min > fullConstraints.max) throw new Error("fc.integer maximum value should be equal or greater than the minimum one");
	if (!safeNumberIsInteger$5(fullConstraints.min)) throw new Error("fc.integer minimum value should be an integer");
	if (!safeNumberIsInteger$5(fullConstraints.max)) throw new Error("fc.integer maximum value should be an integer");
	return new IntegerArbitrary(fullConstraints.min, fullConstraints.max);
}
//#endregion
//#region src/arbitrary/_internals/helpers/DepthContext.ts
/**
* Internal cache for depth contexts
* @internal
*/
const depthContextCache = /* @__PURE__ */ new Map();
/**
* Get back the requested DepthContext
* @remarks Since 2.25.0
* @public
*/
function getDepthContextFor(contextMeta) {
	if (contextMeta === void 0) return { depth: 0 };
	if (typeof contextMeta !== "string") return contextMeta;
	const cachedContext = safeMapGet(depthContextCache, contextMeta);
	if (cachedContext !== void 0) return cachedContext;
	const context = { depth: 0 };
	safeMapSet(depthContextCache, contextMeta, context);
	return context;
}
/**
* Create a new and unique instance of DepthIdentifier
* that can be shared across multiple arbitraries if needed
* @public
*/
function createDepthIdentifier() {
	return { depth: 0 };
}
//#endregion
//#region src/arbitrary/_internals/implementations/NoopSlicedGenerator.ts
/** @internal */
var NoopSlicedGenerator = class {
	constructor(arb, mrng, biasFactor) {
		this.arb = arb;
		this.mrng = mrng;
		this.biasFactor = biasFactor;
	}
	attemptExact() {}
	next() {
		return this.arb.generate(this.mrng, this.biasFactor);
	}
};
//#endregion
//#region src/arbitrary/_internals/implementations/SlicedBasedGenerator.ts
const safeMathMin$5 = Math.min;
const safeMathMax$2 = Math.max;
/** @internal */
var SlicedBasedGenerator = class {
	constructor(arb, mrng, slices, biasFactor) {
		this.arb = arb;
		this.mrng = mrng;
		this.slices = slices;
		this.biasFactor = biasFactor;
		this.activeSliceIndex = 0;
		this.nextIndexInSlice = 0;
		this.lastIndexInSlice = -1;
	}
	attemptExact(targetLength) {
		if (targetLength !== 0 && this.mrng.nextInt(1, this.biasFactor) === 1) {
			const eligibleIndices = [];
			for (let index = 0; index !== this.slices.length; ++index) if (this.slices[index].length === targetLength) safePush(eligibleIndices, index);
			if (eligibleIndices.length === 0) return;
			this.activeSliceIndex = eligibleIndices[this.mrng.nextInt(0, eligibleIndices.length - 1)];
			this.nextIndexInSlice = 0;
			this.lastIndexInSlice = targetLength - 1;
		}
	}
	next() {
		if (this.nextIndexInSlice <= this.lastIndexInSlice) return new Value(this.slices[this.activeSliceIndex][this.nextIndexInSlice++], void 0);
		if (this.mrng.nextInt(1, this.biasFactor) !== 1) return this.arb.generate(this.mrng, this.biasFactor);
		this.activeSliceIndex = this.mrng.nextInt(0, this.slices.length - 1);
		const slice = this.slices[this.activeSliceIndex];
		if (this.mrng.nextInt(1, this.biasFactor) !== 1) {
			this.nextIndexInSlice = 1;
			this.lastIndexInSlice = slice.length - 1;
			return new Value(slice[0], void 0);
		}
		const rangeBoundaryA = this.mrng.nextInt(0, slice.length - 1);
		const rangeBoundaryB = this.mrng.nextInt(0, slice.length - 1);
		this.nextIndexInSlice = safeMathMin$5(rangeBoundaryA, rangeBoundaryB);
		this.lastIndexInSlice = safeMathMax$2(rangeBoundaryA, rangeBoundaryB);
		return new Value(slice[this.nextIndexInSlice++], void 0);
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/BuildSlicedGenerator.ts
/**
* Build a {@link SlicedGenerator}
*
* @param arb - Arbitrary able to generate values
* @param mrng - Random number generator
* @param slices - Slices to be used (WARNING: while we accept no slices, slices themselves must never empty)
* @param biasFactor - The current bias factor
*
* @internal
*/
function buildSlicedGenerator(arb, mrng, slices, biasFactor) {
	if (biasFactor === void 0 || slices.length === 0 || mrng.nextInt(1, biasFactor) !== 1) return new NoopSlicedGenerator(arb, mrng, biasFactor);
	return new SlicedBasedGenerator(arb, mrng, slices, biasFactor);
}
//#endregion
//#region src/arbitrary/_internals/ArrayArbitrary.ts
const safeMathFloor$4 = Math.floor;
const safeMathLog$1 = Math.log;
const safeArrayIsArray$2 = Array.isArray;
/** @internal */
function biasedMaxLength(minLength, maxLength) {
	if (minLength === maxLength) return minLength;
	return minLength + safeMathFloor$4(safeMathLog$1(maxLength - minLength) / safeMathLog$1(2));
}
/** @internal */
var ArrayArbitrary = class ArrayArbitrary extends Arbitrary {
	constructor(arb, minLength, maxGeneratedLength, maxLength, depthIdentifier, setBuilder, customSlices) {
		super();
		this.arb = arb;
		this.minLength = minLength;
		this.maxGeneratedLength = maxGeneratedLength;
		this.maxLength = maxLength;
		this.setBuilder = setBuilder;
		this.customSlices = customSlices;
		this.lengthArb = integer({
			min: minLength,
			max: maxGeneratedLength
		});
		this.depthContext = getDepthContextFor(depthIdentifier);
		this.cachedBiasedMaxLength = biasedMaxLength(minLength, maxGeneratedLength);
	}
	preFilter(tab) {
		if (this.setBuilder === void 0) return tab;
		const s = this.setBuilder();
		for (let index = 0; index !== tab.length; ++index) s.tryAdd(tab[index]);
		return s.getData();
	}
	static makeItCloneable(vs, shrinkables) {
		vs[cloneMethod] = () => {
			const cloned = [];
			for (let idx = 0; idx !== shrinkables.length; ++idx) safePush(cloned, shrinkables[idx].value);
			this.makeItCloneable(cloned, shrinkables);
			return cloned;
		};
		return vs;
	}
	generateNItemsNoDuplicates(setBuilder, N, mrng, biasFactorItems) {
		let numSkippedInRow = 0;
		const s = setBuilder();
		const slicedGenerator = buildSlicedGenerator(this.arb, mrng, this.customSlices, biasFactorItems);
		while (s.size() < N && numSkippedInRow < this.maxGeneratedLength) {
			const current = slicedGenerator.next();
			if (s.tryAdd(current)) numSkippedInRow = 0;
			else numSkippedInRow += 1;
		}
		return s.getData();
	}
	safeGenerateNItemsNoDuplicates(setBuilder, N, mrng, biasFactorItems) {
		const depthImpact = N - this.cachedBiasedMaxLength;
		if (depthImpact <= 0) return this.generateNItemsNoDuplicates(setBuilder, N, mrng, biasFactorItems);
		this.depthContext.depth += depthImpact;
		try {
			return this.generateNItemsNoDuplicates(setBuilder, N, mrng, biasFactorItems);
		} finally {
			this.depthContext.depth -= depthImpact;
		}
	}
	generateNItems(N, mrng, biasFactorItems) {
		const items = [];
		const slicedGenerator = buildSlicedGenerator(this.arb, mrng, this.customSlices, biasFactorItems);
		slicedGenerator.attemptExact(N);
		for (let index = 0; index !== N; ++index) safePush(items, slicedGenerator.next());
		return items;
	}
	safeGenerateNItems(N, mrng, biasFactorItems) {
		const depthImpact = N - this.cachedBiasedMaxLength;
		if (depthImpact <= 0) return this.generateNItems(N, mrng, biasFactorItems);
		this.depthContext.depth += depthImpact;
		try {
			return this.generateNItems(N, mrng, biasFactorItems);
		} finally {
			this.depthContext.depth -= depthImpact;
		}
	}
	wrapper(itemsRaw, shrunkOnce, itemsRawLengthContext, startIndex) {
		const items = shrunkOnce ? this.preFilter(itemsRaw) : itemsRaw;
		let cloneable = false;
		const vs = [];
		const itemsContexts = [];
		for (let idx = 0; idx !== items.length; ++idx) {
			const s = items[idx];
			cloneable = cloneable || s.hasToBeCloned;
			safePush(vs, s.value);
			safePush(itemsContexts, s.context);
		}
		if (cloneable) ArrayArbitrary.makeItCloneable(vs, items);
		return new Value(vs, {
			shrunkOnce,
			lengthContext: itemsRaw.length === items.length && itemsRawLengthContext !== void 0 ? itemsRawLengthContext : void 0,
			itemsContexts,
			startIndex
		});
	}
	generate(mrng, biasFactor) {
		let targetSize;
		let biasFactorItems;
		if (biasFactor === void 0) targetSize = this.lengthArb.generate(mrng, void 0).value;
		else if (this.minLength === this.maxGeneratedLength) {
			targetSize = this.lengthArb.generate(mrng, void 0).value;
			biasFactorItems = biasFactor;
		} else if (mrng.nextInt(1, biasFactor) !== 1) targetSize = this.lengthArb.generate(mrng, void 0).value;
		else if (mrng.nextInt(1, biasFactor) !== 1) {
			targetSize = this.lengthArb.generate(mrng, void 0).value;
			biasFactorItems = biasFactor;
		} else {
			const maxBiasedLength = this.cachedBiasedMaxLength;
			targetSize = integer({
				min: this.minLength,
				max: maxBiasedLength
			}).generate(mrng, void 0).value;
			biasFactorItems = biasFactor;
		}
		const items = this.setBuilder !== void 0 ? this.safeGenerateNItemsNoDuplicates(this.setBuilder, targetSize, mrng, biasFactorItems) : this.safeGenerateNItems(targetSize, mrng, biasFactorItems);
		return this.wrapper(items, false, void 0, 0);
	}
	canShrinkWithoutContext(value) {
		if (!safeArrayIsArray$2(value) || this.minLength > value.length || value.length > this.maxLength) return false;
		for (let index = 0; index !== value.length; ++index) {
			if (!(index in value)) return false;
			if (!this.arb.canShrinkWithoutContext(value[index])) return false;
		}
		return this.preFilter(safeMap(value, (item) => new Value(item, void 0))).length === value.length;
	}
	shrinkItemByItem(value, safeContext, endIndex) {
		const shrinks = [];
		for (let index = safeContext.startIndex; index < endIndex; ++index) safePush(shrinks, makeLazy(() => this.arb.shrink(value[index], safeContext.itemsContexts[index]).map((v) => {
			const beforeCurrent = safeMap(safeSlice(value, 0, index), (v, i) => new Value(cloneIfNeeded(v), safeContext.itemsContexts[i]));
			const afterCurrent = safeMap(safeSlice(value, index + 1), (v, i) => new Value(cloneIfNeeded(v), safeContext.itemsContexts[i + index + 1]));
			return [
				[
					...beforeCurrent,
					v,
					...afterCurrent
				],
				void 0,
				index
			];
		})));
		return Stream.nil().join(...shrinks);
	}
	shrinkImpl(value, context) {
		if (value.length === 0) return Stream.nil();
		const safeContext = context !== void 0 ? context : {
			shrunkOnce: false,
			lengthContext: void 0,
			itemsContexts: [],
			startIndex: 0
		};
		return this.lengthArb.shrink(value.length, safeContext.lengthContext).drop(safeContext.shrunkOnce && safeContext.lengthContext === void 0 && value.length > this.minLength + 1 ? 1 : 0).map((lengthValue) => {
			const sliceStart = value.length - lengthValue.value;
			return [
				safeMap(safeSlice(value, sliceStart), (v, index) => new Value(cloneIfNeeded(v), safeContext.itemsContexts[index + sliceStart])),
				lengthValue.context,
				0
			];
		}).join(makeLazy(() => value.length > this.minLength ? this.shrinkItemByItem(value, safeContext, 1) : this.shrinkItemByItem(value, safeContext, value.length))).join(value.length > this.minLength ? makeLazy(() => {
			const subContext = {
				shrunkOnce: false,
				lengthContext: void 0,
				itemsContexts: safeSlice(safeContext.itemsContexts, 1),
				startIndex: 0
			};
			return this.shrinkImpl(safeSlice(value, 1), subContext).filter((v) => this.minLength <= v[0].length + 1).map((v) => {
				return [
					[new Value(cloneIfNeeded(value[0]), safeContext.itemsContexts[0]), ...v[0]],
					void 0,
					0
				];
			});
		}) : Stream.nil());
	}
	shrink(value, context) {
		return this.shrinkImpl(value, context).map((contextualValue) => this.wrapper(contextualValue[0], true, contextualValue[1], contextualValue[2]));
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/MaxLengthFromMinLength.ts
const safeMathFloor$3 = Math.floor;
const safeMathMin$4 = Math.min;
/**
* Shared upper bound for max length of array-like entities handled within fast-check
*
* "Every Array object has a non-configurable "length" property whose value is always a nonnegative integer less than 2^32."
* See {@link https://262.ecma-international.org/11.0/#sec-array-exotic-objects | ECMAScript Specifications}
*
* "The String type is the set of all ordered sequences [...] up to a maximum length of 2^53 - 1 elements."
* See {@link https://262.ecma-international.org/11.0/#sec-ecmascript-language-types-string-type | ECMAScript Specifications}
*
* @internal
*/
const MaxLengthUpperBound = 2147483647;
/** @internal */
const orderedSize = [
	"xsmall",
	"small",
	"medium",
	"large",
	"xlarge"
];
/** @internal */
const orderedRelativeSize = [
	"-4",
	"-3",
	"-2",
	"-1",
	"=",
	"+1",
	"+2",
	"+3",
	"+4"
];
/**
* The default size used by fast-check
* @internal
*/
const DefaultSize = "small";
/**
* Compute `maxLength` based on `minLength` and `size`
* @internal
*/
function maxLengthFromMinLength(minLength, size) {
	switch (size) {
		case "xsmall": return safeMathFloor$3(1.1 * minLength) + 1;
		case "small": return 2 * minLength + 10;
		case "medium": return 11 * minLength + 100;
		case "large": return 101 * minLength + 1e3;
		case "xlarge": return 1001 * minLength + 1e4;
		default: throw new Error(`Unable to compute lengths based on received size: ${size}`);
	}
}
/**
* Transform a RelativeSize|Size into a Size
* @internal
*/
function relativeSizeToSize(size, defaultSize) {
	const sizeInRelative = safeIndexOf(orderedRelativeSize, size);
	if (sizeInRelative === -1) return size;
	const defaultSizeInSize = safeIndexOf(orderedSize, defaultSize);
	if (defaultSizeInSize === -1) throw new Error(`Unable to offset size based on the unknown defaulted one: ${defaultSize}`);
	const resultingSizeInSize = defaultSizeInSize + sizeInRelative - 4;
	return resultingSizeInSize < 0 ? orderedSize[0] : resultingSizeInSize >= orderedSize.length ? orderedSize[orderedSize.length - 1] : orderedSize[resultingSizeInSize];
}
/**
* Compute `maxGeneratedLength` based on `minLength`, `maxLength` and `size`
* @param size - Size defined by the caller on the arbitrary
* @param minLength - Considered minimal length
* @param maxLength - Considered maximal length
* @param specifiedMaxLength - Whether or not the caller specified the max (true) or if it has been defaulted (false)
* @internal
*/
function maxGeneratedLengthFromSizeForArbitrary(size, minLength, maxLength, specifiedMaxLength) {
	const { baseSize: defaultSize = DefaultSize, defaultSizeToMaxWhenMaxSpecified } = readConfigureGlobal() || {};
	const definedSize = size !== void 0 ? size : specifiedMaxLength && defaultSizeToMaxWhenMaxSpecified ? "max" : defaultSize;
	if (definedSize === "max") return maxLength;
	const finalSize = relativeSizeToSize(definedSize, defaultSize);
	return safeMathMin$4(maxLengthFromMinLength(minLength, finalSize), maxLength);
}
/**
* Compute `depthSize` based on `size`
* @param size - Size or depthSize defined by the caller on the arbitrary
* @param specifiedMaxDepth - Whether or not the caller specified a max depth
* @internal
*/
function depthBiasFromSizeForArbitrary(depthSizeOrSize, specifiedMaxDepth) {
	if (typeof depthSizeOrSize === "number") return 1 / depthSizeOrSize;
	const { baseSize: defaultSize = DefaultSize, defaultSizeToMaxWhenMaxSpecified } = readConfigureGlobal() || {};
	const definedSize = depthSizeOrSize !== void 0 ? depthSizeOrSize : specifiedMaxDepth && defaultSizeToMaxWhenMaxSpecified ? "max" : defaultSize;
	if (definedSize === "max") return 0;
	switch (relativeSizeToSize(definedSize, defaultSize)) {
		case "xsmall": return 1;
		case "small": return .5;
		case "medium": return .25;
		case "large": return .125;
		case "xlarge": return .0625;
	}
}
/**
* Resolve the size that should be used given the current context
* @param size - Size defined by the caller on the arbitrary
*/
function resolveSize(size) {
	const { baseSize: defaultSize = DefaultSize } = readConfigureGlobal() || {};
	if (size === void 0) return defaultSize;
	return relativeSizeToSize(size, defaultSize);
}
//#endregion
//#region src/arbitrary/array.ts
/**
* For arrays of values coming from `arb`
*
* @param arb - Arbitrary used to generate the values inside the array
* @param constraints - Constraints to apply when building instances (since 2.4.0)
*
* @remarks Since 0.0.1
* @public
*/
function array(arb, constraints = {}) {
	const size = constraints.size;
	const minLength = constraints.minLength || 0;
	const maxLengthOrUnset = constraints.maxLength;
	const depthIdentifier = constraints.depthIdentifier;
	const maxLength = maxLengthOrUnset !== void 0 ? maxLengthOrUnset : MaxLengthUpperBound;
	return new ArrayArbitrary(arb, minLength, maxGeneratedLengthFromSizeForArbitrary(size, minLength, maxLength, maxLengthOrUnset !== void 0), maxLength, depthIdentifier, void 0, constraints.experimentalCustomSlices || []);
}
//#endregion
//#region src/arbitrary/_internals/helpers/ShrinkBigInt.ts
/**
* Halve towards zero
* @internal
*/
function halveBigInt(n) {
	return n / SBigInt(2);
}
/**
* Compute shrunk values to move from current to target
* @internal
*/
function shrinkBigInt(current, target, tryTargetAsap) {
	const realGap = current - target;
	function* shrinkDecr() {
		let previous = tryTargetAsap ? void 0 : target;
		const gap = tryTargetAsap ? realGap : halveBigInt(realGap);
		for (let toremove = gap; toremove > 0; toremove = halveBigInt(toremove)) {
			const next = current - toremove;
			yield new Value(next, previous);
			previous = next;
		}
	}
	function* shrinkIncr() {
		let previous = tryTargetAsap ? void 0 : target;
		const gap = tryTargetAsap ? realGap : halveBigInt(realGap);
		for (let toremove = gap; toremove < 0; toremove = halveBigInt(toremove)) {
			const next = current - toremove;
			yield new Value(next, previous);
			previous = next;
		}
	}
	return realGap > 0 ? stream(shrinkDecr()) : stream(shrinkIncr());
}
//#endregion
//#region src/arbitrary/_internals/BigIntArbitrary.ts
/** @internal */
var BigIntArbitrary = class BigIntArbitrary extends Arbitrary {
	constructor(min, max) {
		super();
		this.min = min;
		this.max = max;
	}
	generate(mrng, biasFactor) {
		const range = this.computeGenerateRange(mrng, biasFactor);
		return new Value(mrng.nextBigInt(range.min, range.max), void 0);
	}
	computeGenerateRange(mrng, biasFactor) {
		if (biasFactor === void 0 || mrng.nextInt(1, biasFactor) !== 1) return {
			min: this.min,
			max: this.max
		};
		const ranges = biasNumericRange(this.min, this.max, bigIntLogLike);
		if (ranges.length === 1) return ranges[0];
		const id = mrng.nextInt(-2 * (ranges.length - 1), ranges.length - 2);
		return id < 0 ? ranges[0] : ranges[id + 1];
	}
	canShrinkWithoutContext(value) {
		return typeof value === "bigint" && this.min <= value && value <= this.max;
	}
	shrink(current, context) {
		if (!BigIntArbitrary.isValidContext(current, context)) return shrinkBigInt(current, this.defaultTarget(), true);
		if (this.isLastChanceTry(current, context)) return Stream.of(new Value(context, void 0));
		return shrinkBigInt(current, context, false);
	}
	defaultTarget() {
		if (this.min <= 0 && this.max >= 0) return SBigInt(0);
		return this.min < 0 ? this.max : this.min;
	}
	isLastChanceTry(current, context) {
		if (current > 0) return current === context + SBigInt(1) && current > this.min;
		if (current < 0) return current === context - SBigInt(1) && current < this.max;
		return false;
	}
	static isValidContext(current, context) {
		if (context === void 0) return false;
		if (typeof context !== "bigint") throw new Error(`Invalid context type passed to BigIntArbitrary (#1)`);
		const differentSigns = current > 0 && context < 0 || current < 0 && context > 0;
		if (context !== SBigInt(0) && differentSigns) throw new Error(`Invalid context value passed to BigIntArbitrary (#2)`);
		return true;
	}
};
//#endregion
//#region src/arbitrary/bigInt.ts
/**
* Build fully set BigIntConstraints from a partial data
* @internal
*/
function buildCompleteBigIntConstraints(constraints) {
	const DefaultMin = SBigInt(-1) << SBigInt(255);
	const DefaultMax = (SBigInt(1) << SBigInt(255)) - SBigInt(1);
	const min = constraints.min;
	const max = constraints.max;
	return {
		min: min !== void 0 ? min : DefaultMin - (max !== void 0 && max < SBigInt(0) ? max * max : SBigInt(0)),
		max: max !== void 0 ? max : DefaultMax + (min !== void 0 && min > SBigInt(0) ? min * min : SBigInt(0))
	};
}
/**
* Extract constraints from args received by bigint
* @internal
*/
function extractBigIntConstraints(args) {
	if (args[0] === void 0) return {};
	if (args[1] === void 0) return args[0];
	return {
		min: args[0],
		max: args[1]
	};
}
function bigInt(...args) {
	const constraints = buildCompleteBigIntConstraints(extractBigIntConstraints(args));
	if (constraints.min > constraints.max) throw new Error("fc.bigInt expects max to be greater than or equal to min");
	return new BigIntArbitrary(constraints.min, constraints.max);
}
//#endregion
//#region src/arbitrary/noBias.ts
const stableObjectGetPrototypeOf$1 = Object.getPrototypeOf;
/** @internal */
var NoBiasArbitrary = class extends Arbitrary {
	constructor(arb) {
		super();
		this.arb = arb;
	}
	generate(mrng, _biasFactor) {
		return this.arb.generate(mrng, void 0);
	}
	canShrinkWithoutContext(value) {
		return this.arb.canShrinkWithoutContext(value);
	}
	shrink(value, context) {
		return this.arb.shrink(value, context);
	}
};
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
function noBias(arb) {
	if (stableObjectGetPrototypeOf$1(arb) === NoBiasArbitrary.prototype && arb.generate === NoBiasArbitrary.prototype.generate && arb.canShrinkWithoutContext === NoBiasArbitrary.prototype.canShrinkWithoutContext && arb.shrink === NoBiasArbitrary.prototype.shrink) return arb;
	return new NoBiasArbitrary(arb);
}
//#endregion
//#region src/arbitrary/boolean.ts
/** @internal */
function booleanMapper(v) {
	return v === 1;
}
/** @internal */
function booleanUnmapper(v) {
	if (typeof v !== "boolean") throw new Error("Unsupported input type");
	return v === true ? 1 : 0;
}
/**
* For boolean values - `true` or `false`
* @remarks Since 0.0.6
* @public
*/
function boolean() {
	return noBias(integer({
		min: 0,
		max: 1
	}).map(booleanMapper, booleanUnmapper));
}
//#endregion
//#region src/arbitrary/_internals/ConstantArbitrary.ts
const safeObjectIs$5 = Object.is;
/** @internal */
var FastConstantValuesLookup = class {
	constructor(values) {
		this.values = values;
		this.fastValues = new SSet(this.values);
		let hasMinusZero = false;
		let hasPlusZero = false;
		if (safeHas(this.fastValues, 0)) for (let idx = 0; idx !== this.values.length; ++idx) {
			const value = this.values[idx];
			hasMinusZero = hasMinusZero || safeObjectIs$5(value, -0);
			hasPlusZero = hasPlusZero || safeObjectIs$5(value, 0);
		}
		this.hasMinusZero = hasMinusZero;
		this.hasPlusZero = hasPlusZero;
	}
	has(value) {
		if (value === 0) {
			if (safeObjectIs$5(value, 0)) return this.hasPlusZero;
			return this.hasMinusZero;
		}
		return safeHas(this.fastValues, value);
	}
};
/** @internal */
var ConstantArbitrary = class extends Arbitrary {
	constructor(values) {
		super();
		this.values = values;
	}
	generate(mrng, _biasFactor) {
		const idx = this.values.length === 1 ? 0 : mrng.nextInt(0, this.values.length - 1);
		const value = this.values[idx];
		if (!hasCloneMethod(value)) return new Value(value, idx);
		return new Value(value, idx, () => value[cloneMethod]());
	}
	canShrinkWithoutContext(value) {
		if (this.values.length === 1) return safeObjectIs$5(this.values[0], value);
		if (this.fastValues === void 0) this.fastValues = new FastConstantValuesLookup(this.values);
		return this.fastValues.has(value);
	}
	shrink(value, context) {
		if (context === 0 || safeObjectIs$5(value, this.values[0])) return Stream.nil();
		return Stream.of(new Value(this.values[0], 0));
	}
};
//#endregion
//#region src/arbitrary/constantFrom.ts
function constantFrom(...values) {
	if (values.length === 0) throw new Error("fc.constantFrom expects at least one parameter");
	return new ConstantArbitrary(values);
}
//#endregion
//#region src/arbitrary/falsy.ts
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
function falsy(constraints) {
	if (!constraints || !constraints.withBigInt) return constantFrom(false, null, void 0, 0, "", NaN);
	return constantFrom(false, null, void 0, 0, "", NaN, SBigInt(0));
}
//#endregion
//#region src/arbitrary/constant.ts
/**
* For `value`
* @param value - The value to produce
* @remarks Since 0.0.1
* @public
*/
function constant(value) {
	return new ConstantArbitrary([value]);
}
//#endregion
//#region src/arbitrary/context.ts
/** @internal */
var ContextImplem = class ContextImplem {
	constructor() {
		this.receivedLogs = [];
	}
	log(data) {
		this.receivedLogs.push(data);
	}
	size() {
		return this.receivedLogs.length;
	}
	toString() {
		return JSON.stringify({ logs: this.receivedLogs });
	}
	[cloneMethod]() {
		return new ContextImplem();
	}
};
/**
* Produce a {@link ContextValue} instance
* @remarks Since 1.8.0
* @public
*/
function context() {
	return constant(new ContextImplem());
}
//#endregion
//#region src/arbitrary/_internals/mappers/TimeToDate.ts
const safeNaN$2 = NaN;
const safeNumberIsNaN$4 = Number.isNaN;
/** @internal */
function timeToDateMapper(time) {
	return new SDate(time);
}
/** @internal */
function timeToDateUnmapper(value) {
	if (!(value instanceof SDate) || value.constructor !== SDate) throw new SError("Not a valid value for date unmapper");
	return safeGetTime(value);
}
/** @internal */
function timeToDateMapperWithNaN(valueForNaN) {
	return (time) => {
		return time === valueForNaN ? new SDate(safeNaN$2) : timeToDateMapper(time);
	};
}
/** @internal */
function timeToDateUnmapperWithNaN(valueForNaN) {
	return (value) => {
		const time = timeToDateUnmapper(value);
		return safeNumberIsNaN$4(time) ? valueForNaN : time;
	};
}
//#endregion
//#region src/arbitrary/date.ts
const safeNumberIsNaN$3 = Number.isNaN;
/**
* For date between constraints.min or new Date(-8640000000000000) (included) and constraints.max or new Date(8640000000000000) (included)
*
* @param constraints - Constraints to apply when building instances
*
* @remarks Since 1.17.0
* @public
*/
function date(constraints = {}) {
	const intMin = constraints.min !== void 0 ? safeGetTime(constraints.min) : -864e13;
	const intMax = constraints.max !== void 0 ? safeGetTime(constraints.max) : 864e13;
	const noInvalidDate = constraints.noInvalidDate;
	if (safeNumberIsNaN$3(intMin)) throw new Error("fc.date min must be valid instance of Date");
	if (safeNumberIsNaN$3(intMax)) throw new Error("fc.date max must be valid instance of Date");
	if (intMin > intMax) throw new Error("fc.date max must be greater or equal to min");
	if (noInvalidDate) return integer({
		min: intMin,
		max: intMax
	}).map(timeToDateMapper, timeToDateUnmapper);
	const valueForNaN = intMax + 1;
	return integer({
		min: intMin,
		max: intMax + 1
	}).map(timeToDateMapperWithNaN(valueForNaN), timeToDateUnmapperWithNaN(valueForNaN));
}
//#endregion
//#region src/arbitrary/chainUntil.ts
/** @internal */
var ChainUntilArbitrary = class extends Arbitrary {
	constructor(startArb, chainer) {
		super();
		this.startArb = startArb;
		this.chainer = chainer;
	}
	generate(mrng, biasFactor) {
		const entries = [];
		const clonedMrng = mrng.clone();
		let current = this.startArb.generate(mrng, biasFactor);
		entries.push({
			arbitrary: this.startArb,
			value: current.value_,
			context: current.context,
			clonedMrng
		});
		while (true) {
			const nextArb = this.chainer(current.value_);
			if (nextArb === void 0) break;
			const nextClonedMrng = mrng.clone();
			current = nextArb.generate(mrng, biasFactor);
			entries.push({
				arbitrary: nextArb,
				value: current.value_,
				context: current.context,
				clonedMrng: nextClonedMrng
			});
		}
		const ctx = {
			biasFactor,
			entries,
			currentShrinkLevel: 0
		};
		return new Value(current.value_, ctx);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	shrink(value, context) {
		if (!this.isSafeContext(context)) return Stream.nil();
		return new Stream(this.shrinkIterator(context));
	}
	*shrinkIterator(context) {
		const { entries, currentShrinkLevel, biasFactor } = context;
		for (let level = currentShrinkLevel; level < entries.length; ++level) {
			const entry = entries[level];
			const shrinks = entry.arbitrary.shrink(entry.value, entry.context);
			for (const shrunkValue of shrinks) {
				const newEntries = entries.slice(0, level);
				newEntries.push({
					arbitrary: entry.arbitrary,
					value: shrunkValue.value_,
					context: shrunkValue.context,
					clonedMrng: entry.clonedMrng
				});
				let current = shrunkValue;
				const mrng = entry.clonedMrng.clone();
				while (true) {
					const nextArb = this.chainer(current.value_);
					if (nextArb === void 0) break;
					const nextClonedMrng = mrng.clone();
					const next = nextArb.generate(mrng, biasFactor);
					newEntries.push({
						arbitrary: nextArb,
						value: next.value_,
						context: next.context,
						clonedMrng: nextClonedMrng
					});
					current = next;
				}
				const lastEntry = newEntries[newEntries.length - 1];
				const newContext = {
					biasFactor,
					entries: newEntries,
					currentShrinkLevel: level
				};
				yield new Value(lastEntry.value, newContext);
			}
		}
	}
	isSafeContext(context) {
		return context !== null && context !== void 0 && typeof context === "object" && "biasFactor" in context && "entries" in context && "currentShrinkLevel" in context;
	}
};
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
function chainUntil(startArb, chainer) {
	return new ChainUntilArbitrary(startArb, chainer);
}
//#endregion
//#region src/arbitrary/_internals/CloneArbitrary.ts
const safeSymbolIterator = Symbol.iterator;
const safeIsArray = Array.isArray;
const safeObjectIs$4 = Object.is;
/** @internal */
var CloneArbitrary = class CloneArbitrary extends Arbitrary {
	constructor(arb, numValues) {
		super();
		this.arb = arb;
		this.numValues = numValues;
	}
	generate(mrng, biasFactor) {
		const items = [];
		if (this.numValues <= 0) return this.wrapper(items);
		for (let idx = 0; idx !== this.numValues - 1; ++idx) safePush(items, this.arb.generate(mrng.clone(), biasFactor));
		safePush(items, this.arb.generate(mrng, biasFactor));
		return this.wrapper(items);
	}
	canShrinkWithoutContext(value) {
		if (!safeIsArray(value) || value.length !== this.numValues) return false;
		if (value.length === 0) return true;
		for (let index = 1; index < value.length; ++index) if (!safeObjectIs$4(value[0], value[index])) return false;
		return this.arb.canShrinkWithoutContext(value[0]);
	}
	shrink(value, context) {
		if (value.length === 0) return Stream.nil();
		return new Stream(this.shrinkImpl(value, context !== void 0 ? context : [])).map((v) => this.wrapper(v));
	}
	*shrinkImpl(value, contexts) {
		const its = safeMap(value, (v, idx) => this.arb.shrink(v, contexts[idx])[safeSymbolIterator]());
		let cur = safeMap(its, (it) => it.next());
		while (!cur[0].done) {
			yield safeMap(cur, (c) => c.value);
			cur = safeMap(its, (it) => it.next());
		}
	}
	static makeItCloneable(vs, shrinkables) {
		vs[cloneMethod] = () => {
			const cloned = [];
			for (let idx = 0; idx !== shrinkables.length; ++idx) safePush(cloned, shrinkables[idx].value);
			this.makeItCloneable(cloned, shrinkables);
			return cloned;
		};
		return vs;
	}
	wrapper(items) {
		let cloneable = false;
		const vs = [];
		const contexts = [];
		for (let idx = 0; idx !== items.length; ++idx) {
			const s = items[idx];
			cloneable = cloneable || s.hasToBeCloned;
			safePush(vs, s.value);
			safePush(contexts, s.context);
		}
		if (cloneable) CloneArbitrary.makeItCloneable(vs, items);
		return new Value(vs, contexts);
	}
};
//#endregion
//#region src/arbitrary/clone.ts
function clone(arb, numValues) {
	return new CloneArbitrary(arb, numValues);
}
//#endregion
//#region src/arbitrary/_internals/helpers/CustomEqualSet.ts
/**
* CustomSet based on a fully custom equality function
*
* @internal
*/
var CustomEqualSet = class {
	constructor(isEqual) {
		this.isEqual = isEqual;
		this.data = [];
	}
	tryAdd(value) {
		for (let idx = 0; idx !== this.data.length; ++idx) if (this.isEqual(this.data[idx], value)) return false;
		safePush(this.data, value);
		return true;
	}
	size() {
		return this.data.length;
	}
	getData() {
		return this.data;
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/StrictlyEqualSet.ts
const safeNumberIsNaN$2 = Number.isNaN;
/**
* CustomSet based on "strict equality" as defined by:
* https://tc39.es/ecma262/multipage/abstract-operations.html#sec-isstrictlyequal
*
* And coming with the ability to select a sub-value from the received one.
* @internal
*/
var StrictlyEqualSet = class {
	constructor(selector) {
		this.selector = selector;
		this.selectedItemsExceptNaN = new SSet();
		this.data = [];
	}
	tryAdd(value) {
		const selected = this.selector(value);
		if (safeNumberIsNaN$2(selected)) {
			safePush(this.data, value);
			return true;
		}
		const sizeBefore = this.selectedItemsExceptNaN.size;
		safeAdd(this.selectedItemsExceptNaN, selected);
		if (sizeBefore !== this.selectedItemsExceptNaN.size) {
			safePush(this.data, value);
			return true;
		}
		return false;
	}
	size() {
		return this.data.length;
	}
	getData() {
		return this.data;
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/SameValueSet.ts
const safeObjectIs$3 = Object.is;
/**
* CustomSet based on "SameValue" as defined by:
* https://tc39.es/ecma262/multipage/abstract-operations.html#sec-samevalue
*
* And coming with the ability to select a sub-value from the received one.
* @internal
*/
var SameValueSet = class {
	constructor(selector) {
		this.selector = selector;
		this.selectedItemsExceptMinusZero = new SSet();
		this.data = [];
		this.hasMinusZero = false;
	}
	tryAdd(value) {
		const selected = this.selector(value);
		if (safeObjectIs$3(selected, -0)) {
			if (this.hasMinusZero) return false;
			safePush(this.data, value);
			this.hasMinusZero = true;
			return true;
		}
		const sizeBefore = this.selectedItemsExceptMinusZero.size;
		safeAdd(this.selectedItemsExceptMinusZero, selected);
		if (sizeBefore !== this.selectedItemsExceptMinusZero.size) {
			safePush(this.data, value);
			return true;
		}
		return false;
	}
	size() {
		return this.data.length;
	}
	getData() {
		return this.data;
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/SameValueZeroSet.ts
/**
* CustomSet based on "SameValueZero" as defined by:
* https://tc39.es/ecma262/multipage/abstract-operations.html#sec-samevaluezero
*
* And coming with the ability to select a sub-value from the received one.
* @internal
*/
var SameValueZeroSet = class {
	constructor(selector) {
		this.selector = selector;
		this.selectedItems = new SSet();
		this.data = [];
	}
	tryAdd(value) {
		const selected = this.selector(value);
		const sizeBefore = this.selectedItems.size;
		safeAdd(this.selectedItems, selected);
		if (sizeBefore !== this.selectedItems.size) {
			safePush(this.data, value);
			return true;
		}
		return false;
	}
	size() {
		return this.data.length;
	}
	getData() {
		return this.data;
	}
};
//#endregion
//#region src/arbitrary/uniqueArray.ts
/** @internal */
function buildUniqueArraySetBuilder(constraints) {
	if (typeof constraints.comparator === "function") {
		if (constraints.selector === void 0) {
			const comparator = constraints.comparator;
			const isEqualForBuilder = (nextA, nextB) => comparator(nextA.value_, nextB.value_);
			return () => new CustomEqualSet(isEqualForBuilder);
		}
		const comparator = constraints.comparator;
		const selector = constraints.selector;
		const refinedSelector = (next) => selector(next.value_);
		const isEqualForBuilder = (nextA, nextB) => comparator(refinedSelector(nextA), refinedSelector(nextB));
		return () => new CustomEqualSet(isEqualForBuilder);
	}
	const selector = constraints.selector || ((v) => v);
	const refinedSelector = (next) => selector(next.value_);
	switch (constraints.comparator) {
		case "IsStrictlyEqual": return () => new StrictlyEqualSet(refinedSelector);
		case "SameValueZero": return () => new SameValueZeroSet(refinedSelector);
		case "SameValue":
		case void 0: return () => new SameValueSet(refinedSelector);
	}
}
function uniqueArray(arb, constraints = {}) {
	const minLength = constraints.minLength !== void 0 ? constraints.minLength : 0;
	const maxLength = constraints.maxLength !== void 0 ? constraints.maxLength : MaxLengthUpperBound;
	const maxGeneratedLength = maxGeneratedLengthFromSizeForArbitrary(constraints.size, minLength, maxLength, constraints.maxLength !== void 0);
	const depthIdentifier = constraints.depthIdentifier;
	const arrayArb = new ArrayArbitrary(arb, minLength, maxGeneratedLength, maxLength, depthIdentifier, buildUniqueArraySetBuilder(constraints), []);
	if (minLength === 0) return arrayArb;
	return arrayArb.filter((tab) => tab.length >= minLength);
}
//#endregion
//#region src/arbitrary/_internals/mappers/KeyValuePairsToObject.ts
const safeObjectCreate$5 = Object.create;
const safeObjectDefineProperty$2 = Object.defineProperty;
const safeObjectGetOwnPropertyDescriptor$2 = Object.getOwnPropertyDescriptor;
const safeObjectGetPrototypeOf$1 = Object.getPrototypeOf;
const safeObjectPrototype$1 = Object.prototype;
const safeReflectOwnKeys = Reflect.ownKeys;
/** @internal */
function keyValuePairsToObjectMapper(definition) {
	const obj = definition[1] ? safeObjectCreate$5(null) : {};
	const keyValues = definition[0];
	for (let idx = 0; idx !== keyValues.length; ++idx) {
		const key = keyValues[idx][0];
		if (key === "__proto__") safeObjectDefineProperty$2(obj, key, {
			enumerable: true,
			configurable: true,
			writable: true,
			value: keyValues[idx][1]
		});
		else obj[key] = keyValues[idx][1];
	}
	return obj;
}
/** @internal */
function isValidPropertyNameFilter(descriptor) {
	return descriptor !== void 0 && !!descriptor.configurable && !!descriptor.enumerable && !!descriptor.writable && descriptor.get === void 0 && descriptor.set === void 0;
}
/** @internal */
function keyValuePairsToObjectUnmapper(value) {
	if (typeof value !== "object" || value === null) throw new SError("Incompatible instance received: should be a non-null object");
	const hasNullPrototype = safeObjectGetPrototypeOf$1(value) === null;
	const hasObjectPrototype = safeObjectGetPrototypeOf$1(value) === safeObjectPrototype$1;
	if (!hasNullPrototype && !hasObjectPrototype) throw new SError("Incompatible instance received: should be of exact type Object");
	const propertyDescriptors = safeMap(safeReflectOwnKeys(value), (key) => [key, safeObjectGetOwnPropertyDescriptor$2(value, key)]);
	if (!safeEvery(propertyDescriptors, ([, descriptor]) => isValidPropertyNameFilter(descriptor))) throw new SError("Incompatible instance received: should contain only c/e/w properties without get/set");
	return [safeMap(propertyDescriptors, ([key, descriptor]) => [key, descriptor.value]), hasNullPrototype];
}
//#endregion
//#region src/arbitrary/dictionary.ts
/** @internal */
function dictionaryKeyExtractor(entry) {
	return entry[0];
}
function dictionary(keyArb, valueArb, constraints = {}) {
	const noNullPrototype = !!constraints.noNullPrototype;
	return tuple(uniqueArray(tuple(keyArb, valueArb), {
		minLength: constraints.minKeys,
		maxLength: constraints.maxKeys,
		size: constraints.size,
		selector: dictionaryKeyExtractor,
		depthIdentifier: constraints.depthIdentifier
	}), noNullPrototype ? constant(false) : boolean()).map(keyValuePairsToObjectMapper, keyValuePairsToObjectUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/FrequencyArbitrary.ts
const safePositiveInfinity$7 = Number.POSITIVE_INFINITY;
const safeMaxSafeInteger$2 = Number.MAX_SAFE_INTEGER;
const safeNumberIsInteger$4 = Number.isInteger;
const safeMathFloor$2 = Math.floor;
const safeMathPow = Math.pow;
const safeMathMin$3 = Math.min;
/** @internal */
var FrequencyArbitrary = class FrequencyArbitrary extends Arbitrary {
	static from(warbs, constraints, label) {
		if (warbs.length === 0) throw new Error(`${label} expects at least one weighted arbitrary`);
		let totalWeight = 0;
		for (let idx = 0; idx !== warbs.length; ++idx) {
			if (warbs[idx].arbitrary === void 0) throw new Error(`${label} expects arbitraries to be specified`);
			const currentWeight = warbs[idx].weight;
			totalWeight += currentWeight;
			if (!safeNumberIsInteger$4(currentWeight)) throw new Error(`${label} expects weights to be integer values`);
			if (currentWeight < 0) throw new Error(`${label} expects weights to be superior or equal to 0`);
		}
		if (totalWeight <= 0) throw new Error(`${label} expects the sum of weights to be strictly superior to 0`);
		const sanitizedConstraints = {
			depthBias: depthBiasFromSizeForArbitrary(constraints.depthSize, constraints.maxDepth !== void 0),
			maxDepth: constraints.maxDepth !== void 0 ? constraints.maxDepth : safePositiveInfinity$7,
			withCrossShrink: !!constraints.withCrossShrink
		};
		return new FrequencyArbitrary(warbs, sanitizedConstraints, getDepthContextFor(constraints.depthIdentifier));
	}
	constructor(warbs, constraints, context) {
		super();
		this.warbs = warbs;
		this.constraints = constraints;
		this.context = context;
		let currentWeight = 0;
		this.cumulatedWeights = [];
		for (let idx = 0; idx !== warbs.length; ++idx) {
			currentWeight += warbs[idx].weight;
			safePush(this.cumulatedWeights, currentWeight);
		}
		this.totalWeight = currentWeight;
	}
	generate(mrng, biasFactor) {
		if (this.mustGenerateFirst()) return this.safeGenerateForIndex(mrng, 0, biasFactor);
		const selected = mrng.nextInt(this.computeNegDepthBenefit(), this.totalWeight - 1);
		for (let idx = 0; idx !== this.cumulatedWeights.length; ++idx) if (selected < this.cumulatedWeights[idx]) return this.safeGenerateForIndex(mrng, idx, biasFactor);
		throw new Error(`Unable to generate from fc.frequency`);
	}
	canShrinkWithoutContext(value) {
		return this.canShrinkWithoutContextIndex(value) !== -1;
	}
	shrink(value, context) {
		if (context !== void 0) {
			const safeContext = context;
			const selectedIndex = safeContext.selectedIndex;
			const originalBias = safeContext.originalBias;
			const originalShrinks = this.warbs[selectedIndex].arbitrary.shrink(value, safeContext.originalContext).map((v) => this.mapIntoValue(selectedIndex, v, null, originalBias));
			if (safeContext.clonedMrngForFallbackFirst !== null) {
				if (safeContext.cachedGeneratedForFirst === void 0) safeContext.cachedGeneratedForFirst = this.safeGenerateForIndex(safeContext.clonedMrngForFallbackFirst, 0, originalBias);
				const valueFromFirst = safeContext.cachedGeneratedForFirst;
				return Stream.of(valueFromFirst).join(originalShrinks);
			}
			return originalShrinks;
		}
		const potentialSelectedIndex = this.canShrinkWithoutContextIndex(value);
		if (potentialSelectedIndex === -1) return Stream.nil();
		return this.defaultShrinkForFirst(potentialSelectedIndex).join(this.warbs[potentialSelectedIndex].arbitrary.shrink(value, void 0).map((v) => this.mapIntoValue(potentialSelectedIndex, v, null, void 0)));
	}
	/** Generate shrink values for first arbitrary when no context and no value was provided */
	defaultShrinkForFirst(selectedIndex) {
		++this.context.depth;
		try {
			if (!this.mustFallbackToFirstInShrink(selectedIndex) || this.warbs[0].fallbackValue === void 0) return Stream.nil();
		} finally {
			--this.context.depth;
		}
		const rawShrinkValue = new Value(this.warbs[0].fallbackValue.default, void 0);
		return Stream.of(this.mapIntoValue(0, rawShrinkValue, null, void 0));
	}
	/** Extract the index of the generator that would have been able to gennrate the value */
	canShrinkWithoutContextIndex(value) {
		if (this.mustGenerateFirst()) return this.warbs[0].arbitrary.canShrinkWithoutContext(value) ? 0 : -1;
		try {
			++this.context.depth;
			for (let idx = 0; idx !== this.warbs.length; ++idx) {
				const warb = this.warbs[idx];
				if (warb.weight !== 0 && warb.arbitrary.canShrinkWithoutContext(value)) return idx;
			}
			return -1;
		} finally {
			--this.context.depth;
		}
	}
	/** Map the output of one of the children with the context of frequency */
	mapIntoValue(idx, value, clonedMrngForFallbackFirst, biasFactor) {
		const context = {
			selectedIndex: idx,
			originalBias: biasFactor,
			originalContext: value.context,
			clonedMrngForFallbackFirst
		};
		return new Value(value.value, context);
	}
	/** Generate using Arbitrary at index idx and safely handle depth context */
	safeGenerateForIndex(mrng, idx, biasFactor) {
		++this.context.depth;
		try {
			const value = this.warbs[idx].arbitrary.generate(mrng, biasFactor);
			const clonedMrngForFallbackFirst = this.mustFallbackToFirstInShrink(idx) ? mrng.clone() : null;
			return this.mapIntoValue(idx, value, clonedMrngForFallbackFirst, biasFactor);
		} finally {
			--this.context.depth;
		}
	}
	/** Check if generating a value based on the first arbitrary is compulsory */
	mustGenerateFirst() {
		return this.constraints.maxDepth <= this.context.depth;
	}
	/** Check if fallback on first arbitrary during shrinking is required */
	mustFallbackToFirstInShrink(idx) {
		return idx !== 0 && this.constraints.withCrossShrink && this.warbs[0].weight !== 0;
	}
	/** Compute the benefit for the current depth */
	computeNegDepthBenefit() {
		const depthBias = this.constraints.depthBias;
		if (depthBias <= 0 || this.warbs[0].weight === 0) return 0;
		const depthBenefit = safeMathFloor$2(safeMathPow(1 + depthBias, this.context.depth)) - 1;
		return -safeMathMin$3(this.totalWeight * depthBenefit, safeMaxSafeInteger$2) || 0;
	}
};
//#endregion
//#region src/arbitrary/oneof.ts
/**
* @internal
*/
function isOneOfContraints(param) {
	return param !== null && param !== void 0 && typeof param === "object" && !("generate" in param) && !("arbitrary" in param) && !("weight" in param);
}
/**
* @internal
*/
function toWeightedArbitrary(maybeWeightedArbitrary) {
	if (isArbitrary(maybeWeightedArbitrary)) return {
		arbitrary: maybeWeightedArbitrary,
		weight: 1
	};
	return maybeWeightedArbitrary;
}
function oneof(...args) {
	const constraints = args[0];
	if (isOneOfContraints(constraints)) {
		const weightedArbs = safeMap(safeSlice(args, 1), toWeightedArbitrary);
		return FrequencyArbitrary.from(weightedArbs, constraints, "fc.oneof");
	}
	const weightedArbs = safeMap(args, toWeightedArbitrary);
	return FrequencyArbitrary.from(weightedArbs, {}, "fc.oneof");
}
//#endregion
//#region src/arbitrary/nat.ts
const safeNumberIsInteger$3 = Number.isInteger;
function nat(arg) {
	const max = typeof arg === "number" ? arg : arg && arg.max !== void 0 ? arg.max : 2147483647;
	if (max < 0) throw new Error("fc.nat value should be greater than or equal to 0");
	if (!safeNumberIsInteger$3(max)) throw new Error("fc.nat maximum value should be an integer");
	return new IntegerArbitrary(0, max);
}
//#endregion
//#region src/arbitrary/_internals/mappers/IndexToMappedConstant.ts
/** @internal */
const safeObjectIs$2 = Object.is;
/** @internal */
function buildDichotomyEntries(entries) {
	let currentFrom = 0;
	const dichotomyEntries = [];
	for (const entry of entries) {
		const from = currentFrom;
		currentFrom = from + entry.num;
		const to = currentFrom - 1;
		dichotomyEntries.push({
			from,
			to,
			entry
		});
	}
	return dichotomyEntries;
}
/** @internal */
function findDichotomyEntry(dichotomyEntries, choiceIndex) {
	let min = 0;
	let max = dichotomyEntries.length;
	while (max - min > 1) {
		const mid = ~~((min + max) / 2);
		if (choiceIndex < dichotomyEntries[mid].from) max = mid;
		else min = mid;
	}
	return dichotomyEntries[min];
}
/** @internal */
function indexToMappedConstantMapperFor(entries) {
	const dichotomyEntries = buildDichotomyEntries(entries);
	return function indexToMappedConstantMapper(choiceIndex) {
		const dichotomyEntry = findDichotomyEntry(dichotomyEntries, choiceIndex);
		return dichotomyEntry.entry.build(choiceIndex - dichotomyEntry.from);
	};
}
/** @internal */
function buildReverseMapping(entries) {
	const reverseMapping = {
		mapping: new SMap$2(),
		negativeZeroIndex: void 0
	};
	let choiceIndex = 0;
	for (let entryIdx = 0; entryIdx !== entries.length; ++entryIdx) {
		const entry = entries[entryIdx];
		for (let idxInEntry = 0; idxInEntry !== entry.num; ++idxInEntry) {
			const value = entry.build(idxInEntry);
			if (value === 0 && 1 / value === SNumber.NEGATIVE_INFINITY) reverseMapping.negativeZeroIndex = choiceIndex;
			else safeMapSet(reverseMapping.mapping, value, choiceIndex);
			++choiceIndex;
		}
	}
	return reverseMapping;
}
/** @internal */
function indexToMappedConstantUnmapperFor(entries) {
	let reverseMapping = null;
	return function indexToMappedConstantUnmapper(value) {
		if (reverseMapping === null) reverseMapping = buildReverseMapping(entries);
		const choiceIndex = safeObjectIs$2(value, -0) ? reverseMapping.negativeZeroIndex : safeMapGet(reverseMapping.mapping, value);
		if (choiceIndex === void 0) throw new SError("Unknown value encountered cannot be built using this mapToConstant");
		return choiceIndex;
	};
}
//#endregion
//#region src/arbitrary/mapToConstant.ts
/** @internal */
function computeNumChoices(options) {
	if (options.length === 0) throw new SError(`fc.mapToConstant expects at least one option`);
	let numChoices = 0;
	for (let idx = 0; idx !== options.length; ++idx) {
		if (options[idx].num < 0) throw new SError(`fc.mapToConstant expects all options to have a number of entries greater or equal to zero`);
		numChoices += options[idx].num;
	}
	if (numChoices === 0) throw new SError(`fc.mapToConstant expects at least one choice among options`);
	return numChoices;
}
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
function mapToConstant(...entries) {
	return nat({ max: computeNumChoices(entries) - 1 }).map(indexToMappedConstantMapperFor(entries), indexToMappedConstantUnmapperFor(entries));
}
//#endregion
//#region src/arbitrary/_internals/helpers/TokenizeString.ts
/**
* Split a string into valid tokens of patternsArb
* @internal
*/
function tokenizeString(patternsArb, value, minLength, maxLength) {
	if (value.length === 0) {
		if (minLength > 0) return;
		return [];
	}
	if (maxLength <= 0) return;
	const stack = [{
		endIndexChunks: 0,
		nextStartIndex: 1,
		chunks: []
	}];
	while (stack.length > 0) {
		const last = safePop$1(stack);
		for (let index = last.nextStartIndex; index <= value.length; ++index) {
			const chunk = safeSubstring(value, last.endIndexChunks, index);
			if (patternsArb.canShrinkWithoutContext(chunk)) {
				const newChunks = [...last.chunks, chunk];
				if (index === value.length) {
					if (newChunks.length < minLength) break;
					return newChunks;
				}
				safePush(stack, {
					endIndexChunks: last.endIndexChunks,
					nextStartIndex: index + 1,
					chunks: last.chunks
				});
				if (newChunks.length < maxLength) safePush(stack, {
					endIndexChunks: index,
					nextStartIndex: index + 1,
					chunks: newChunks
				});
				break;
			}
		}
	}
}
//#endregion
//#region src/arbitrary/_internals/mappers/PatternsToString.ts
/** @internal - tab is supposed to be composed of valid entries extracted from the source arbitrary */
function patternsToStringMapper(tab) {
	return safeJoin(tab, "");
}
/** @internal */
function minLengthFrom(constraints) {
	return constraints.minLength !== void 0 ? constraints.minLength : 0;
}
/** @internal */
function maxLengthFrom(constraints) {
	return constraints.maxLength !== void 0 ? constraints.maxLength : MaxLengthUpperBound;
}
/** @internal */
function patternsToStringUnmapperIsValidLength(tokens, constraints) {
	return minLengthFrom(constraints) <= tokens.length && tokens.length <= maxLengthFrom(constraints);
}
/** @internal */
function patternsToStringUnmapperFor(patternsArb, constraints) {
	return function patternsToStringUnmapper(value) {
		if (typeof value !== "string") throw new SError("Unsupported value");
		const tokens = tokenizeString(patternsArb, value, minLengthFrom(constraints), maxLengthFrom(constraints));
		if (tokens === void 0) throw new SError("Unable to unmap received string");
		return tokens;
	};
}
//#endregion
//#region src/arbitrary/_internals/helpers/SlicesForStringBuilder.ts
const dangerousStrings = [
	"__defineGetter__",
	"__defineSetter__",
	"__lookupGetter__",
	"__lookupSetter__",
	"__proto__",
	"constructor",
	"hasOwnProperty",
	"isPrototypeOf",
	"propertyIsEnumerable",
	"toLocaleString",
	"toString",
	"valueOf",
	"apply",
	"arguments",
	"bind",
	"call",
	"caller",
	"length",
	"name",
	"prototype",
	"key",
	"ref"
];
/** @internal */
function computeCandidateStringLegacy(dangerous, charArbitrary, stringSplitter) {
	let candidate;
	try {
		candidate = stringSplitter(dangerous);
	} catch {
		return;
	}
	for (const entry of candidate) if (!charArbitrary.canShrinkWithoutContext(entry)) return;
	return candidate;
}
/** @internal */
function createSlicesForStringLegacy(charArbitrary, stringSplitter) {
	const slicesForString = [];
	for (const dangerous of dangerousStrings) {
		const candidate = computeCandidateStringLegacy(dangerous, charArbitrary, stringSplitter);
		if (candidate !== void 0) safePush(slicesForString, candidate);
	}
	return slicesForString;
}
/** @internal */
const slicesPerArbitrary = /* @__PURE__ */ new WeakMap();
/** @internal */
function createSlicesForStringNoConstraints(charArbitrary) {
	const slicesForString = [];
	for (const dangerous of dangerousStrings) {
		const candidate = tokenizeString(charArbitrary, dangerous, 0, MaxLengthUpperBound);
		if (candidate !== void 0) safePush(slicesForString, candidate);
	}
	return slicesForString;
}
/** @internal */
function createSlicesForString(charArbitrary, constraints) {
	let slices = safeGet(slicesPerArbitrary, charArbitrary);
	if (slices === void 0) {
		slices = createSlicesForStringNoConstraints(charArbitrary);
		safeSet(slicesPerArbitrary, charArbitrary, slices);
	}
	const slicesForConstraints = [];
	for (const slice of slices) if (patternsToStringUnmapperIsValidLength(slice, constraints)) safePush(slicesForConstraints, slice);
	return slicesForConstraints;
}
//#endregion
//#region src/arbitrary/_internals/data/GraphemeRanges.ts
/** @internal */
const asciiAlphabetRanges = [[0, 127]];
/** @internal */
const fullAlphabetRanges = [[0, 55295], [57344, 1114111]];
/**
* Ranges of Graphemes safe to be combined together without any risks to interract between each others.
* 779 ranges, gathering 31828 code-points over the 34931 being declared by http://unicode.org/Public/UNIDATA/UnicodeData.txt on the 17th of August 2024
* @internal
*/
const autonomousGraphemeRanges = [
	[32, 126],
	[160, 172],
	[174, 767],
	[880, 887],
	[890, 895],
	[900, 906],
	[908],
	[910, 929],
	[931, 1154],
	[1162, 1327],
	[1329, 1366],
	[1369, 1418],
	[1421, 1423],
	[1470],
	[1472],
	[1475],
	[1478],
	[1488, 1514],
	[1519, 1524],
	[1542, 1551],
	[1563],
	[1565, 1610],
	[1632, 1647],
	[1649, 1749],
	[1758],
	[1765, 1766],
	[1769],
	[1774, 1805],
	[1808],
	[1810, 1839],
	[1869, 1957],
	[1969],
	[1984, 2026],
	[2036, 2042],
	[2046, 2069],
	[2074],
	[2084],
	[2088],
	[2096, 2110],
	[2112, 2136],
	[2142],
	[2144, 2154],
	[2160, 2190],
	[2208, 2249],
	[2308, 2361],
	[2365],
	[2384],
	[2392, 2401],
	[2404, 2432],
	[2437, 2444],
	[2447, 2448],
	[2451, 2472],
	[2474, 2480],
	[2482],
	[2486, 2489],
	[2493],
	[2510],
	[2524, 2525],
	[2527, 2529],
	[2534, 2557],
	[2565, 2570],
	[2575, 2576],
	[2579, 2600],
	[2602, 2608],
	[2610, 2611],
	[2613, 2614],
	[2616, 2617],
	[2649, 2652],
	[2654],
	[2662, 2671],
	[2674, 2676],
	[2678],
	[2693, 2701],
	[2703, 2705],
	[2707, 2728],
	[2730, 2736],
	[2738, 2739],
	[2741, 2745],
	[2749],
	[2768],
	[2784, 2785],
	[2790, 2801],
	[2809],
	[2821, 2828],
	[2831, 2832],
	[2835, 2856],
	[2858, 2864],
	[2866, 2867],
	[2869, 2873],
	[2877],
	[2908, 2909],
	[2911, 2913],
	[2918, 2935],
	[2947],
	[2949, 2954],
	[2958, 2960],
	[2962, 2965],
	[2969, 2970],
	[2972],
	[2974, 2975],
	[2979, 2980],
	[2984, 2986],
	[2990, 3001],
	[3024],
	[3046, 3066],
	[3077, 3084],
	[3086, 3088],
	[3090, 3112],
	[3114, 3129],
	[3133],
	[3160, 3162],
	[3165],
	[3168, 3169],
	[3174, 3183],
	[3191, 3200],
	[3204, 3212],
	[3214, 3216],
	[3218, 3240],
	[3242, 3251],
	[3253, 3257],
	[3261],
	[3293, 3294],
	[3296, 3297],
	[3302, 3311],
	[3313, 3314],
	[3332, 3340],
	[3342, 3344],
	[3346, 3386],
	[3389],
	[3407],
	[3412, 3414],
	[3416, 3425],
	[3430, 3455],
	[3461, 3478],
	[3482, 3505],
	[3507, 3515],
	[3517],
	[3520, 3526],
	[3558, 3567],
	[3572],
	[3585, 3632],
	[3634],
	[3647, 3654],
	[3663, 3675],
	[3713, 3714],
	[3716],
	[3718, 3722],
	[3724, 3747],
	[3749],
	[3751, 3760],
	[3762],
	[3773],
	[3776, 3780],
	[3782],
	[3792, 3801],
	[3804, 3807],
	[3840, 3863],
	[3866, 3892],
	[3894],
	[3896],
	[3898, 3901],
	[3904, 3911],
	[3913, 3948],
	[3973],
	[3976, 3980],
	[4030, 4037],
	[4039, 4044],
	[4046, 4058],
	[4096, 4138],
	[4159, 4181],
	[4186, 4189],
	[4193],
	[4197, 4198],
	[4206, 4208],
	[4213, 4225],
	[4238],
	[4240, 4249],
	[4254, 4293],
	[4295],
	[4301],
	[4304, 4351],
	[4608, 4680],
	[4682, 4685],
	[4688, 4694],
	[4696],
	[4698, 4701],
	[4704, 4744],
	[4746, 4749],
	[4752, 4784],
	[4786, 4789],
	[4792, 4798],
	[4800],
	[4802, 4805],
	[4808, 4822],
	[4824, 4880],
	[4882, 4885],
	[4888, 4954],
	[4960, 4988],
	[4992, 5017],
	[5024, 5109],
	[5112, 5117],
	[5120, 5788],
	[5792, 5880],
	[5888, 5905],
	[5919, 5937],
	[5941, 5942],
	[5952, 5969],
	[5984, 5996],
	[5998, 6e3],
	[6016, 6067],
	[6100, 6108],
	[6112, 6121],
	[6128, 6137],
	[6144, 6154],
	[6160, 6169],
	[6176, 6264],
	[6272, 6276],
	[6279, 6312],
	[6314],
	[6320, 6389],
	[6400, 6430],
	[6464],
	[6468, 6509],
	[6512, 6516],
	[6528, 6571],
	[6576, 6601],
	[6608, 6618],
	[6622, 6678],
	[6686, 6740],
	[6784, 6793],
	[6800, 6809],
	[6816, 6829],
	[6917, 6963],
	[6981, 6988],
	[6992, 7018],
	[7028, 7038],
	[7043, 7072],
	[7086, 7141],
	[7164, 7203],
	[7227, 7241],
	[7245, 7304],
	[7312, 7354],
	[7357, 7367],
	[7379],
	[7401, 7404],
	[7406, 7411],
	[7413, 7414],
	[7418],
	[7424, 7615],
	[7680, 7957],
	[7960, 7965],
	[7968, 8005],
	[8008, 8013],
	[8016, 8023],
	[8025],
	[8027],
	[8029],
	[8031, 8061],
	[8064, 8116],
	[8118, 8132],
	[8134, 8147],
	[8150, 8155],
	[8157, 8175],
	[8178, 8180],
	[8182, 8190],
	[8192, 8202],
	[8208, 8233],
	[8239, 8287],
	[8304, 8305],
	[8308, 8334],
	[8336, 8348],
	[8352, 8384],
	[8448, 8587],
	[8592, 9254],
	[9280, 9290],
	[9312, 11123],
	[11126, 11157],
	[11159, 11502],
	[11506, 11507],
	[11513, 11557],
	[11559],
	[11565],
	[11568, 11623],
	[11631, 11632],
	[11648, 11670],
	[11680, 11686],
	[11688, 11694],
	[11696, 11702],
	[11704, 11710],
	[11712, 11718],
	[11720, 11726],
	[11728, 11734],
	[11736, 11742],
	[11776, 11869],
	[11904, 11929],
	[11931, 12019],
	[12032, 12245],
	[12272, 12329],
	[12336, 12351],
	[12353, 12438],
	[12443, 12543],
	[12549, 12591],
	[12593, 12686],
	[12688, 12771],
	[12783, 12830],
	[12832, 13312],
	[19903, 19968],
	[40959, 42124],
	[42128, 42182],
	[42192, 42539],
	[42560, 42606],
	[42611],
	[42622, 42653],
	[42656, 42735],
	[42738, 42743],
	[42752, 42954],
	[42960, 42961],
	[42963],
	[42965, 42969],
	[42994, 43009],
	[43011, 43013],
	[43015, 43018],
	[43020, 43042],
	[43048, 43051],
	[43056, 43065],
	[43072, 43127],
	[43138, 43187],
	[43214, 43225],
	[43250, 43262],
	[43264, 43301],
	[43310, 43334],
	[43359],
	[43396, 43442],
	[43457, 43469],
	[43471, 43481],
	[43486, 43492],
	[43494, 43518],
	[43520, 43560],
	[43584, 43586],
	[43588, 43595],
	[43600, 43609],
	[43612, 43642],
	[43646, 43695],
	[43697],
	[43701, 43702],
	[43705, 43709],
	[43712],
	[43714],
	[43739, 43754],
	[43760, 43764],
	[43777, 43782],
	[43785, 43790],
	[43793, 43798],
	[43808, 43814],
	[43816, 43822],
	[43824, 43883],
	[43888, 44002],
	[44011],
	[44016, 44025],
	[44032],
	[55203],
	[63744, 64109],
	[64112, 64217],
	[64256, 64262],
	[64275, 64279],
	[64285],
	[64287, 64310],
	[64312, 64316],
	[64318],
	[64320, 64321],
	[64323, 64324],
	[64326, 64450],
	[64467, 64911],
	[64914, 64967],
	[64975],
	[65008, 65023],
	[65040, 65049],
	[65072, 65106],
	[65108, 65126],
	[65128, 65131],
	[65136, 65140],
	[65142, 65276],
	[65281, 65437],
	[65440, 65470],
	[65474, 65479],
	[65482, 65487],
	[65490, 65495],
	[65498, 65500],
	[65504, 65510],
	[65512, 65518],
	[65532, 65533],
	[65536, 65547],
	[65549, 65574],
	[65576, 65594],
	[65596, 65597],
	[65599, 65613],
	[65616, 65629],
	[65664, 65786],
	[65792, 65794],
	[65799, 65843],
	[65847, 65934],
	[65936, 65948],
	[65952],
	[66e3, 66044],
	[66176, 66204],
	[66208, 66256],
	[66273, 66299],
	[66304, 66339],
	[66349, 66378],
	[66384, 66421],
	[66432, 66461],
	[66463, 66499],
	[66504, 66517],
	[66560, 66717],
	[66720, 66729],
	[66736, 66771],
	[66776, 66811],
	[66816, 66855],
	[66864, 66915],
	[66927, 66938],
	[66940, 66954],
	[66956, 66962],
	[66964, 66965],
	[66967, 66977],
	[66979, 66993],
	[66995, 67001],
	[67003, 67004],
	[67072, 67382],
	[67392, 67413],
	[67424, 67431],
	[67456, 67461],
	[67463, 67504],
	[67506, 67514],
	[67584, 67589],
	[67592],
	[67594, 67637],
	[67639, 67640],
	[67644],
	[67647, 67669],
	[67671, 67742],
	[67751, 67759],
	[67808, 67826],
	[67828, 67829],
	[67835, 67867],
	[67871, 67897],
	[67903],
	[67968, 68023],
	[68028, 68047],
	[68050, 68096],
	[68112, 68115],
	[68117, 68119],
	[68121, 68149],
	[68160, 68168],
	[68176, 68184],
	[68192, 68255],
	[68288, 68324],
	[68331, 68342],
	[68352, 68405],
	[68409, 68437],
	[68440, 68466],
	[68472, 68497],
	[68505, 68508],
	[68521, 68527],
	[68608, 68680],
	[68736, 68786],
	[68800, 68850],
	[68858, 68899],
	[68912, 68921],
	[69216, 69246],
	[69248, 69289],
	[69293],
	[69296, 69297],
	[69376, 69415],
	[69424, 69445],
	[69457, 69465],
	[69488, 69505],
	[69510, 69513],
	[69552, 69579],
	[69600, 69622],
	[69635, 69687],
	[69703, 69709],
	[69714, 69743],
	[69745, 69746],
	[69749],
	[69763, 69807],
	[69819, 69820],
	[69822, 69825],
	[69840, 69864],
	[69872, 69881],
	[69891, 69926],
	[69942, 69956],
	[69959],
	[69968, 70002],
	[70004, 70006],
	[70019, 70066],
	[70081],
	[70084, 70088],
	[70093],
	[70096, 70111],
	[70113, 70132],
	[70144, 70161],
	[70163, 70187],
	[70200, 70205],
	[70207, 70208],
	[70272, 70278],
	[70280],
	[70282, 70285],
	[70287, 70301],
	[70303, 70313],
	[70320, 70366],
	[70384, 70393],
	[70405, 70412],
	[70415, 70416],
	[70419, 70440],
	[70442, 70448],
	[70450, 70451],
	[70453, 70457],
	[70461],
	[70480],
	[70493, 70497],
	[70656, 70708],
	[70727, 70747],
	[70749],
	[70751, 70753],
	[70784, 70831],
	[70852, 70855],
	[70864, 70873],
	[71040, 71086],
	[71105, 71131],
	[71168, 71215],
	[71233, 71236],
	[71248, 71257],
	[71264, 71276],
	[71296, 71338],
	[71352, 71353],
	[71360, 71369],
	[71424, 71450],
	[71472, 71494],
	[71680, 71723],
	[71739],
	[71840, 71922],
	[71935, 71942],
	[71945],
	[71948, 71955],
	[71957, 71958],
	[71960, 71983],
	[72004, 72006],
	[72016, 72025],
	[72096, 72103],
	[72106, 72144],
	[72161, 72163],
	[72192],
	[72203, 72242],
	[72255, 72262],
	[72272],
	[72284, 72323],
	[72346, 72354],
	[72368, 72440],
	[72448, 72457],
	[72704, 72712],
	[72714, 72750],
	[72768, 72773],
	[72784, 72812],
	[72816, 72847],
	[72960, 72966],
	[72968, 72969],
	[72971, 73008],
	[73040, 73049],
	[73056, 73061],
	[73063, 73064],
	[73066, 73097],
	[73112],
	[73120, 73129],
	[73440, 73458],
	[73463, 73464],
	[73476, 73488],
	[73490, 73523],
	[73539, 73561],
	[73648],
	[73664, 73713],
	[73727, 74649],
	[74752, 74862],
	[74864, 74868],
	[74880, 75075],
	[77712, 77810],
	[77824, 78895],
	[78913, 78918],
	[82944, 83526],
	[92160, 92728],
	[92736, 92766],
	[92768, 92777],
	[92782, 92862],
	[92864, 92873],
	[92880, 92909],
	[92917],
	[92928, 92975],
	[92983, 92997],
	[93008, 93017],
	[93019, 93025],
	[93027, 93047],
	[93053, 93071],
	[93760, 93850],
	[93952, 94026],
	[94032],
	[94099, 94111],
	[94176, 94179],
	[94208],
	[100343],
	[100352, 101589],
	[101632],
	[101640],
	[110576, 110579],
	[110581, 110587],
	[110589, 110590],
	[110592, 110882],
	[110898],
	[110928, 110930],
	[110933],
	[110948, 110951],
	[110960, 111355],
	[113664, 113770],
	[113776, 113788],
	[113792, 113800],
	[113808, 113817],
	[113820],
	[113823],
	[118608, 118723],
	[118784, 119029],
	[119040, 119078],
	[119081, 119140],
	[119146, 119148],
	[119171, 119172],
	[119180, 119209],
	[119214, 119274],
	[119296, 119361],
	[119365],
	[119488, 119507],
	[119520, 119539],
	[119552, 119638],
	[119648, 119672],
	[119808, 119892],
	[119894, 119964],
	[119966, 119967],
	[119970],
	[119973, 119974],
	[119977, 119980],
	[119982, 119993],
	[119995],
	[119997, 120003],
	[120005, 120069],
	[120071, 120074],
	[120077, 120084],
	[120086, 120092],
	[120094, 120121],
	[120123, 120126],
	[120128, 120132],
	[120134],
	[120138, 120144],
	[120146, 120485],
	[120488, 120779],
	[120782, 121343],
	[121399, 121402],
	[121453, 121460],
	[121462, 121475],
	[121477, 121483],
	[122624, 122654],
	[122661, 122666],
	[122928, 122989],
	[123136, 123180],
	[123191, 123197],
	[123200, 123209],
	[123214, 123215],
	[123536, 123565],
	[123584, 123627],
	[123632, 123641],
	[123647],
	[124112, 124139],
	[124144, 124153],
	[124896, 124902],
	[124904, 124907],
	[124909, 124910],
	[124912, 124926],
	[124928, 125124],
	[125127, 125135],
	[125184, 125251],
	[125259],
	[125264, 125273],
	[125278, 125279],
	[126065, 126132],
	[126209, 126269],
	[126464, 126467],
	[126469, 126495],
	[126497, 126498],
	[126500],
	[126503],
	[126505, 126514],
	[126516, 126519],
	[126521],
	[126523],
	[126530],
	[126535],
	[126537],
	[126539],
	[126541, 126543],
	[126545, 126546],
	[126548],
	[126551],
	[126553],
	[126555],
	[126557],
	[126559],
	[126561, 126562],
	[126564],
	[126567, 126570],
	[126572, 126578],
	[126580, 126583],
	[126585, 126588],
	[126590],
	[126592, 126601],
	[126603, 126619],
	[126625, 126627],
	[126629, 126633],
	[126635, 126651],
	[126704, 126705],
	[126976, 127019],
	[127024, 127123],
	[127136, 127150],
	[127153, 127167],
	[127169, 127183],
	[127185, 127221],
	[127232, 127405],
	[127488, 127490],
	[127504, 127547],
	[127552, 127560],
	[127568, 127569],
	[127584, 127589],
	[127744, 127994],
	[128e3, 128727],
	[128732, 128748],
	[128752, 128764],
	[128768, 128886],
	[128891, 128985],
	[128992, 129003],
	[129008],
	[129024, 129035],
	[129040, 129095],
	[129104, 129113],
	[129120, 129159],
	[129168, 129197],
	[129200, 129201],
	[129280, 129619],
	[129632, 129645],
	[129648, 129660],
	[129664, 129672],
	[129680, 129725],
	[129727, 129733],
	[129742, 129755],
	[129760, 129768],
	[129776, 129784],
	[129792, 129938],
	[129940, 129994],
	[130032, 130041],
	[131072],
	[173791],
	[173824],
	[177977],
	[177984],
	[178205],
	[178208],
	[183969],
	[183984],
	[191456],
	[191472],
	[192093],
	[194560, 195101],
	[196608],
	[201546],
	[201552],
	[205743]
];
/**
* Same as {@link autonomousGraphemeRanges} but only made of NFD decomposable graphemes.
* We preserved only one version of each decomposition meaning that if c1.normalize('NFD') === c2.normalize('NFD')
* we only preserved the first one to build our set of ranges.
* As such we found 998 NFD decomposable graphemes and kept 980 of them spread into 197 ranges.
* @internal
*/
const autonomousDecomposableGraphemeRanges = [
	[192, 197],
	[199, 207],
	[209, 214],
	[217, 221],
	[224, 229],
	[231, 239],
	[241, 246],
	[249, 253],
	[255, 271],
	[274, 293],
	[296, 304],
	[308, 311],
	[313, 318],
	[323, 328],
	[332, 337],
	[340, 357],
	[360, 382],
	[416, 417],
	[431, 432],
	[461, 476],
	[478, 483],
	[486, 496],
	[500, 501],
	[504, 539],
	[542, 543],
	[550, 563],
	[901, 902],
	[904, 906],
	[908],
	[910, 912],
	[938, 944],
	[970, 974],
	[979, 980],
	[1024, 1025],
	[1027],
	[1031],
	[1036, 1038],
	[1049],
	[1081],
	[1104, 1105],
	[1107],
	[1111],
	[1116, 1118],
	[1142, 1143],
	[1217, 1218],
	[1232, 1235],
	[1238, 1239],
	[1242, 1247],
	[1250, 1255],
	[1258, 1269],
	[1272, 1273],
	[1570, 1574],
	[1728],
	[1730],
	[1747],
	[2345],
	[2353],
	[2356],
	[2392, 2399],
	[2524, 2525],
	[2527],
	[2611],
	[2614],
	[2649, 2651],
	[2654],
	[2908, 2909],
	[2964],
	[3907],
	[3917],
	[3922],
	[3927],
	[3932],
	[3945],
	[4134],
	[6918],
	[6920],
	[6922],
	[6924],
	[6926],
	[6930],
	[7680, 7833],
	[7835],
	[7840, 7929],
	[7936, 7957],
	[7960, 7965],
	[7968, 8005],
	[8008, 8013],
	[8016, 8023],
	[8025],
	[8027],
	[8029],
	[8031, 8048],
	[8050],
	[8052],
	[8054],
	[8056],
	[8058],
	[8060],
	[8064, 8116],
	[8118, 8122],
	[8124],
	[8129, 8132],
	[8134, 8136],
	[8138],
	[8140, 8146],
	[8150, 8154],
	[8157, 8162],
	[8164, 8170],
	[8172, 8173],
	[8178, 8180],
	[8182, 8184],
	[8186],
	[8188],
	[8602, 8603],
	[8622],
	[8653, 8655],
	[8708],
	[8713],
	[8716],
	[8740],
	[8742],
	[8769],
	[8772],
	[8775],
	[8777],
	[8800],
	[8802],
	[8813, 8817],
	[8820, 8821],
	[8824, 8825],
	[8832, 8833],
	[8836, 8837],
	[8840, 8841],
	[8876, 8879],
	[8928, 8931],
	[8938, 8941],
	[10972],
	[12364],
	[12366],
	[12368],
	[12370],
	[12372],
	[12374],
	[12376],
	[12378],
	[12380],
	[12382],
	[12384],
	[12386],
	[12389],
	[12391],
	[12393],
	[12400, 12401],
	[12403, 12404],
	[12406, 12407],
	[12409, 12410],
	[12412, 12413],
	[12436],
	[12446],
	[12460],
	[12462],
	[12464],
	[12466],
	[12468],
	[12470],
	[12472],
	[12474],
	[12476],
	[12478],
	[12480],
	[12482],
	[12485],
	[12487],
	[12489],
	[12496, 12497],
	[12499, 12500],
	[12502, 12503],
	[12505, 12506],
	[12508, 12509],
	[12532],
	[12535, 12538],
	[12542],
	[44032],
	[55203],
	[64285],
	[64287],
	[64298, 64310],
	[64312, 64316],
	[64318],
	[64320, 64321],
	[64323, 64324],
	[64326, 64334],
	[69786],
	[69788],
	[69803],
	[119134, 119140],
	[119227, 119232]
];
//#endregion
//#region src/arbitrary/_internals/helpers/GraphemeRangesHelpers.ts
/** @internal */
const safeStringFromCodePoint$3 = String.fromCodePoint;
/** @internal */
const safeMathMin$2 = Math.min;
/** @internal */
const safeMathMax$1 = Math.max;
/**
* Convert a range into an entry for mapToConstant
* @internal
*/
function convertGraphemeRangeToMapToConstantEntry(range) {
	if (range.length === 1) {
		const codePointString = safeStringFromCodePoint$3(range[0]);
		return {
			num: 1,
			build: () => codePointString
		};
	}
	const rangeStart = range[0];
	return {
		num: range[1] - range[0] + 1,
		build: (idInGroup) => safeStringFromCodePoint$3(rangeStart + idInGroup)
	};
}
/**
* Ranges have to be ordered and non-overlapping
* @internal
*/
function intersectGraphemeRanges(rangesA, rangesB) {
	const mergedRanges = [];
	let cursorA = 0;
	let cursorB = 0;
	while (cursorA < rangesA.length && cursorB < rangesB.length) {
		const rangeA = rangesA[cursorA];
		const rangeAMin = rangeA[0];
		const rangeAMax = rangeA.length === 1 ? rangeA[0] : rangeA[1];
		const rangeB = rangesB[cursorB];
		const rangeBMin = rangeB[0];
		const rangeBMax = rangeB.length === 1 ? rangeB[0] : rangeB[1];
		if (rangeAMax < rangeBMin) cursorA += 1;
		else if (rangeBMax < rangeAMin) cursorB += 1;
		else {
			let min = safeMathMax$1(rangeAMin, rangeBMin);
			const max = safeMathMin$2(rangeAMax, rangeBMax);
			if (mergedRanges.length >= 1) {
				const lastMergedRange = mergedRanges[mergedRanges.length - 1];
				if ((lastMergedRange.length === 1 ? lastMergedRange[0] : lastMergedRange[1]) + 1 === min) {
					min = lastMergedRange[0];
					safePop$1(mergedRanges);
				}
			}
			safePush(mergedRanges, min === max ? [min] : [min, max]);
			if (rangeAMax <= max) cursorA += 1;
			if (rangeBMax <= max) cursorB += 1;
		}
	}
	return mergedRanges;
}
//#endregion
//#region src/arbitrary/_internals/StringUnitArbitrary.ts
/**
* Caching all already instanciated variations of stringUnit
* @internal
*/
const registeredStringUnitInstancesMap = Object.create(null);
/** @internal */
function getAlphabetRanges(alphabet) {
	switch (alphabet) {
		case "full": return fullAlphabetRanges;
		case "ascii": return asciiAlphabetRanges;
	}
}
/** @internal */
function getOrCreateStringUnitInstance(type, alphabet) {
	const key = `${type}:${alphabet}`;
	const registered = registeredStringUnitInstancesMap[key];
	if (registered !== void 0) return registered;
	const alphabetRanges = getAlphabetRanges(alphabet);
	const ranges = type === "binary" ? alphabetRanges : intersectGraphemeRanges(alphabetRanges, autonomousGraphemeRanges);
	const entries = [];
	for (const range of ranges) safePush(entries, convertGraphemeRangeToMapToConstantEntry(range));
	if (type === "grapheme") {
		const decomposedRanges = intersectGraphemeRanges(alphabetRanges, autonomousDecomposableGraphemeRanges);
		for (const range of decomposedRanges) {
			const rawEntry = convertGraphemeRangeToMapToConstantEntry(range);
			safePush(entries, {
				num: rawEntry.num,
				build: (idInGroup) => safeNormalize(rawEntry.build(idInGroup), "NFD")
			});
		}
	}
	const stringUnitInstance = mapToConstant(...entries);
	registeredStringUnitInstancesMap[key] = stringUnitInstance;
	return stringUnitInstance;
}
/** @internal */
function stringUnit(type, alphabet) {
	return getOrCreateStringUnitInstance(type, alphabet);
}
//#endregion
//#region src/arbitrary/string.ts
/** @internal */
function extractUnitArbitrary(constraints) {
	if (typeof constraints.unit === "object") return constraints.unit;
	switch (constraints.unit) {
		case "grapheme": return stringUnit("grapheme", "full");
		case "grapheme-composite": return stringUnit("composite", "full");
		case "grapheme-ascii":
		case void 0: return stringUnit("grapheme", "ascii");
		case "binary": return stringUnit("binary", "full");
		case "binary-ascii": return stringUnit("binary", "ascii");
	}
}
/**
* For strings of {@link char}
*
* @param constraints - Constraints to apply when building instances (since 2.4.0)
*
* @remarks Since 0.0.1
* @public
*/
function string(constraints = {}) {
	const charArbitrary = extractUnitArbitrary(constraints);
	const unmapper = patternsToStringUnmapperFor(charArbitrary, constraints);
	const experimentalCustomSlices = createSlicesForString(charArbitrary, constraints);
	return array(charArbitrary, {
		...constraints,
		experimentalCustomSlices
	}).map(patternsToStringMapper, unmapper);
}
//#endregion
//#region src/arbitrary/_internals/builders/CharacterRangeArbitraryBuilder.ts
const SMap = Map;
const safeStringFromCharCode$1 = String.fromCharCode;
/** @internal */
const lowerCaseMapper = {
	num: 26,
	build: (v) => safeStringFromCharCode$1(v + 97)
};
/** @internal */
const upperCaseMapper = {
	num: 26,
	build: (v) => safeStringFromCharCode$1(v + 65)
};
/** @internal */
const numericMapper = {
	num: 10,
	build: (v) => safeStringFromCharCode$1(v + 48)
};
/** @internal */
function percentCharArbMapper(c) {
	const encoded = SencodeURIComponent(c);
	return c !== encoded ? encoded : `%${safeNumberToString(safeCharCodeAt(c, 0), 16)}`;
}
/** @internal */
function percentCharArbUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported");
	return decodeURIComponent(value);
}
/** @internal */
const percentCharArb = () => string({
	unit: "binary",
	minLength: 1,
	maxLength: 1
}).map(percentCharArbMapper, percentCharArbUnmapper);
let lowerAlphaArbitrary = void 0;
/** @internal */
function getOrCreateLowerAlphaArbitrary() {
	if (lowerAlphaArbitrary === void 0) lowerAlphaArbitrary = mapToConstant(lowerCaseMapper);
	return lowerAlphaArbitrary;
}
let lowerAlphaNumericArbitraries = void 0;
/** @internal */
function getOrCreateLowerAlphaNumericArbitrary(others) {
	if (lowerAlphaNumericArbitraries === void 0) lowerAlphaNumericArbitraries = new SMap();
	let match = safeMapGet(lowerAlphaNumericArbitraries, others);
	if (match === void 0) {
		match = mapToConstant(lowerCaseMapper, numericMapper, {
			num: others.length,
			build: (v) => others[v]
		});
		safeMapSet(lowerAlphaNumericArbitraries, others, match);
	}
	return match;
}
/** @internal */
function buildAlphaNumericArbitrary(others) {
	return mapToConstant(lowerCaseMapper, upperCaseMapper, numericMapper, {
		num: others.length,
		build: (v) => others[v]
	});
}
let alphaNumericPercentArbitraries = void 0;
/** @internal */
function getOrCreateAlphaNumericPercentArbitrary(others) {
	if (alphaNumericPercentArbitraries === void 0) alphaNumericPercentArbitraries = new SMap();
	let match = safeMapGet(alphaNumericPercentArbitraries, others);
	if (match === void 0) {
		match = oneof({
			weight: 10,
			arbitrary: buildAlphaNumericArbitrary(others)
		}, {
			weight: 1,
			arbitrary: percentCharArb()
		});
		safeMapSet(alphaNumericPercentArbitraries, others, match);
	}
	return match;
}
//#endregion
//#region src/arbitrary/option.ts
/**
* For either nil or a value coming from `arb` with custom frequency
*
* @param arb - Arbitrary that will be called to generate a non nil value
* @param constraints - Constraints on the option(since 1.17.0)
*
* @remarks Since 0.0.6
* @public
*/
function option(arb, constraints = {}) {
	const freq = constraints.freq === void 0 ? 6 : constraints.freq;
	const nilValue = safeHasOwnProperty(constraints, "nil") ? constraints.nil : null;
	const weightedArbs = [{
		arbitrary: constant(nilValue),
		weight: 1,
		fallbackValue: { default: nilValue }
	}, {
		arbitrary: arb,
		weight: freq - 1
	}];
	const frequencyConstraints = {
		withCrossShrink: true,
		depthSize: constraints.depthSize,
		maxDepth: constraints.maxDepth,
		depthIdentifier: constraints.depthIdentifier
	};
	return FrequencyArbitrary.from(weightedArbs, frequencyConstraints, "fc.option");
}
//#endregion
//#region src/arbitrary/_internals/helpers/InvalidSubdomainLabelFiIter.ts
/** @internal */
function filterInvalidSubdomainLabel(subdomainLabel) {
	if (subdomainLabel.length > 63) return false;
	return subdomainLabel.length < 4 || subdomainLabel[0] !== "x" || subdomainLabel[1] !== "n" || subdomainLabel[2] !== "-" || subdomainLabel[3] !== "-";
}
//#endregion
//#region src/arbitrary/_internals/AdapterArbitrary.ts
/** @internal */
const AdaptedValue = Symbol("adapted-value");
/** @internal */
function toAdapterValue(rawValue, adapter) {
	const adapted = adapter(rawValue.value_);
	if (!adapted.adapted) return rawValue;
	return new Value(adapted.value, AdaptedValue);
}
/**
* @internal
* Adapt an existing Arbitrary by truncating its generating values
* if they don't fit the requirements
*/
var AdapterArbitrary = class extends Arbitrary {
	constructor(sourceArb, adapter) {
		super();
		this.sourceArb = sourceArb;
		this.adapter = adapter;
		this.adaptValue = (rawValue) => toAdapterValue(rawValue, adapter);
	}
	generate(mrng, biasFactor) {
		const rawValue = this.sourceArb.generate(mrng, biasFactor);
		return this.adaptValue(rawValue);
	}
	canShrinkWithoutContext(value) {
		return this.sourceArb.canShrinkWithoutContext(value) && !this.adapter(value).adapted;
	}
	shrink(value, context) {
		if (context === AdaptedValue) {
			if (!this.sourceArb.canShrinkWithoutContext(value)) return Stream.nil();
			return this.sourceArb.shrink(value, void 0).map(this.adaptValue);
		}
		return this.sourceArb.shrink(value, context).map(this.adaptValue);
	}
};
/** @internal */
function adapter(sourceArb, adapter) {
	return new AdapterArbitrary(sourceArb, adapter);
}
//#endregion
//#region src/arbitrary/domain.ts
/** @internal */
function toSubdomainLabelMapper([f, d]) {
	return d === null ? f : `${f}${d[0]}${d[1]}`;
}
/** @internal */
function toSubdomainLabelUnmapper(value) {
	if (typeof value !== "string" || value.length === 0) throw new Error("Unsupported");
	if (value.length === 1) return [value[0], null];
	return [value[0], [safeSubstring(value, 1, value.length - 1), value[value.length - 1]]];
}
/** @internal */
function subdomainLabel(size) {
	const alphaNumericArb = getOrCreateLowerAlphaNumericArbitrary("");
	return tuple(alphaNumericArb, option(tuple(string({
		unit: getOrCreateLowerAlphaNumericArbitrary("-"),
		size,
		maxLength: 61
	}), alphaNumericArb))).map(toSubdomainLabelMapper, toSubdomainLabelUnmapper).filter(filterInvalidSubdomainLabel);
}
/** @internal */
function labelsMapper(elements) {
	return `${safeJoin(elements[0], ".")}.${elements[1]}`;
}
/** @internal */
function labelsUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported type");
	const lastDotIndex = value.lastIndexOf(".");
	return [safeSplit(safeSubstring(value, 0, lastDotIndex), "."), safeSubstring(value, lastDotIndex + 1)];
}
/** @internal */
function labelsAdapter(labels) {
	const [subDomains, suffix] = labels;
	let lengthNotIncludingIndex = suffix.length;
	for (let index = 0; index !== subDomains.length; ++index) {
		lengthNotIncludingIndex += 1 + subDomains[index].length;
		if (lengthNotIncludingIndex > 255) return {
			adapted: true,
			value: [safeSlice(subDomains, 0, index), suffix]
		};
	}
	return {
		adapted: false,
		value: labels
	};
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
function domain(constraints = {}) {
	const resolvedSize = resolveSize(constraints.size);
	const resolvedSizeMinusOne = relativeSizeToSize("-1", resolvedSize);
	const publicSuffixArb = string({
		unit: getOrCreateLowerAlphaArbitrary(),
		minLength: 2,
		maxLength: 63,
		size: resolvedSizeMinusOne
	});
	return adapter(tuple(array(subdomainLabel(resolvedSize), {
		size: resolvedSizeMinusOne,
		minLength: 1,
		maxLength: 127
	}), publicSuffixArb), labelsAdapter).map(labelsMapper, labelsUnmapper);
}
//#endregion
//#region src/arbitrary/emailAddress.ts
/** @internal */
function dotAdapter(a) {
	let currentLength = a[0].length;
	for (let index = 1; index !== a.length; ++index) {
		currentLength += 1 + a[index].length;
		if (currentLength > 64) return {
			adapted: true,
			value: safeSlice(a, 0, index)
		};
	}
	return {
		adapted: false,
		value: a
	};
}
/** @internal */
function dotMapper(a) {
	return safeJoin(a, ".");
}
/** @internal */
function dotUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported");
	return safeSplit(value, ".");
}
/** @internal */
function atMapper(data) {
	return `${data[0]}@${data[1]}`;
}
/** @internal */
function atUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported");
	return safeSplit(value, "@", 2);
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
function emailAddress(constraints = {}) {
	return tuple(adapter(array(string({
		unit: getOrCreateLowerAlphaNumericArbitrary("!#$%&'*+-/=?^_`{|}~"),
		minLength: 1,
		maxLength: 64,
		size: constraints.size
	}), {
		minLength: 1,
		maxLength: 32,
		size: constraints.size
	}), dotAdapter).map(dotMapper, dotUnmapper), domain({ size: constraints.size })).map(atMapper, atUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/helpers/DoubleHelpers.ts
const safeNegativeInfinity$6 = SNumber.NEGATIVE_INFINITY;
const safePositiveInfinity$6 = SNumber.POSITIVE_INFINITY;
const safeEpsilon = SNumber.EPSILON;
/** @internal */
const INDEX_POSITIVE_INFINITY$1 = SBigInt(2146435072) * SBigInt(4294967296);
/** @internal */
const INDEX_NEGATIVE_INFINITY$1 = -INDEX_POSITIVE_INFINITY$1 - SBigInt(1);
const num2Pow52 = 4503599627370496;
const big2Pow52Mask = SBigInt(0xfffffffffffff);
const big2Pow53 = SBigInt("9007199254740992");
const f64 = /* @__PURE__ */ new Float64Array(1);
const u32$1 = new Uint32Array(f64.buffer, f64.byteOffset);
/** @internal */
function bitCastDoubleToUInt64(f) {
	f64[0] = f;
	return [u32$1[1], u32$1[0]];
}
/**
* Decompose a 64-bit floating point number into its interpreted parts:
* - 53-bit significand (fraction) with implicit bit and sign included
* - 11-bit exponent
*
* - Number.MAX_VALUE = 2**1023    * (1 + (2**52-1)/2**52)
*                    = 2**1023    * (2 - Number.EPSILON)
* - Number.MIN_VALUE = 2**(-1022) * 2**(-52)
* - Number.EPSILON   = 2**(-52)
*
* @param d - 64-bit floating point number to be decomposed into (significand, exponent)
*
* @internal
*/
function decomposeDouble(d) {
	const { 0: hi, 1: lo } = bitCastDoubleToUInt64(d);
	const signBit = hi >>> 31;
	const exponentBits = hi >>> 20 & 2047;
	const significandBits = (hi & 1048575) * 4294967296 + lo;
	const exponent = exponentBits === 0 ? -1022 : exponentBits - 1023;
	let significand = exponentBits === 0 ? 0 : 1;
	significand += significandBits * safeEpsilon;
	significand *= signBit === 0 ? 1 : -1;
	return {
		exponent,
		significand
	};
}
/** @internal */
function indexInDoubleFromDecomp(exponent, significand) {
	if (exponent === -1022) return SBigInt(significand * num2Pow52);
	return SBigInt((significand - 1) * num2Pow52) + (SBigInt(exponent + 1023) << SBigInt(52));
}
/**
* Compute the index of d relative to other available 64-bit floating point numbers
* Rq: Produces negative indexes for negative doubles
*
* @param d - 64-bit floating point number, anything except NaN
*
* @internal
*/
function doubleToIndex(d) {
	if (d === safePositiveInfinity$6) return INDEX_POSITIVE_INFINITY$1;
	if (d === safeNegativeInfinity$6) return INDEX_NEGATIVE_INFINITY$1;
	const decomp = decomposeDouble(d);
	const exponent = decomp.exponent;
	const significand = decomp.significand;
	if (d > 0 || d === 0 && 1 / d === safePositiveInfinity$6) return indexInDoubleFromDecomp(exponent, significand);
	else return -indexInDoubleFromDecomp(exponent, -significand) - SBigInt(1);
}
/**
* Compute the 64-bit floating point number corresponding to the provided indexes
*
* @param n - index of the double
*
* @internal
*/
function indexToDouble(index) {
	if (index < 0) return -indexToDouble(-index - SBigInt(1));
	if (index === INDEX_POSITIVE_INFINITY$1) return safePositiveInfinity$6;
	if (index < big2Pow53) return SNumber(index) * 2 ** -1074;
	const postIndex = index - big2Pow53;
	const exponent = -1021 + SNumber(postIndex >> SBigInt(52));
	return (1 + SNumber(postIndex & big2Pow52Mask) * safeEpsilon) * 2 ** exponent;
}
//#endregion
//#region src/arbitrary/_internals/helpers/FloatingOnlyHelpers.ts
const safeNumberIsInteger$2 = Number.isInteger;
const safeObjectIs$1 = Object.is;
const safeNegativeInfinity$5 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$5 = Number.POSITIVE_INFINITY;
/** @internals */
function refineConstraintsForFloatingOnly(constraints, maxValue, maxNonIntegerValue, onlyIntegersAfterThisValue) {
	const { noDefaultInfinity = false, minExcluded = false, maxExcluded = false, min = noDefaultInfinity ? -maxValue : safeNegativeInfinity$5, max = noDefaultInfinity ? maxValue : safePositiveInfinity$5 } = constraints;
	const effectiveMin = minExcluded ? min < -maxNonIntegerValue ? -onlyIntegersAfterThisValue : Math.max(min, -maxNonIntegerValue) : min === safeNegativeInfinity$5 ? Math.max(min, -onlyIntegersAfterThisValue) : Math.max(min, -maxNonIntegerValue);
	const effectiveMax = maxExcluded ? max > maxNonIntegerValue ? onlyIntegersAfterThisValue : Math.min(max, maxNonIntegerValue) : max === safePositiveInfinity$5 ? Math.min(max, onlyIntegersAfterThisValue) : Math.min(max, maxNonIntegerValue);
	return {
		noDefaultInfinity: false,
		minExcluded: minExcluded || (min !== safeNegativeInfinity$5 || minExcluded) && safeNumberIsInteger$2(effectiveMin),
		maxExcluded: maxExcluded || (max !== safePositiveInfinity$5 || maxExcluded) && safeNumberIsInteger$2(effectiveMax),
		min: safeObjectIs$1(effectiveMin, -0) ? 0 : effectiveMin,
		max: safeObjectIs$1(effectiveMax, 0) ? -0 : effectiveMax,
		noNaN: constraints.noNaN || false
	};
}
//#endregion
//#region src/arbitrary/_internals/helpers/DoubleOnlyHelpers.ts
const safeNegativeInfinity$4 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$4 = Number.POSITIVE_INFINITY;
const safeMaxValue$2 = Number.MAX_VALUE;
const maxNonIntegerValue$1 = 4503599627370495.5;
const onlyIntegersAfterThisValue$1 = 4503599627370496;
/**
* Refine source constraints receive by a double to focus only on non-integer values.
* @param constraints - Source constraints to be refined
*/
function refineConstraintsForDoubleOnly(constraints) {
	return refineConstraintsForFloatingOnly(constraints, safeMaxValue$2, maxNonIntegerValue$1, onlyIntegersAfterThisValue$1);
}
function doubleOnlyMapper(value) {
	return value === 4503599627370496 ? safePositiveInfinity$4 : value === -4503599627370496 ? safeNegativeInfinity$4 : value;
}
function doubleOnlyUnmapper(value) {
	if (typeof value !== "number") throw new Error("Unsupported type");
	return value === safePositiveInfinity$4 ? onlyIntegersAfterThisValue$1 : value === safeNegativeInfinity$4 ? -4503599627370496 : value;
}
//#endregion
//#region src/arbitrary/double.ts
const safeNumberIsInteger$1 = Number.isInteger;
const safeNumberIsNaN$1 = Number.isNaN;
const safeNegativeInfinity$3 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$3 = Number.POSITIVE_INFINITY;
const safeMaxValue$1 = Number.MAX_VALUE;
const safeNaN$1 = NaN;
/**
* Same as {@link doubleToIndex} except it throws in case of invalid double (NaN)
*
* @internal
*/
function safeDoubleToIndex(d, constraintsLabel) {
	if (safeNumberIsNaN$1(d)) throw new Error("fc.double constraints." + constraintsLabel + " must be a 64-bit float");
	return doubleToIndex(d);
}
/** @internal */
function unmapperDoubleToIndex(value) {
	if (typeof value !== "number") throw new Error("Unsupported type");
	return doubleToIndex(value);
}
/** @internal */
function numberIsNotInteger$1(value) {
	return !safeNumberIsInteger$1(value);
}
/** @internal */
function anyDouble(constraints) {
	const { noDefaultInfinity = false, noNaN = false, minExcluded = false, maxExcluded = false, min = noDefaultInfinity ? -safeMaxValue$1 : safeNegativeInfinity$3, max = noDefaultInfinity ? safeMaxValue$1 : safePositiveInfinity$3 } = constraints;
	const minIndexRaw = safeDoubleToIndex(min, "min");
	const minIndex = minExcluded ? minIndexRaw + SBigInt(1) : minIndexRaw;
	const maxIndexRaw = safeDoubleToIndex(max, "max");
	const maxIndex = maxExcluded ? maxIndexRaw - SBigInt(1) : maxIndexRaw;
	if (maxIndex < minIndex) throw new Error("fc.double constraints.min must be smaller or equal to constraints.max");
	if (noNaN) return bigInt({
		min: minIndex,
		max: maxIndex
	}).map(indexToDouble, unmapperDoubleToIndex);
	const positiveMaxIdx = maxIndex > SBigInt(0);
	const minIndexWithNaN = positiveMaxIdx ? minIndex : minIndex - SBigInt(1);
	const maxIndexWithNaN = positiveMaxIdx ? maxIndex + SBigInt(1) : maxIndex;
	return bigInt({
		min: minIndexWithNaN,
		max: maxIndexWithNaN
	}).map((index) => {
		if (maxIndex < index || index < minIndex) return safeNaN$1;
		else return indexToDouble(index);
	}, (value) => {
		if (typeof value !== "number") throw new Error("Unsupported type");
		if (safeNumberIsNaN$1(value)) return maxIndex !== maxIndexWithNaN ? maxIndexWithNaN : minIndexWithNaN;
		return doubleToIndex(value);
	});
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
function double(constraints = {}) {
	if (!constraints.noInteger) return anyDouble(constraints);
	return anyDouble(refineConstraintsForDoubleOnly(constraints)).map(doubleOnlyMapper, doubleOnlyUnmapper).filter(numberIsNotInteger$1);
}
//#endregion
//#region src/arbitrary/_internals/helpers/FloatHelpers.ts
const safeNegativeInfinity$2 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$2 = Number.POSITIVE_INFINITY;
const safeMathImul = Math.imul;
/** @internal */
const MAX_VALUE_32 = 2 ** 127 * (1 + (2 ** 23 - 1) / 2 ** 23);
/** @internal */
const INDEX_POSITIVE_INFINITY = 2139095040;
/** @internal */
const INDEX_NEGATIVE_INFINITY = -2139095041;
const f32 = /* @__PURE__ */ new Float32Array(1);
const u32 = new Uint32Array(f32.buffer, f32.byteOffset);
/** @internal */
function bitCastFloatToUInt32(f) {
	f32[0] = f;
	return u32[0];
}
/**
* Decompose a 32-bit floating point number into its interpreted parts:
* - 24-bit significand (fraction) with implicit bit included
* - 8-bit signed exponent after bias subtraction
*
* Remark in 64-bit floating point number:
* - significand is over 53 bits including sign
* - exponent is over 11 bits including sign
* - Number.MAX_VALUE = 2**1023    * (1 + (2**52-1)/2**52)
* - Number.MIN_VALUE = 2**(-1022) * 2**(-52)
* - Number.EPSILON   = 2**(-52)
*
* @param f - 32-bit floating point number to be decomposed into (significand, exponent)
*
* @internal
*/
function decomposeFloat(f) {
	const bits = bitCastFloatToUInt32(f);
	const signBit = bits >>> 31;
	const exponentBits = bits >>> 23 & 255;
	const significandBits = bits & 8388607;
	const exponent = exponentBits === 0 ? -126 : exponentBits - 127;
	let significand = exponentBits === 0 ? 0 : 1;
	significand += significandBits / 2 ** 23;
	significand *= signBit === 0 ? 1 : -1;
	return {
		exponent,
		significand
	};
}
/** @internal */
function indexInFloatFromDecomp(exponent, significand) {
	if (exponent === -126) return significand * 8388608;
	return safeMathImul(exponent + 127, 8388608) + (significand - 1) * 8388608;
}
/**
* Compute the index of f relative to other available 32-bit floating point numbers
* Rq: Produces negative indexes for negative floats
*
* @param f - 32-bit floating point number
*
* @internal
*/
function floatToIndex(f) {
	if (f === safePositiveInfinity$2) return INDEX_POSITIVE_INFINITY;
	if (f === safeNegativeInfinity$2) return INDEX_NEGATIVE_INFINITY;
	const decomp = decomposeFloat(f);
	const exponent = decomp.exponent;
	const significand = decomp.significand;
	if (f > 0 || f === 0 && 1 / f === safePositiveInfinity$2) return indexInFloatFromDecomp(exponent, significand);
	else return -indexInFloatFromDecomp(exponent, -significand) - 1;
}
/**
* Compute the 32-bit floating point number corresponding to the provided indexes
*
* @param n - index of the float
*
* @internal
*/
function indexToFloat(index) {
	if (index < 0) return -indexToFloat(-index - 1);
	if (index === INDEX_POSITIVE_INFINITY) return safePositiveInfinity$2;
	if (index < 16777216) return index * 2 ** -149;
	const postIndex = index - 16777216;
	const exponent = -125 + (postIndex >> 23);
	return (1 + (postIndex & 8388607) / 8388608) * 2 ** exponent;
}
//#endregion
//#region src/arbitrary/_internals/helpers/FloatOnlyHelpers.ts
const safeNegativeInfinity$1 = Number.NEGATIVE_INFINITY;
const safePositiveInfinity$1 = Number.POSITIVE_INFINITY;
const safeMaxValue = MAX_VALUE_32;
const maxNonIntegerValue = 8388607.5;
const onlyIntegersAfterThisValue = 8388608;
/**
* Refine source constraints receive by a float to focus only on non-integer values.
* @param constraints - Source constraints to be refined
*/
function refineConstraintsForFloatOnly(constraints) {
	return refineConstraintsForFloatingOnly(constraints, safeMaxValue, maxNonIntegerValue, onlyIntegersAfterThisValue);
}
function floatOnlyMapper(value) {
	return value === 8388608 ? safePositiveInfinity$1 : value === -8388608 ? safeNegativeInfinity$1 : value;
}
function floatOnlyUnmapper(value) {
	if (typeof value !== "number") throw new Error("Unsupported type");
	return value === safePositiveInfinity$1 ? onlyIntegersAfterThisValue : value === safeNegativeInfinity$1 ? -8388608 : value;
}
//#endregion
//#region src/arbitrary/float.ts
const safeNumberIsInteger = Number.isInteger;
const safeNumberIsNaN = Number.isNaN;
const safeMathFround = Math.fround;
const safeNegativeInfinity = Number.NEGATIVE_INFINITY;
const safePositiveInfinity = Number.POSITIVE_INFINITY;
const safeNaN = NaN;
/**
* Same as {@link floatToIndex} except it throws if f is NaN or not representable as a 32-bit float
*
* @internal
*/
function safeFloatToIndex(f, constraintsLabel) {
	const errorMessage = "fc.float constraints." + constraintsLabel + " must be a 32-bit float - you can convert any double to a 32-bit float by using `Math.fround(myDouble)`";
	if (safeNumberIsNaN(f) || safeMathFround(f) !== f) throw new Error(errorMessage);
	return floatToIndex(f);
}
/** @internal */
function unmapperFloatToIndex(value) {
	if (typeof value !== "number") throw new Error("Unsupported type");
	return floatToIndex(value);
}
/** @internal */
function numberIsNotInteger(value) {
	return !safeNumberIsInteger(value);
}
function anyFloat(constraints) {
	const { noDefaultInfinity = false, noNaN = false, minExcluded = false, maxExcluded = false, min = noDefaultInfinity ? -MAX_VALUE_32 : safeNegativeInfinity, max = noDefaultInfinity ? MAX_VALUE_32 : safePositiveInfinity } = constraints;
	const minIndexRaw = safeFloatToIndex(min, "min");
	const minIndex = minExcluded ? minIndexRaw + 1 : minIndexRaw;
	const maxIndexRaw = safeFloatToIndex(max, "max");
	const maxIndex = maxExcluded ? maxIndexRaw - 1 : maxIndexRaw;
	if (minIndex > maxIndex) throw new Error("fc.float constraints.min must be smaller or equal to constraints.max");
	if (noNaN) return integer({
		min: minIndex,
		max: maxIndex
	}).map(indexToFloat, unmapperFloatToIndex);
	const minIndexWithNaN = maxIndex > 0 ? minIndex : minIndex - 1;
	const maxIndexWithNaN = maxIndex > 0 ? maxIndex + 1 : maxIndex;
	return integer({
		min: minIndexWithNaN,
		max: maxIndexWithNaN
	}).map((index) => {
		if (index > maxIndex || index < minIndex) return safeNaN;
		else return indexToFloat(index);
	}, (value) => {
		if (typeof value !== "number") throw new Error("Unsupported type");
		if (safeNumberIsNaN(value)) return maxIndex !== maxIndexWithNaN ? maxIndexWithNaN : minIndexWithNaN;
		return floatToIndex(value);
	});
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
function float(constraints = {}) {
	if (!constraints.noInteger) return anyFloat(constraints);
	return anyFloat(refineConstraintsForFloatOnly(constraints)).map(floatOnlyMapper, floatOnlyUnmapper).filter(numberIsNotInteger);
}
//#endregion
//#region src/arbitrary/_internals/helpers/TextEscaper.ts
/** @internal */
function escapeForTemplateString(originalText) {
	return originalText.replace(/([$`\\])/g, "\\$1").replace(/\r/g, "\\r");
}
/** @internal */
function escapeForMultilineComments(originalText) {
	return originalText.replace(/\*\//g, "*\\/");
}
//#endregion
//#region src/utils/hash.ts
/** @internal */
const crc32Table = [
	0,
	1996959894,
	3993919788,
	2567524794,
	124634137,
	1886057615,
	3915621685,
	2657392035,
	249268274,
	2044508324,
	3772115230,
	2547177864,
	162941995,
	2125561021,
	3887607047,
	2428444049,
	498536548,
	1789927666,
	4089016648,
	2227061214,
	450548861,
	1843258603,
	4107580753,
	2211677639,
	325883990,
	1684777152,
	4251122042,
	2321926636,
	335633487,
	1661365465,
	4195302755,
	2366115317,
	997073096,
	1281953886,
	3579855332,
	2724688242,
	1006888145,
	1258607687,
	3524101629,
	2768942443,
	901097722,
	1119000684,
	3686517206,
	2898065728,
	853044451,
	1172266101,
	3705015759,
	2882616665,
	651767980,
	1373503546,
	3369554304,
	3218104598,
	565507253,
	1454621731,
	3485111705,
	3099436303,
	671266974,
	1594198024,
	3322730930,
	2970347812,
	795835527,
	1483230225,
	3244367275,
	3060149565,
	1994146192,
	31158534,
	2563907772,
	4023717930,
	1907459465,
	112637215,
	2680153253,
	3904427059,
	2013776290,
	251722036,
	2517215374,
	3775830040,
	2137656763,
	141376813,
	2439277719,
	3865271297,
	1802195444,
	476864866,
	2238001368,
	4066508878,
	1812370925,
	453092731,
	2181625025,
	4111451223,
	1706088902,
	314042704,
	2344532202,
	4240017532,
	1658658271,
	366619977,
	2362670323,
	4224994405,
	1303535960,
	984961486,
	2747007092,
	3569037538,
	1256170817,
	1037604311,
	2765210733,
	3554079995,
	1131014506,
	879679996,
	2909243462,
	3663771856,
	1141124467,
	855842277,
	2852801631,
	3708648649,
	1342533948,
	654459306,
	3188396048,
	3373015174,
	1466479909,
	544179635,
	3110523913,
	3462522015,
	1591671054,
	702138776,
	2966460450,
	3352799412,
	1504918807,
	783551873,
	3082640443,
	3233442989,
	3988292384,
	2596254646,
	62317068,
	1957810842,
	3939845945,
	2647816111,
	81470997,
	1943803523,
	3814918930,
	2489596804,
	225274430,
	2053790376,
	3826175755,
	2466906013,
	167816743,
	2097651377,
	4027552580,
	2265490386,
	503444072,
	1762050814,
	4150417245,
	2154129355,
	426522225,
	1852507879,
	4275313526,
	2312317920,
	282753626,
	1742555852,
	4189708143,
	2394877945,
	397917763,
	1622183637,
	3604390888,
	2714866558,
	953729732,
	1340076626,
	3518719985,
	2797360999,
	1068828381,
	1219638859,
	3624741850,
	2936675148,
	906185462,
	1090812512,
	3747672003,
	2825379669,
	829329135,
	1181335161,
	3412177804,
	3160834842,
	628085408,
	1382605366,
	3423369109,
	3138078467,
	570562233,
	1426400815,
	3317316542,
	2998733608,
	733239954,
	1555261956,
	3268935591,
	3050360625,
	752459403,
	1541320221,
	2607071920,
	3965973030,
	1969922972,
	40735498,
	2617837225,
	3943577151,
	1913087877,
	83908371,
	2512341634,
	3803740692,
	2075208622,
	213261112,
	2463272603,
	3855990285,
	2094854071,
	198958881,
	2262029012,
	4057260610,
	1759359992,
	534414190,
	2176718541,
	4139329115,
	1873836001,
	414664567,
	2282248934,
	4279200368,
	1711684554,
	285281116,
	2405801727,
	4167216745,
	1634467795,
	376229701,
	2685067896,
	3608007406,
	1308918612,
	956543938,
	2808555105,
	3495958263,
	1231636301,
	1047427035,
	2932959818,
	3654703836,
	1088359270,
	936918e3,
	2847714899,
	3736837829,
	1202900863,
	817233897,
	3183342108,
	3401237130,
	1404277552,
	615818150,
	3134207493,
	3453421203,
	1423857449,
	601450431,
	3009837614,
	3294710456,
	1567103746,
	711928724,
	3020668471,
	3272380065,
	1510334235,
	755167117
];
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
function hash(repr) {
	let crc = 4294967295;
	for (let idx = 0; idx < repr.length; ++idx) {
		const c = safeCharCodeAt(repr, idx);
		if (c < 128) crc = crc32Table[crc & 255 ^ c] ^ crc >> 8;
		else if (c < 2048) {
			crc = crc32Table[crc & 255 ^ (192 | c >> 6 & 31)] ^ crc >> 8;
			crc = crc32Table[crc & 255 ^ (128 | c & 63)] ^ crc >> 8;
		} else if (c >= 55296 && c < 57344) {
			const cNext = safeCharCodeAt(repr, ++idx);
			if (c >= 56320 || cNext < 56320 || cNext > 57343 || Number.isNaN(cNext)) {
				idx -= 1;
				crc = crc32Table[crc & 255 ^ 239] ^ crc >> 8;
				crc = crc32Table[crc & 255 ^ 191] ^ crc >> 8;
				crc = crc32Table[crc & 255 ^ 189] ^ crc >> 8;
			} else {
				const c1 = (c & 1023) + 64;
				const c2 = cNext & 1023;
				crc = crc32Table[crc & 255 ^ (240 | c1 >> 8 & 7)] ^ crc >> 8;
				crc = crc32Table[crc & 255 ^ (128 | c1 >> 2 & 63)] ^ crc >> 8;
				crc = crc32Table[crc & 255 ^ (128 | c2 >> 6 & 15 | (c1 & 3) << 4)] ^ crc >> 8;
				crc = crc32Table[crc & 255 ^ (128 | c2 & 63)] ^ crc >> 8;
			}
		} else {
			crc = crc32Table[crc & 255 ^ (224 | c >> 12 & 15)] ^ crc >> 8;
			crc = crc32Table[crc & 255 ^ (128 | c >> 6 & 63)] ^ crc >> 8;
			crc = crc32Table[crc & 255 ^ (128 | c & 63)] ^ crc >> 8;
		}
	}
	return (crc | 0) + 2147483648;
}
//#endregion
//#region src/arbitrary/noShrink.ts
const stableObjectGetPrototypeOf = Object.getPrototypeOf;
/** @internal */
var NoShrinkArbitrary = class extends Arbitrary {
	constructor(arb) {
		super();
		this.arb = arb;
	}
	generate(mrng, biasFactor) {
		return this.arb.generate(mrng, biasFactor);
	}
	canShrinkWithoutContext(value) {
		return this.arb.canShrinkWithoutContext(value);
	}
	shrink(_value, _context) {
		return Stream.nil();
	}
};
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
function noShrink(arb) {
	if (stableObjectGetPrototypeOf(arb) === NoShrinkArbitrary.prototype && arb.generate === NoShrinkArbitrary.prototype.generate && arb.canShrinkWithoutContext === NoShrinkArbitrary.prototype.canShrinkWithoutContext && arb.shrink === NoShrinkArbitrary.prototype.shrink) return arb;
	return new NoShrinkArbitrary(arb);
}
//#endregion
//#region src/arbitrary/_internals/builders/CompareFunctionArbitraryBuilder.ts
const safeObjectAssign$4 = Object.assign;
const safeObjectKeys$3 = Object.keys;
/** @internal */
function buildCompareFunctionArbitrary(cmp) {
	return tuple(noShrink(integer()), noShrink(integer({
		min: 1,
		max: 4294967295
	}))).map(([seed, hashEnvSize]) => {
		const producer = () => {
			const recorded = {};
			const f = (a, b) => {
				const reprA = stringify(a);
				const reprB = stringify(b);
				const val = cmp(hash(`${seed}${reprA}`) % hashEnvSize, hash(`${seed}${reprB}`) % hashEnvSize);
				recorded[`[${reprA},${reprB}]`] = val;
				return val;
			};
			return safeObjectAssign$4(f, {
				toString: () => {
					const seenValues = safeObjectKeys$3(recorded).sort().map((k) => `${k} => ${stringify(recorded[k])}`).map((line) => `/* ${escapeForMultilineComments(line)} */`);
					return `function(a, b) {
  // With hash and stringify coming from fast-check${seenValues.length !== 0 ? `\n  ${safeJoin(seenValues, "\n  ")}` : ""}
  const cmp = ${cmp};
  const hA = hash('${seed}' + stringify(a)) % ${hashEnvSize};
  const hB = hash('${seed}' + stringify(b)) % ${hashEnvSize};
  return cmp(hA, hB);
}`;
				},
				[cloneMethod]: producer
			});
		};
		return producer();
	});
}
//#endregion
//#region src/arbitrary/compareBooleanFunc.ts
const safeObjectAssign$3 = Object.assign;
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
function compareBooleanFunc() {
	return buildCompareFunctionArbitrary(safeObjectAssign$3((hA, hB) => hA < hB, { toString() {
		return "(hA, hB) => hA < hB";
	} }));
}
//#endregion
//#region src/arbitrary/compareFunc.ts
const safeObjectAssign$2 = Object.assign;
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
function compareFunc() {
	return buildCompareFunctionArbitrary(safeObjectAssign$2((hA, hB) => hA - hB, { toString() {
		return "(hA, hB) => hA - hB";
	} }));
}
//#endregion
//#region src/arbitrary/func.ts
const safeObjectDefineProperties$1 = Object.defineProperties;
const safeObjectKeys$2 = Object.keys;
/**
* For pure functions
*
* @param arb - Arbitrary responsible to produce the values
*
* @remarks Since 1.6.0
* @public
*/
function func(arb) {
	return tuple(array(arb, { minLength: 1 }), noShrink(integer())).map(([outs, seed]) => {
		const producer = () => {
			const recorded = {};
			const f = (...args) => {
				const repr = stringify(args);
				const val = outs[hash(`${seed}${repr}`) % outs.length];
				recorded[repr] = val;
				return hasCloneMethod(val) ? val[cloneMethod]() : val;
			};
			function prettyPrint(stringifiedOuts) {
				const seenValues = safeMap(safeMap(safeSort(safeObjectKeys$2(recorded)), (k) => `${k} => ${stringify(recorded[k])}`), (line) => `/* ${escapeForMultilineComments(line)} */`);
				return `function(...args) {
  // With hash and stringify coming from fast-check${seenValues.length !== 0 ? `\n  ${seenValues.join("\n  ")}` : ""}
  const outs = ${stringifiedOuts};
  return outs[hash('${seed}' + stringify(args)) % outs.length];
}`;
			}
			return safeObjectDefineProperties$1(f, {
				toString: { value: () => prettyPrint(stringify(outs)) },
				[toStringMethod]: { value: () => prettyPrint(stringify(outs)) },
				[asyncToStringMethod]: { value: async () => prettyPrint(await asyncStringify(outs)) },
				[cloneMethod]: {
					value: producer,
					configurable: true
				}
			});
		};
		return producer();
	});
}
//#endregion
//#region src/arbitrary/maxSafeInteger.ts
const safeMinSafeInteger = Number.MIN_SAFE_INTEGER;
const safeMaxSafeInteger$1 = Number.MAX_SAFE_INTEGER;
/**
* For integers between Number.MIN_SAFE_INTEGER (included) and Number.MAX_SAFE_INTEGER (included)
* @remarks Since 1.11.0
* @public
*/
function maxSafeInteger() {
	return new IntegerArbitrary(safeMinSafeInteger, safeMaxSafeInteger$1);
}
//#endregion
//#region src/arbitrary/maxSafeNat.ts
const safeMaxSafeInteger = Number.MAX_SAFE_INTEGER;
/**
* For positive integers between 0 (included) and Number.MAX_SAFE_INTEGER (included)
* @remarks Since 1.11.0
* @public
*/
function maxSafeNat() {
	return new IntegerArbitrary(0, safeMaxSafeInteger);
}
//#endregion
//#region src/arbitrary/_internals/mappers/NatToStringifiedNat.ts
const safeNumberParseInt = Number.parseInt;
/** @internal */
function natToStringifiedNatMapper(options) {
	const [style, v] = options;
	switch (style) {
		case "oct": return `0${safeNumberToString(v, 8)}`;
		case "hex": return `0x${safeNumberToString(v, 16)}`;
		default: return `${v}`;
	}
}
/** @internal */
function tryParseStringifiedNat(stringValue, radix) {
	const parsedNat = safeNumberParseInt(stringValue, radix);
	if (safeNumberToString(parsedNat, radix) !== stringValue) throw new Error("Invalid value");
	return parsedNat;
}
/** @internal */
function natToStringifiedNatUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	if (value.length >= 2 && value[0] === "0") {
		if (value[1] === "x") return ["hex", tryParseStringifiedNat(safeSubstring(value, 2), 16)];
		return ["oct", tryParseStringifiedNat(safeSubstring(value, 1), 8)];
	}
	return ["dec", tryParseStringifiedNat(value, 10)];
}
//#endregion
//#region src/arbitrary/ipV4.ts
/** @internal */
function dotJoinerMapper$1(data) {
	return safeJoin(data, ".");
}
/** @internal */
function dotJoinerUnmapper$1(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	return safeMap(safeSplit(value, "."), (v) => tryParseStringifiedNat(v, 10));
}
/**
* For valid IP v4
*
* Following {@link https://tools.ietf.org/html/rfc3986#section-3.2.2 | RFC 3986}
*
* @remarks Since 1.14.0
* @public
*/
function ipV4() {
	return tuple(nat(255), nat(255), nat(255), nat(255)).map(dotJoinerMapper$1, dotJoinerUnmapper$1);
}
//#endregion
//#region src/arbitrary/_internals/builders/StringifiedNatArbitraryBuilder.ts
/** @internal */
function buildStringifiedNatArbitrary(maxValue) {
	return tuple(constantFrom("dec", "oct", "hex"), nat(maxValue)).map(natToStringifiedNatMapper, natToStringifiedNatUnmapper);
}
//#endregion
//#region src/arbitrary/ipV4Extended.ts
/** @internal */
function dotJoinerMapper(data) {
	return safeJoin(data, ".");
}
/** @internal */
function dotJoinerUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	return safeSplit(value, ".");
}
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
function ipV4Extended() {
	return oneof(tuple(buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(255)).map(dotJoinerMapper, dotJoinerUnmapper), tuple(buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(65535)).map(dotJoinerMapper, dotJoinerUnmapper), tuple(buildStringifiedNatArbitrary(255), buildStringifiedNatArbitrary(16777215)).map(dotJoinerMapper, dotJoinerUnmapper), buildStringifiedNatArbitrary(4294967295));
}
//#endregion
//#region src/arbitrary/_internals/mappers/EntitiesToIPv6.ts
/** @internal */
function readBh(value) {
	if (value.length === 0) return [];
	else return safeSplit(value, ":");
}
/** @internal */
function extractEhAndL(value) {
	const valueSplits = safeSplit(value, ":");
	if (valueSplits.length >= 2 && valueSplits[valueSplits.length - 1].length <= 4) return [safeSlice(valueSplits, 0, valueSplits.length - 2), `${valueSplits[valueSplits.length - 2]}:${valueSplits[valueSplits.length - 1]}`];
	return [safeSlice(valueSplits, 0, valueSplits.length - 1), valueSplits[valueSplits.length - 1]];
}
/** @internal */
function fullySpecifiedMapper(data) {
	return `${safeJoin(data[0], ":")}:${data[1]}`;
}
/** @internal */
function fullySpecifiedUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	return extractEhAndL(value);
}
/** @internal */
function onlyTrailingMapper(data) {
	return `::${safeJoin(data[0], ":")}:${data[1]}`;
}
/** @internal */
function onlyTrailingUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	if (!safeStartsWith(value, "::")) throw new Error("Invalid value");
	return extractEhAndL(safeSubstring(value, 2));
}
/** @internal */
function multiTrailingMapper(data) {
	return `${safeJoin(data[0], ":")}::${safeJoin(data[1], ":")}:${data[2]}`;
}
/** @internal */
function multiTrailingUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	const [bhString, trailingString] = safeSplit(value, "::", 2);
	const [eh, l] = extractEhAndL(trailingString);
	return [
		readBh(bhString),
		eh,
		l
	];
}
/** @internal */
function multiTrailingMapperOne(data) {
	return multiTrailingMapper([
		data[0],
		[data[1]],
		data[2]
	]);
}
/** @internal */
function multiTrailingUnmapperOne(value) {
	const out = multiTrailingUnmapper(value);
	return [
		out[0],
		safeJoin(out[1], ":"),
		out[2]
	];
}
/** @internal */
function singleTrailingMapper(data) {
	return `${safeJoin(data[0], ":")}::${data[1]}`;
}
/** @internal */
function singleTrailingUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	const [bhString, trailing] = safeSplit(value, "::", 2);
	return [readBh(bhString), trailing];
}
/** @internal */
function noTrailingMapper(data) {
	return `${safeJoin(data[0], ":")}::`;
}
/** @internal */
function noTrailingUnmapper(value) {
	if (typeof value !== "string") throw new Error("Invalid type");
	if (!safeEndsWith(value, "::")) throw new Error("Invalid value");
	return [readBh(safeSubstring(value, 0, value.length - 2))];
}
//#endregion
//#region src/arbitrary/ipV6.ts
/** @internal */
function h16sTol32Mapper([a, b]) {
	return `${a}:${b}`;
}
/** @internal */
function h16sTol32Unmapper(value) {
	if (typeof value !== "string") throw new SError("Invalid type");
	if (!value.includes(":")) throw new SError("Invalid value");
	return value.split(":", 2);
}
const items = "0123456789abcdef";
let cachedHexa = void 0;
/** @internal */
function hexa() {
	if (cachedHexa === void 0) cachedHexa = integer({
		min: 0,
		max: 15
	}).map((n) => items[n], (c) => {
		if (typeof c !== "string") throw new SError("Not a string");
		if (c.length !== 1) throw new SError("Invalid length");
		const code = safeCharCodeAt(c, 0);
		if (code <= 57) return code - 48;
		if (code < 97) throw new SError("Invalid character");
		return code - 87;
	});
	return cachedHexa;
}
/**
* For valid IP v6
*
* Following {@link https://tools.ietf.org/html/rfc3986#section-3.2.2 | RFC 3986}
*
* @remarks Since 1.14.0
* @public
*/
function ipV6() {
	const h16Arb = string({
		unit: hexa(),
		minLength: 1,
		maxLength: 4,
		size: "max"
	});
	const ls32Arb = oneof(tuple(h16Arb, h16Arb).map(h16sTol32Mapper, h16sTol32Unmapper), ipV4());
	return oneof(tuple(array(h16Arb, {
		minLength: 6,
		maxLength: 6,
		size: "max"
	}), ls32Arb).map(fullySpecifiedMapper, fullySpecifiedUnmapper), tuple(array(h16Arb, {
		minLength: 5,
		maxLength: 5,
		size: "max"
	}), ls32Arb).map(onlyTrailingMapper, onlyTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 1,
		size: "max"
	}), array(h16Arb, {
		minLength: 4,
		maxLength: 4,
		size: "max"
	}), ls32Arb).map(multiTrailingMapper, multiTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 2,
		size: "max"
	}), array(h16Arb, {
		minLength: 3,
		maxLength: 3,
		size: "max"
	}), ls32Arb).map(multiTrailingMapper, multiTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 3,
		size: "max"
	}), array(h16Arb, {
		minLength: 2,
		maxLength: 2,
		size: "max"
	}), ls32Arb).map(multiTrailingMapper, multiTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 4,
		size: "max"
	}), h16Arb, ls32Arb).map(multiTrailingMapperOne, multiTrailingUnmapperOne), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 5,
		size: "max"
	}), ls32Arb).map(singleTrailingMapper, singleTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 6,
		size: "max"
	}), h16Arb).map(singleTrailingMapper, singleTrailingUnmapper), tuple(array(h16Arb, {
		minLength: 0,
		maxLength: 7,
		size: "max"
	})).map(noTrailingMapper, noTrailingUnmapper));
}
//#endregion
//#region src/arbitrary/_internals/LazyArbitrary.ts
/** @internal */
var LazyArbitrary = class extends Arbitrary {
	constructor(name) {
		super();
		this.name = name;
		this.underlying = null;
	}
	generate(mrng, biasFactor) {
		if (this.underlying === null) throw new Error(`Lazy arbitrary ${JSON.stringify(this.name)} not correctly initialized`);
		return this.underlying.generate(mrng, biasFactor);
	}
	canShrinkWithoutContext(value) {
		if (this.underlying === null) throw new Error(`Lazy arbitrary ${JSON.stringify(this.name)} not correctly initialized`);
		return this.underlying.canShrinkWithoutContext(value);
	}
	shrink(value, context) {
		if (this.underlying === null) throw new Error(`Lazy arbitrary ${JSON.stringify(this.name)} not correctly initialized`);
		return this.underlying.shrink(value, context);
	}
};
//#endregion
//#region src/arbitrary/letrec.ts
const safeGetOwnPropertyNames = Object.getOwnPropertyNames;
/** @internal */
function createLazyArbsPool() {
	const lazyArbsPool = new SMap$2();
	const getLazyFromPool = (key) => {
		let lazyArb = safeMapGet(lazyArbsPool, key);
		if (lazyArb !== void 0) return lazyArb;
		lazyArb = new LazyArbitrary(String(key));
		safeMapSet(lazyArbsPool, key, lazyArb);
		return lazyArb;
	};
	return getLazyFromPool;
}
function letrec(builder) {
	const getLazyFromPool = createLazyArbsPool();
	const strictArbs = builder(getLazyFromPool);
	const declaredArbitraryNames = safeGetOwnPropertyNames(strictArbs);
	for (const name of declaredArbitraryNames) {
		const lazyArb = getLazyFromPool(name);
		lazyArb.underlying = strictArbs[name];
	}
	return strictArbs;
}
//#endregion
//#region src/arbitrary/_internals/InitialPoolForEntityGraphArbitrary.ts
function canHaveAtLeastOneItem(keys, constraints) {
	for (const key of keys) {
		const constraintsOnKey = constraints[key] || {};
		if (constraintsOnKey.maxLength === void 0 || constraintsOnKey.maxLength > 0) return true;
	}
	return false;
}
/** @internal */
function initialPoolForEntityGraph(keys, constraints) {
	if (keys.length === 0) return constant([]);
	if (!canHaveAtLeastOneItem(keys, constraints)) throw new SError("Contraints on pool must accept at least one entity, maxLength cannot sum to 0");
	return tuple(...keys.map((key) => array(constant(key), constraints[key]))).map((values) => safeFlat(values)).filter((names) => names.length > 0);
}
//#endregion
//#region src/arbitrary/_internals/mappers/UnlinkedToLinkedEntities.ts
const safeObjectAssign$1 = Object.assign;
const safeObjectCreate$4 = Object.create;
const safeObjectDefineProperty$1 = Object.defineProperty;
const safeObjectGetPrototypeOf = Object.getPrototypeOf;
const safeObjectPrototype = Object.prototype;
/** @internal */
function withTargetStringifiedValue(stringifiedValue) {
	return safeObjectDefineProperty$1(safeObjectCreate$4(null), toStringMethod, {
		configurable: false,
		enumerable: false,
		writable: false,
		value: () => stringifiedValue
	});
}
/** @internal */
function withReferenceStringifiedValue(type, index) {
	return withTargetStringifiedValue(`<${SString(type)}#${index}>`);
}
/** @internal */
function unlinkedToLinkedEntitiesMapper(unlinkedEntities, producedLinks) {
	const linkedEntities = safeObjectCreate$4(safeObjectPrototype);
	for (const name in unlinkedEntities) {
		const unlinkedEntitiesForName = unlinkedEntities[name];
		const linkedEntitiesForName = [];
		for (const unlinkedEntity of unlinkedEntitiesForName) {
			const linkedEntity = safeObjectAssign$1(safeObjectCreate$4(safeObjectGetPrototypeOf(unlinkedEntity)), unlinkedEntity);
			linkedEntitiesForName.push(linkedEntity);
		}
		linkedEntities[name] = linkedEntitiesForName;
	}
	for (const name in producedLinks) {
		const entityLinks = producedLinks[name];
		for (let entityIndex = 0; entityIndex !== entityLinks.length; ++entityIndex) {
			const entityLinksForInstance = entityLinks[entityIndex];
			const linkedInstance = linkedEntities[name][entityIndex];
			for (const prop in entityLinksForInstance) {
				const propValue = entityLinksForInstance[prop];
				linkedInstance[prop] = propValue.index === void 0 ? void 0 : typeof propValue.index === "number" ? linkedEntities[propValue.type][propValue.index] : safeMap(propValue.index, (index) => linkedEntities[propValue.type][index]);
			}
			safeObjectDefineProperty$1(linkedInstance, toStringMethod, {
				configurable: false,
				enumerable: false,
				writable: false,
				value: () => {
					const unlinkedEntity = unlinkedEntities[name][entityIndex];
					const entity = safeObjectAssign$1(safeObjectCreate$4(safeObjectGetPrototypeOf(unlinkedEntity)), unlinkedEntity);
					for (const prop in entityLinksForInstance) {
						const propValue = entityLinksForInstance[prop];
						entity[prop] = propValue.index === void 0 ? void 0 : typeof propValue.index === "number" ? withReferenceStringifiedValue(propValue.type, propValue.index) : safeMap(propValue.index, (index) => withReferenceStringifiedValue(propValue.type, index));
					}
					return stringify(entity);
				}
			});
		}
	}
	return linkedEntities;
}
//#endregion
//#region src/arbitrary/_internals/helpers/BuildInversedRelationsMapping.ts
/**
* Build mapping from forward to inverse relationships
* @internal
*/
function buildInversedRelationsMapping(relations) {
	let foundInversedRelations = 0;
	const requestedInversedRelations = new SMap$2();
	for (const name in relations) {
		const relationsForName = relations[name];
		for (const fieldName in relationsForName) {
			const relation = relationsForName[fieldName];
			if (relation.arity !== "inverse") continue;
			let existingOnes = safeMapGet(requestedInversedRelations, relation.type);
			if (existingOnes === void 0) {
				existingOnes = new SMap$2();
				safeMapSet(requestedInversedRelations, relation.type, existingOnes);
			}
			if (safeMapHas(existingOnes, relation.forwardRelationship)) throw new SError(`Cannot declare multiple inverse relationships for the same forward relationship ${SString(relation.forwardRelationship)} on type ${SString(relation.type)}`);
			safeMapSet(existingOnes, relation.forwardRelationship, {
				type: name,
				property: fieldName
			});
			foundInversedRelations += 1;
		}
	}
	const inversedRelations = new SMap$2();
	if (foundInversedRelations === 0) return inversedRelations;
	for (const name in relations) {
		const relationsForName = relations[name];
		const requestedInversedRelationsForName = safeMapGet(requestedInversedRelations, name);
		if (requestedInversedRelationsForName === void 0) continue;
		for (const fieldName in relationsForName) {
			const relation = relationsForName[fieldName];
			if (relation.arity === "inverse") continue;
			const requestedIfAny = safeMapGet(requestedInversedRelationsForName, fieldName);
			if (requestedIfAny === void 0) continue;
			if (requestedIfAny.type !== relation.type) throw new SError(`Inverse relationship ${SString(requestedIfAny.property)} on type ${SString(requestedIfAny.type)} references forward relationship ${SString(fieldName)} but types do not match`);
			safeMapSet(inversedRelations, relation, requestedIfAny);
		}
	}
	if (inversedRelations.size !== foundInversedRelations) throw new SError(`Some inverse relationships could not be matched with their corresponding forward relationships`);
	return inversedRelations;
}
//#endregion
//#region src/arbitrary/_internals/OnTheFlyLinksForEntityGraphArbitrary.ts
const safeObjectAssign = Object.assign;
const safeObjectCreate$3 = Object.create;
/** @internal */
function produceLinkUnitaryIndexArbitrary(strategy, currentIndexIfSameType, countInTargetType) {
	switch (strategy) {
		case "exclusive": return constant(countInTargetType);
		case "successor": return noBias(integer({
			min: currentIndexIfSameType !== void 0 ? currentIndexIfSameType + 1 : 0,
			max: countInTargetType
		}));
		case "any": return noBias(integer({
			min: 0,
			max: countInTargetType
		}));
	}
}
/** @internal */
function buildLinkIndexArbitrary(arity, strategy, currentIndexIfSameType, countInTargetType, currentEntityDepth) {
	const linkArbitrary = produceLinkUnitaryIndexArbitrary(strategy, currentIndexIfSameType, countInTargetType);
	switch (arity) {
		case "0-1": return option(linkArbitrary, {
			nil: void 0,
			depthIdentifier: currentEntityDepth
		});
		case "1": return linkArbitrary;
		case "many": {
			let randomUnicity = 0;
			return option(uniqueArray(linkArbitrary, {
				depthIdentifier: currentEntityDepth,
				selector: (v) => v === countInTargetType ? v + ++randomUnicity : v,
				minLength: 1
			}), {
				nil: [],
				depthIdentifier: currentEntityDepth
			}).map((values) => {
				let offset = 0;
				return safeMap(values, (v) => v === countInTargetType ? v + offset++ : v);
			});
		}
	}
}
/** @internal */
function createEmptyLinksInstanceFor(relations, targetType) {
	const emptyLinksInstance = safeObjectCreate$3(null);
	const relationsForType = relations[targetType];
	for (const name in relationsForType) {
		const relation = relationsForType[name];
		if (relation.arity === "inverse") emptyLinksInstance[name] = {
			type: relation.type,
			index: []
		};
	}
	return emptyLinksInstance;
}
/** @internal */
function assertAcceptableRelations(relations) {
	const nonExclusiveEntities = new SSet();
	const exclusiveEntities = new SSet();
	for (const name in relations) {
		const relationsForName = relations[name];
		for (const fieldName in relationsForName) {
			const relation = relationsForName[fieldName];
			if (relation.arity === "inverse") continue;
			if (relation.strategy === "exclusive") {
				if (safeHas(nonExclusiveEntities, relation.type)) throw new SError(`Cannot mix exclusive with other strategies for type ${SString(relation.type)}`);
				safeAdd(exclusiveEntities, relation.type);
			} else {
				if (safeHas(exclusiveEntities, relation.type)) throw new SError(`Cannot mix exclusive with other strategies for type ${SString(relation.type)}`);
				safeAdd(nonExclusiveEntities, relation.type);
			}
			if (relation.strategy === "successor" && relation.type !== name) throw new SError(`Cannot mix types for the strategy successor`);
			if (relation.strategy === "successor" && relation.arity === "1") throw new SError(`Cannot use an arity of 1 for the strategy successor`);
		}
	}
}
/** @internal */
function draftNextProductionState(state, offset) {
	const { producedLinks, toBeProducedEntities } = state;
	const nextIndex = state.nextIndex + offset;
	const newProducedLinks = safeObjectAssign(safeObjectCreate$3(null), producedLinks);
	function getOrCreateProducedLinksFor(type) {
		if (newProducedLinks[type] === producedLinks[type]) newProducedLinks[type] = safeSlice(producedLinks[type]);
		return newProducedLinks[type];
	}
	function getOrCreateLinksFor(type, indexInType) {
		const producedLinksForType = getOrCreateProducedLinksFor(type);
		if (producedLinksForType[indexInType] === producedLinks[type][indexInType]) producedLinksForType[indexInType] = safeObjectAssign(safeObjectCreate$3(null), producedLinks[type][indexInType]);
		return producedLinksForType[indexInType];
	}
	function getOrCreateRelationFor(type, indexInType, property) {
		const links = getOrCreateLinksFor(type, indexInType);
		const originalEntity = producedLinks[type][indexInType];
		if (originalEntity !== void 0 && links[property] === originalEntity[property]) {
			const sharedRelation = links[property];
			links[property] = {
				type: sharedRelation.type,
				index: typeof sharedRelation.index === "object" ? safeSlice(sharedRelation.index) : sharedRelation.index
			};
		}
		return links[property];
	}
	let newToBeProducedEntities = void 0;
	const toBeProduced = toBeProducedEntities[nextIndex];
	return {
		setOutboundLink: (name, value) => {
			const currentLinks = getOrCreateLinksFor(toBeProduced.type, toBeProduced.indexInType);
			currentLinks[name] = value;
		},
		enqueueNewEntity: (relations, targetType) => {
			const producedLinksInTargetType = getOrCreateProducedLinksFor(targetType);
			const newEntityIndexInType = producedLinksInTargetType.length;
			if (newToBeProducedEntities === void 0) newToBeProducedEntities = safeSlice(toBeProducedEntities);
			safePush(newToBeProducedEntities, {
				type: targetType,
				indexInType: newEntityIndexInType,
				depth: toBeProduced.depth + 1
			});
			safePush(producedLinksInTargetType, createEmptyLinksInstanceFor(relations, targetType));
			return newEntityIndexInType;
		},
		appendBackReference: (targetType, indexInType, property) => {
			const knownInversedLinks = getOrCreateRelationFor(targetType, indexInType, property).index;
			safePush(knownInversedLinks, toBeProduced.indexInType);
		},
		commit: () => ({
			producedLinks: newProducedLinks,
			toBeProducedEntities: newToBeProducedEntities !== void 0 ? newToBeProducedEntities : toBeProducedEntities,
			nextIndex: nextIndex + 1
		})
	};
}
/** @internal */
function buildInitialProductionState(relations, defaultEntities) {
	const producedLinks = safeObjectCreate$3(null);
	for (const name in relations) producedLinks[name] = [];
	const toBeProducedEntities = [];
	for (const name of defaultEntities) {
		safePush(toBeProducedEntities, {
			type: name,
			indexInType: producedLinks[name].length,
			depth: 0
		});
		safePush(producedLinks[name], createEmptyLinksInstanceFor(relations, name));
	}
	return {
		producedLinks,
		toBeProducedEntities,
		nextIndex: 0
	};
}
/** @internal */
function buildEntityStepArbitrary(relations, inversedRelations, lastState, offset) {
	const lastProducedLinks = lastState.producedLinks;
	const currentEntity = lastState.toBeProducedEntities[lastState.nextIndex + offset];
	const currentRelations = relations[currentEntity.type];
	const currentEntityDepth = createDepthIdentifier();
	currentEntityDepth.depth = currentEntity.depth;
	const subArbitraries = [];
	const linkContexts = [];
	for (const name in currentRelations) {
		const relation = currentRelations[name];
		if (relation.arity === "inverse") continue;
		const targetType = relation.type;
		const countInTargetType = lastProducedLinks[targetType].length;
		safePush(subArbitraries, buildLinkIndexArbitrary(relation.arity, relation.strategy || "any", targetType === currentEntity.type ? currentEntity.indexInType : void 0, countInTargetType, currentEntityDepth));
		safePush(linkContexts, {
			name,
			relation,
			sentinelLinkIndex: countInTargetType
		});
	}
	if (subArbitraries.length === 0) return;
	return tuple(...subArbitraries).map((results) => {
		const state = draftNextProductionState(lastState, offset);
		for (let resultIndex = 0; resultIndex !== results.length; ++resultIndex) {
			const linkOrLinks = results[resultIndex];
			const { name, relation, sentinelLinkIndex } = linkContexts[resultIndex];
			const effectiveLinks = [];
			const links = linkOrLinks === void 0 ? [] : typeof linkOrLinks === "number" ? [linkOrLinks] : linkOrLinks;
			for (const link of links) {
				let newEntityIndexInType;
				if (link >= sentinelLinkIndex) newEntityIndexInType = state.enqueueNewEntity(relations, relation.type);
				else newEntityIndexInType = link;
				safePush(effectiveLinks, newEntityIndexInType);
				const inversed = safeMapGet(inversedRelations, relation);
				if (inversed !== void 0) state.appendBackReference(relation.type, newEntityIndexInType, inversed.property);
			}
			state.setOutboundLink(name, {
				type: relation.type,
				index: linkOrLinks === void 0 ? void 0 : typeof linkOrLinks === "number" ? effectiveLinks[0] : effectiveLinks
			});
		}
		return state.commit();
	});
}
/** @internal */
function onTheFlyLinksForEntityGraph(relations, defaultEntities) {
	assertAcceptableRelations(relations);
	const inversedRelations = buildInversedRelationsMapping(relations);
	return chainUntil(constant(buildInitialProductionState(relations, defaultEntities)), (state) => {
		if (state.nextIndex >= state.toBeProducedEntities.length) return;
		let offset = 0;
		let next = void 0;
		while (next === void 0 && state.nextIndex + offset < state.toBeProducedEntities.length) {
			next = buildEntityStepArbitrary(relations, inversedRelations, state, offset);
			offset += 1;
		}
		return next;
	}).map((state) => {
		return state.producedLinks;
	});
}
//#endregion
//#region src/arbitrary/_internals/helpers/EnumerableKeysExtractor.ts
const safeObjectKeys$1 = Object.keys;
const safeObjectGetOwnPropertySymbols$1 = Object.getOwnPropertySymbols;
const safeObjectGetOwnPropertyDescriptor$1 = Object.getOwnPropertyDescriptor;
/** @internal */
function extractEnumerableKeys(instance) {
	const keys = safeObjectKeys$1(instance);
	const symbols = safeObjectGetOwnPropertySymbols$1(instance);
	for (let index = 0; index !== symbols.length; ++index) {
		const symbol = symbols[index];
		const descriptor = safeObjectGetOwnPropertyDescriptor$1(instance, symbol);
		if (descriptor && descriptor.enumerable) keys.push(symbol);
	}
	return keys;
}
//#endregion
//#region src/arbitrary/_internals/mappers/ValuesAndSeparateKeysToObject.ts
const safeObjectCreate$2 = Object.create;
const safeObjectDefineProperty = Object.defineProperty;
const safeObjectGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
const safeObjectGetOwnPropertyNames = Object.getOwnPropertyNames;
const safeObjectGetOwnPropertySymbols = Object.getOwnPropertySymbols;
/** @internal */
function buildValuesAndSeparateKeysToObjectMapper(keys, noKeyValue) {
	return function valuesAndSeparateKeysToObjectMapper(definition) {
		const obj = definition[definition.length - 1] ? safeObjectCreate$2(null) : {};
		for (let idx = 0; idx !== keys.length; ++idx) {
			const valueWrapper = definition[idx];
			if (valueWrapper !== noKeyValue) {
				const key = keys[idx];
				if (key === "__proto__") safeObjectDefineProperty(obj, key, {
					value: valueWrapper,
					configurable: true,
					enumerable: true,
					writable: true
				});
				else obj[key] = valueWrapper;
			}
		}
		return obj;
	};
}
/** @internal */
function buildValuesAndSeparateKeysToObjectUnmapper(keys, noKeyValue) {
	return function valuesAndSeparateKeysToObjectUnmapper(value) {
		if (typeof value !== "object" || value === null) throw new Error("Incompatible instance received: should be a non-null object");
		const hasNullPrototype = Object.getPrototypeOf(value) === null;
		const hasObjectPrototype = "constructor" in value && value.constructor === Object;
		if (!hasNullPrototype && !hasObjectPrototype) throw new Error("Incompatible instance received: should be of exact type Object");
		let extractedPropertiesCount = 0;
		const extractedValues = [];
		for (let idx = 0; idx !== keys.length; ++idx) {
			const descriptor = safeObjectGetOwnPropertyDescriptor(value, keys[idx]);
			if (descriptor !== void 0) {
				if (!descriptor.configurable || !descriptor.enumerable || !descriptor.writable) throw new Error("Incompatible instance received: should contain only c/e/w properties");
				if (descriptor.get !== void 0 || descriptor.set !== void 0) throw new Error("Incompatible instance received: should contain only no get/set properties");
				++extractedPropertiesCount;
				safePush(extractedValues, descriptor.value);
			} else safePush(extractedValues, noKeyValue);
		}
		const namePropertiesCount = safeObjectGetOwnPropertyNames(value).length;
		const symbolPropertiesCount = safeObjectGetOwnPropertySymbols(value).length;
		if (extractedPropertiesCount !== namePropertiesCount + symbolPropertiesCount) throw new Error("Incompatible instance received: should not contain extra properties");
		return [...extractedValues, hasNullPrototype];
	};
}
//#endregion
//#region src/arbitrary/_internals/builders/PartialRecordArbitraryBuilder.ts
const noKeyValue = Symbol("no-key");
/** @internal */
function buildPartialRecordArbitrary(recordModel, requiredKeys, noNullPrototype) {
	const keys = extractEnumerableKeys(recordModel);
	const arbs = [];
	for (let index = 0; index !== keys.length; ++index) {
		const k = keys[index];
		const requiredArbitrary = recordModel[k];
		if (requiredKeys === void 0 || safeIndexOf(requiredKeys, k) !== -1) safePush(arbs, requiredArbitrary);
		else safePush(arbs, option(requiredArbitrary, { nil: noKeyValue }));
	}
	return tuple(...arbs, noNullPrototype ? constant(false) : boolean()).map(buildValuesAndSeparateKeysToObjectMapper(keys, noKeyValue), buildValuesAndSeparateKeysToObjectUnmapper(keys, noKeyValue));
}
//#endregion
//#region src/arbitrary/record.ts
function record(recordModel, constraints) {
	const noNullPrototype = constraints !== void 0 && !!constraints.noNullPrototype;
	if (constraints === void 0) return buildPartialRecordArbitrary(recordModel, void 0, noNullPrototype);
	if (!("requiredKeys" in constraints && constraints.requiredKeys !== void 0)) return buildPartialRecordArbitrary(recordModel, void 0, noNullPrototype);
	const requiredKeys = ("requiredKeys" in constraints ? constraints.requiredKeys : void 0) || [];
	for (let idx = 0; idx !== requiredKeys.length; ++idx) {
		const descriptor = Object.getOwnPropertyDescriptor(recordModel, requiredKeys[idx]);
		if (descriptor === void 0) throw new Error(`requiredKeys cannot reference keys that have not been defined in recordModel`);
		if (!descriptor.enumerable) throw new Error(`requiredKeys cannot reference keys that are not enumerable in recordModel`);
	}
	return buildPartialRecordArbitrary(recordModel, requiredKeys, noNullPrototype);
}
//#endregion
//#region src/arbitrary/_internals/UnlinkedEntitiesForEntityGraph.ts
const safeObjectCreate$1 = Object.create;
/** @internal */
function unlinkedEntitiesForEntityGraph(arbitraries, countFor, unicityConstraintsFor, constraints) {
	const recordModel = safeObjectCreate$1(null);
	for (const name in arbitraries) {
		const entityRecordModel = arbitraries[name];
		const entityArbitrary = record(entityRecordModel, constraints);
		const count = countFor(name);
		const unicityConstraints = unicityConstraintsFor(name);
		const arrayConstraints = {
			minLength: count,
			maxLength: count
		};
		recordModel[name] = unicityConstraints !== void 0 ? uniqueArray(entityArbitrary, {
			...arrayConstraints,
			selector: unicityConstraints
		}) : array(entityArbitrary, arrayConstraints);
	}
	return record(recordModel);
}
//#endregion
//#region src/arbitrary/entityGraph.ts
const safeObjectCreate = Object.create;
const safeObjectKeys = Object.keys;
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
function entityGraph(arbitraries, relations, constraints = {}) {
	const allKeys = safeObjectKeys(arbitraries);
	const initialPoolConstraints = constraints.initialPoolConstraints || safeObjectCreate(null);
	const unicityConstraints = constraints.unicityConstraints || safeObjectCreate(null);
	const unlinkedContraints = { noNullPrototype: constraints.noNullPrototype };
	return initialPoolForEntityGraph(allKeys, initialPoolConstraints).chain((defaultEntities) => onTheFlyLinksForEntityGraph(relations, defaultEntities).chain((producedLinks) => unlinkedEntitiesForEntityGraph(arbitraries, (name) => producedLinks[name].length, (name) => unicityConstraints[name], unlinkedContraints).map((unlinkedEntities) => unlinkedToLinkedEntitiesMapper(unlinkedEntities, producedLinks))));
}
//#endregion
//#region src/arbitrary/_internals/mappers/WordsToLorem.ts
/** @internal */
function wordsToJoinedStringMapper(words) {
	return safeJoin(safeMap(words, (w) => w[w.length - 1] === "," ? safeSubstring(w, 0, w.length - 1) : w), " ");
}
/** @internal */
function wordsToJoinedStringUnmapperFor(wordsArbitrary) {
	return function wordsToJoinedStringUnmapper(value) {
		if (typeof value !== "string") throw new Error("Unsupported type");
		const words = [];
		for (const candidate of safeSplit(value, " ")) if (wordsArbitrary.canShrinkWithoutContext(candidate)) safePush(words, candidate);
		else if (wordsArbitrary.canShrinkWithoutContext(candidate + ",")) safePush(words, candidate + ",");
		else throw new Error("Unsupported word");
		return words;
	};
}
/** @internal */
function wordsToSentenceMapper(words) {
	let sentence = safeJoin(words, " ");
	if (sentence[sentence.length - 1] === ",") sentence = safeSubstring(sentence, 0, sentence.length - 1);
	return safeToUpperCase(sentence[0]) + safeSubstring(sentence, 1) + ".";
}
/** @internal */
function wordsToSentenceUnmapperFor(wordsArbitrary) {
	return function wordsToSentenceUnmapper(value) {
		if (typeof value !== "string") throw new Error("Unsupported type");
		if (value.length < 2 || value[value.length - 1] !== "." || value[value.length - 2] === "," || safeToUpperCase(safeToLowerCase(value[0])) !== value[0]) throw new Error("Unsupported value");
		const adaptedValue = safeToLowerCase(value[0]) + safeSubstring(value, 1, value.length - 1);
		const words = [];
		const candidates = safeSplit(adaptedValue, " ");
		for (let idx = 0; idx !== candidates.length; ++idx) {
			const candidate = candidates[idx];
			if (wordsArbitrary.canShrinkWithoutContext(candidate)) safePush(words, candidate);
			else if (idx === candidates.length - 1 && wordsArbitrary.canShrinkWithoutContext(candidate + ",")) safePush(words, candidate + ",");
			else throw new Error("Unsupported word");
		}
		return words;
	};
}
/** @internal */
function sentencesToParagraphMapper(sentences) {
	return safeJoin(sentences, " ");
}
/** @internal */
function sentencesToParagraphUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported type");
	const sentences = safeSplit(value, ". ");
	for (let idx = 0; idx < sentences.length - 1; ++idx) sentences[idx] += ".";
	return sentences;
}
//#endregion
//#region src/arbitrary/lorem.ts
/**
* Helper function responsible to build the entries for oneof
* @internal
*/
const h = (v, w) => {
	return {
		arbitrary: constant(v),
		weight: w
	};
};
/**
* Number of occurences extracted from the lorem ipsum:
* {@link https://fr.wikipedia.org/wiki/Faux-texte#Lorem_ipsum_(version_populaire)}
*
* Code generated using:
* >  Object.entries(
* >    text
* >      .replace(/[\r\n]/g, ' ')
* >      .split(' ')
* >      .filter(w => w.length > 0)
* >      .map(w => w.toLowerCase())
* >      .map(w => w[w.length-1] === '.' ? w.substr(0, w.length -1) : w)
* >      .reduce((acc, cur) => { acc[cur] = (acc[cur] || 0) + 1; return acc; }, {})
* >  )
* >  .sort(([w1, n1], [w2, n2]) => n2 - n1)
* >  .reduce((acc, [w, n]) => acc.concat([`h(${JSON.stringify(w)}, ${n})`]), [])
* >  .join(',')
*
* @internal
*/
function loremWord() {
	return oneof(h("non", 6), h("adipiscing", 5), h("ligula", 5), h("enim", 5), h("pellentesque", 5), h("in", 5), h("augue", 5), h("et", 5), h("nulla", 5), h("lorem", 4), h("sit", 4), h("sed", 4), h("diam", 4), h("fermentum", 4), h("ut", 4), h("eu", 4), h("aliquam", 4), h("mauris", 4), h("vitae", 4), h("felis", 4), h("ipsum", 3), h("dolor", 3), h("amet,", 3), h("elit", 3), h("euismod", 3), h("mi", 3), h("orci", 3), h("erat", 3), h("praesent", 3), h("egestas", 3), h("leo", 3), h("vel", 3), h("sapien", 3), h("integer", 3), h("curabitur", 3), h("convallis", 3), h("purus", 3), h("risus", 2), h("suspendisse", 2), h("lectus", 2), h("nec,", 2), h("ultricies", 2), h("sed,", 2), h("cras", 2), h("elementum", 2), h("ultrices", 2), h("maecenas", 2), h("massa,", 2), h("varius", 2), h("a,", 2), h("semper", 2), h("proin", 2), h("nec", 2), h("nisl", 2), h("amet", 2), h("duis", 2), h("congue", 2), h("libero", 2), h("vestibulum", 2), h("pede", 2), h("blandit", 2), h("sodales", 2), h("ante", 2), h("nibh", 2), h("ac", 2), h("aenean", 2), h("massa", 2), h("suscipit", 2), h("sollicitudin", 2), h("fusce", 2), h("tempus", 2), h("aliquam,", 2), h("nunc", 2), h("ullamcorper", 2), h("rhoncus", 2), h("metus", 2), h("faucibus,", 2), h("justo", 2), h("magna", 2), h("at", 2), h("tincidunt", 2), h("consectetur", 1), h("tortor,", 1), h("dignissim", 1), h("congue,", 1), h("non,", 1), h("porttitor,", 1), h("nonummy", 1), h("molestie,", 1), h("est", 1), h("eleifend", 1), h("mi,", 1), h("arcu", 1), h("scelerisque", 1), h("vitae,", 1), h("consequat", 1), h("in,", 1), h("pretium", 1), h("volutpat", 1), h("pharetra", 1), h("tempor", 1), h("bibendum", 1), h("odio", 1), h("dui", 1), h("primis", 1), h("faucibus", 1), h("luctus", 1), h("posuere", 1), h("cubilia", 1), h("curae,", 1), h("hendrerit", 1), h("velit", 1), h("mauris,", 1), h("gravida", 1), h("ornare", 1), h("ut,", 1), h("pulvinar", 1), h("varius,", 1), h("turpis", 1), h("nibh,", 1), h("eros", 1), h("id", 1), h("aliquet", 1), h("quis", 1), h("lobortis", 1), h("consectetuer", 1), h("morbi", 1), h("vehicula", 1), h("tortor", 1), h("tellus,", 1), h("id,", 1), h("eu,", 1), h("quam", 1), h("feugiat,", 1), h("posuere,", 1), h("iaculis", 1), h("lectus,", 1), h("tristique", 1), h("mollis,", 1), h("nisl,", 1), h("vulputate", 1), h("sem", 1), h("vivamus", 1), h("placerat", 1), h("imperdiet", 1), h("cursus", 1), h("rutrum", 1), h("iaculis,", 1), h("augue,", 1), h("lacus", 1));
}
/**
* For lorem ipsum string of words or sentences with maximal number of words or sentences
*
* @param constraints - Constraints to be applied onto the generated value (since 2.5.0)
*
* @remarks Since 0.0.1
* @public
*/
function lorem(constraints = {}) {
	const { maxCount, mode = "words", size } = constraints;
	if (maxCount !== void 0 && maxCount < 1) throw new Error(`lorem has to produce at least one word/sentence`);
	const wordArbitrary = loremWord();
	if (mode === "sentences") return array(array(wordArbitrary, {
		minLength: 1,
		size: "small"
	}).map(wordsToSentenceMapper, wordsToSentenceUnmapperFor(wordArbitrary)), {
		minLength: 1,
		maxLength: maxCount,
		size
	}).map(sentencesToParagraphMapper, sentencesToParagraphUnmapper);
	else return array(wordArbitrary, {
		minLength: 1,
		maxLength: maxCount,
		size
	}).map(wordsToJoinedStringMapper, wordsToJoinedStringUnmapperFor(wordArbitrary));
}
//#endregion
//#region src/arbitrary/_internals/mappers/ArrayToMap.ts
/** @internal */
function arrayToMapMapper(data) {
	return new Map(data);
}
/** @internal */
function arrayToMapUnmapper(value) {
	if (typeof value !== "object" || value === null) throw new Error("Incompatible instance received: should be a non-null object");
	if (!("constructor" in value) || value.constructor !== Map) throw new Error("Incompatible instance received: should be of exact type Map");
	return Array.from(value);
}
//#endregion
//#region src/arbitrary/map.ts
/** @internal */
function mapKeyExtractor(entry) {
	return entry[0];
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
function map(keyArb, valueArb, constraints = {}) {
	return uniqueArray(tuple(keyArb, valueArb), {
		minLength: constraints.minKeys,
		maxLength: constraints.maxKeys,
		size: constraints.size,
		selector: mapKeyExtractor,
		depthIdentifier: constraints.depthIdentifier,
		comparator: "SameValueZero"
	}).map(arrayToMapMapper, arrayToMapUnmapper);
}
//#endregion
//#region src/arbitrary/memo.ts
/** @internal */
let contextRemainingDepth = 10;
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
function memo(builder) {
	const previous = {};
	return ((maxDepth) => {
		const n = maxDepth !== void 0 ? maxDepth : contextRemainingDepth;
		if (!safeHasOwnProperty(previous, n)) {
			const prev = contextRemainingDepth;
			contextRemainingDepth = n - 1;
			previous[n] = builder(n);
			contextRemainingDepth = prev;
		}
		return previous[n];
	});
}
//#endregion
//#region src/arbitrary/_internals/helpers/ToggleFlags.ts
/** @internal */
function countToggledBits(n) {
	let count = 0;
	while (n > SBigInt(0)) {
		if (n & SBigInt(1)) ++count;
		n >>= SBigInt(1);
	}
	return count;
}
/** @internal */
function computeNextFlags(flags, nextSize) {
	const allowedMask = (SBigInt(1) << SBigInt(nextSize)) - SBigInt(1);
	const preservedFlags = flags & allowedMask;
	let numMissingFlags = countToggledBits(flags - preservedFlags);
	let nFlags = preservedFlags;
	for (let mask = SBigInt(1); mask <= allowedMask && numMissingFlags !== 0; mask <<= SBigInt(1)) if (!(nFlags & mask)) {
		nFlags |= mask;
		--numMissingFlags;
	}
	return nFlags;
}
/** @internal */
function computeTogglePositions(chars, toggleCase) {
	const positions = [];
	for (let idx = chars.length - 1; idx !== -1; --idx) if (toggleCase(chars[idx]) !== chars[idx]) safePush(positions, idx);
	return positions;
}
/**
* Compute the flags required to move from untoggledChars to toggledChars
*
* @param untoggledChars - Original string split into characters
* @param toggledChars - Toggled version of the string
* @param togglePositions - Array referencing all case sensitive indexes in chars
*
* @internal
*/
function computeFlagsFromChars(untoggledChars, toggledChars, togglePositions) {
	let flags = SBigInt(0);
	for (let idx = 0, mask = SBigInt(1); idx !== togglePositions.length; ++idx, mask <<= SBigInt(1)) if (untoggledChars[togglePositions[idx]] !== toggledChars[togglePositions[idx]]) flags |= mask;
	return flags;
}
/**
* Apply flags onto chars
*
* @param chars - Original string split into characters (warning perform side-effects on it)
* @param flags - One flag/bit per entry in togglePositions - 1 means change case of the character
* @param togglePositions - Array referencing all case sensitive indexes in chars
* @param toggleCase - Toggle one char
*
* @internal
*/
function applyFlagsOnChars(chars, flags, togglePositions, toggleCase) {
	for (let idx = 0, mask = SBigInt(1); idx !== togglePositions.length; ++idx, mask <<= SBigInt(1)) if (flags & mask) chars[togglePositions[idx]] = toggleCase(chars[togglePositions[idx]]);
}
//#endregion
//#region src/arbitrary/_internals/MixedCaseArbitrary.ts
/** @internal */
var MixedCaseArbitrary = class extends Arbitrary {
	constructor(stringArb, toggleCase, untoggleAll) {
		super();
		this.stringArb = stringArb;
		this.toggleCase = toggleCase;
		this.untoggleAll = untoggleAll;
	}
	/**
	* Create a proper context
	* @param rawStringValue
	* @param flagsValue
	*/
	buildContextFor(rawStringValue, flagsValue) {
		return {
			rawString: rawStringValue.value,
			rawStringContext: rawStringValue.context,
			flags: flagsValue.value,
			flagsContext: flagsValue.context
		};
	}
	generate(mrng, biasFactor) {
		const rawStringValue = this.stringArb.generate(mrng, biasFactor);
		const chars = [...rawStringValue.value];
		const togglePositions = computeTogglePositions(chars, this.toggleCase);
		const flagsValue = bigInt(SBigInt(0), (SBigInt(1) << SBigInt(togglePositions.length)) - SBigInt(1)).generate(mrng, void 0);
		applyFlagsOnChars(chars, flagsValue.value, togglePositions, this.toggleCase);
		return new Value(safeJoin(chars, ""), this.buildContextFor(rawStringValue, flagsValue));
	}
	canShrinkWithoutContext(value) {
		if (typeof value !== "string") return false;
		return this.untoggleAll !== void 0 ? this.stringArb.canShrinkWithoutContext(this.untoggleAll(value)) : this.stringArb.canShrinkWithoutContext(value);
	}
	shrink(value, context) {
		let contextSafe;
		if (context !== void 0) contextSafe = context;
		else if (this.untoggleAll !== void 0) {
			const untoggledValue = this.untoggleAll(value);
			const valueChars = [...value];
			const untoggledValueChars = [...untoggledValue];
			contextSafe = {
				rawString: untoggledValue,
				rawStringContext: void 0,
				flags: computeFlagsFromChars(untoggledValueChars, valueChars, computeTogglePositions(untoggledValueChars, this.toggleCase)),
				flagsContext: void 0
			};
		} else contextSafe = {
			rawString: value,
			rawStringContext: void 0,
			flags: SBigInt(0),
			flagsContext: void 0
		};
		const rawString = contextSafe.rawString;
		const flags = contextSafe.flags;
		return this.stringArb.shrink(rawString, contextSafe.rawStringContext).map((nRawStringValue) => {
			const nChars = [...nRawStringValue.value];
			const nTogglePositions = computeTogglePositions(nChars, this.toggleCase);
			const nFlags = computeNextFlags(flags, nTogglePositions.length);
			applyFlagsOnChars(nChars, nFlags, nTogglePositions, this.toggleCase);
			return new Value(safeJoin(nChars, ""), this.buildContextFor(nRawStringValue, new Value(nFlags, void 0)));
		}).join(makeLazy(() => {
			const chars = [...rawString];
			const togglePositions = computeTogglePositions(chars, this.toggleCase);
			return bigInt(SBigInt(0), (SBigInt(1) << SBigInt(togglePositions.length)) - SBigInt(1)).shrink(flags, contextSafe.flagsContext).map((nFlagsValue) => {
				const nChars = safeSlice(chars);
				applyFlagsOnChars(nChars, nFlagsValue.value, togglePositions, this.toggleCase);
				return new Value(safeJoin(nChars, ""), this.buildContextFor(new Value(rawString, contextSafe.rawStringContext), nFlagsValue));
			});
		}));
	}
};
//#endregion
//#region src/arbitrary/mixedCase.ts
/** @internal */
function defaultToggleCase(rawChar) {
	const upper = safeToUpperCase(rawChar);
	if (upper !== rawChar) return upper;
	return safeToLowerCase(rawChar);
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
function mixedCase(stringArb, constraints) {
	return new MixedCaseArbitrary(stringArb, constraints && constraints.toggleCase || defaultToggleCase, constraints && constraints.untoggleAll);
}
//#endregion
//#region src/arbitrary/float32Array.ts
/** @internal */
function toTypedMapper$1(data) {
	return SFloat32Array.from(data);
}
/** @internal */
function fromTypedUnmapper$1(value) {
	if (!(value instanceof SFloat32Array)) throw new Error("Unexpected type");
	return [...value];
}
/**
* For Float32Array
* @remarks Since 2.9.0
* @public
*/
function float32Array(constraints = {}) {
	return array(float(constraints), constraints).map(toTypedMapper$1, fromTypedUnmapper$1);
}
//#endregion
//#region src/arbitrary/float64Array.ts
/** @internal */
function toTypedMapper(data) {
	return SFloat64Array.from(data);
}
/** @internal */
function fromTypedUnmapper(value) {
	if (!(value instanceof SFloat64Array)) throw new Error("Unexpected type");
	return [...value];
}
/**
* For Float64Array
* @remarks Since 2.9.0
* @public
*/
function float64Array(constraints = {}) {
	return array(double(constraints), constraints).map(toTypedMapper, fromTypedUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/builders/TypedIntArrayArbitraryBuilder.ts
/** @internal */
function typedIntArrayArbitraryArbitraryBuilder(constraints, defaultMin, defaultMax, TypedArrayClass, arbitraryBuilder) {
	const generatorName = TypedArrayClass.name;
	const { min = defaultMin, max = defaultMax, ...arrayConstraints } = constraints;
	if (min > max) throw new Error(`Invalid range passed to ${generatorName}: min must be lower than or equal to max`);
	if (min < defaultMin) throw new Error(`Invalid min value passed to ${generatorName}: min must be greater than or equal to ${defaultMin}`);
	if (max > defaultMax) throw new Error(`Invalid max value passed to ${generatorName}: max must be lower than or equal to ${defaultMax}`);
	return array(arbitraryBuilder({
		min,
		max
	}), arrayConstraints).map((data) => TypedArrayClass.from(data), (value) => {
		if (!(value instanceof TypedArrayClass)) throw new Error("Invalid type");
		return [...value];
	});
}
//#endregion
//#region src/arbitrary/int16Array.ts
/**
* For Int16Array
* @remarks Since 2.9.0
* @public
*/
function int16Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, -32768, 32767, SInt16Array, integer);
}
//#endregion
//#region src/arbitrary/int32Array.ts
/**
* For Int32Array
* @remarks Since 2.9.0
* @public
*/
function int32Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, -2147483648, 2147483647, SInt32Array, integer);
}
//#endregion
//#region src/arbitrary/int8Array.ts
/**
* For Int8Array
* @remarks Since 2.9.0
* @public
*/
function int8Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, -128, 127, SInt8Array, integer);
}
//#endregion
//#region src/arbitrary/uint16Array.ts
/**
* For Uint16Array
* @remarks Since 2.9.0
* @public
*/
function uint16Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, 0, 65535, SUint16Array, integer);
}
//#endregion
//#region src/arbitrary/uint32Array.ts
/**
* For Uint32Array
* @remarks Since 2.9.0
* @public
*/
function uint32Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, 0, 4294967295, SUint32Array, integer);
}
//#endregion
//#region src/arbitrary/uint8Array.ts
/**
* For Uint8Array
* @remarks Since 2.9.0
* @public
*/
function uint8Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, 0, 255, SUint8Array, integer);
}
//#endregion
//#region src/arbitrary/uint8ClampedArray.ts
/**
* For Uint8ClampedArray
* @remarks Since 2.9.0
* @public
*/
function uint8ClampedArray(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, 0, 255, SUint8ClampedArray, integer);
}
//#endregion
//#region src/arbitrary/_internals/WithShrinkFromOtherArbitrary.ts
/** @internal */
function isSafeContext(context) {
	return context !== void 0;
}
/** @internal */
function toGeneratorValue(value) {
	if (value.hasToBeCloned) return new Value(value.value_, { generatorContext: value.context }, () => value.value);
	return new Value(value.value_, { generatorContext: value.context });
}
/** @internal */
function toShrinkerValue(value) {
	if (value.hasToBeCloned) return new Value(value.value_, { shrinkerContext: value.context }, () => value.value);
	return new Value(value.value_, { shrinkerContext: value.context });
}
/** @internal */
var WithShrinkFromOtherArbitrary = class extends Arbitrary {
	constructor(generatorArbitrary, shrinkerArbitrary) {
		super();
		this.generatorArbitrary = generatorArbitrary;
		this.shrinkerArbitrary = shrinkerArbitrary;
	}
	generate(mrng, biasFactor) {
		return toGeneratorValue(this.generatorArbitrary.generate(mrng, biasFactor));
	}
	canShrinkWithoutContext(value) {
		return this.shrinkerArbitrary.canShrinkWithoutContext(value);
	}
	shrink(value, context) {
		if (!isSafeContext(context)) return this.shrinkerArbitrary.shrink(value, void 0).map(toShrinkerValue);
		if ("generatorContext" in context) return this.generatorArbitrary.shrink(value, context.generatorContext).map(toGeneratorValue);
		return this.shrinkerArbitrary.shrink(value, context.shrinkerContext).map(toShrinkerValue);
	}
};
//#endregion
//#region src/arbitrary/_internals/builders/RestrictedIntegerArbitraryBuilder.ts
/** @internal */
function restrictedIntegerArbitraryBuilder(min, maxGenerated, max) {
	const generatorArbitrary = integer({
		min,
		max: maxGenerated
	});
	if (maxGenerated === max) return generatorArbitrary;
	return new WithShrinkFromOtherArbitrary(generatorArbitrary, integer({
		min,
		max
	}));
}
//#endregion
//#region src/arbitrary/sparseArray.ts
const safeMathMin$1 = Math.min;
const safeMathMax = Math.max;
const safeArrayIsArray$1 = SArray.isArray;
const safeObjectEntries = Object.entries;
/** @internal */
function extractMaxIndex(indexesAndValues) {
	let maxIndex = -1;
	for (let index = 0; index !== indexesAndValues.length; ++index) maxIndex = safeMathMax(maxIndex, indexesAndValues[index][0]);
	return maxIndex;
}
/** @internal */
function arrayFromItems(length, indexesAndValues) {
	const array = SArray(length);
	for (let index = 0; index !== indexesAndValues.length; ++index) {
		const it = indexesAndValues[index];
		if (it[0] < length) array[it[0]] = it[1];
	}
	return array;
}
/**
* For sparse arrays of values coming from `arb`
* @param arb - Arbitrary used to generate the values inside the sparse array
* @param constraints - Constraints to apply when building instances
* @remarks Since 2.13.0
* @public
*/
function sparseArray(arb, constraints = {}) {
	const { size, minNumElements = 0, maxLength = MaxLengthUpperBound, maxNumElements = maxLength, noTrailingHole, depthIdentifier } = constraints;
	const maxGeneratedLength = maxGeneratedLengthFromSizeForArbitrary(size, maxGeneratedLengthFromSizeForArbitrary(size, minNumElements, maxNumElements, constraints.maxNumElements !== void 0), maxLength, constraints.maxLength !== void 0);
	if (minNumElements > maxLength) throw new Error(`The minimal number of non-hole elements cannot be higher than the maximal length of the array`);
	if (minNumElements > maxNumElements) throw new Error(`The minimal number of non-hole elements cannot be higher than the maximal number of non-holes`);
	const resultedMaxNumElements = safeMathMin$1(maxNumElements, maxLength);
	const resultedSizeMaxNumElements = constraints.maxNumElements !== void 0 || size !== void 0 ? size : "=";
	const sparseArrayNoTrailingHole = uniqueArray(tuple(restrictedIntegerArbitraryBuilder(0, safeMathMax(maxGeneratedLength - 1, 0), safeMathMax(maxLength - 1, 0)), arb), {
		size: resultedSizeMaxNumElements,
		minLength: minNumElements,
		maxLength: resultedMaxNumElements,
		selector: (item) => item[0],
		depthIdentifier
	}).map((items) => {
		return arrayFromItems(extractMaxIndex(items) + 1, items);
	}, (value) => {
		if (!safeArrayIsArray$1(value)) throw new Error("Not supported entry type");
		if (noTrailingHole && value.length !== 0 && !(value.length - 1 in value)) throw new Error("No trailing hole");
		return safeMap(safeObjectEntries(value), (entry) => [Number(entry[0]), entry[1]]);
	});
	if (noTrailingHole || maxLength === minNumElements) return sparseArrayNoTrailingHole;
	return tuple(sparseArrayNoTrailingHole, restrictedIntegerArbitraryBuilder(minNumElements, maxGeneratedLength, maxLength)).map((data) => {
		const sparse = data[0];
		const targetLength = data[1];
		if (sparse.length >= targetLength) return sparse;
		const longerSparse = safeSlice(sparse);
		longerSparse.length = targetLength;
		return longerSparse;
	}, (value) => {
		if (!safeArrayIsArray$1(value)) throw new Error("Not supported entry type");
		return [value, value.length];
	});
}
//#endregion
//#region src/arbitrary/_internals/mappers/ArrayToSet.ts
/** @internal */
function arrayToSetMapper(data) {
	return new Set(data);
}
/** @internal */
function arrayToSetUnmapper(value) {
	if (typeof value !== "object" || value === null) throw new Error("Incompatible instance received: should be a non-null object");
	if (!("constructor" in value) || value.constructor !== Set) throw new Error("Incompatible instance received: should be of exact type Set");
	return Array.from(value);
}
//#endregion
//#region src/arbitrary/set.ts
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
function set(arb, constraints = {}) {
	return uniqueArray(arb, {
		minLength: constraints.minLength,
		maxLength: constraints.maxLength,
		size: constraints.size,
		depthIdentifier: constraints.depthIdentifier,
		comparator: "SameValueZero"
	}).map(arrayToSetMapper, arrayToSetUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/builders/AnyArbitraryBuilder.ts
/** @internal */
function dictOf(ka, va, maxKeys, size, depthIdentifier, withNullPrototype) {
	return dictionary(ka, va, {
		maxKeys,
		noNullPrototype: !withNullPrototype,
		size,
		depthIdentifier
	});
}
/** @internal */
function typedArray(constraints) {
	return oneof(int8Array(constraints), uint8Array(constraints), uint8ClampedArray(constraints), int16Array(constraints), uint16Array(constraints), int32Array(constraints), uint32Array(constraints), float32Array(constraints), float64Array(constraints));
}
/** @internal */
function anyArbitraryBuilder(constraints) {
	const arbitrariesForBase = constraints.values;
	const depthSize = constraints.depthSize;
	const depthIdentifier = createDepthIdentifier();
	const maxDepth = constraints.maxDepth;
	const maxKeys = constraints.maxKeys;
	const size = constraints.size;
	const baseArb = oneof(...arbitrariesForBase, ...constraints.withBigInt ? [bigInt()] : [], ...constraints.withDate ? [date()] : []);
	return letrec((tie) => ({
		anything: oneof({
			maxDepth,
			depthSize,
			depthIdentifier
		}, baseArb, tie("array"), tie("object"), ...constraints.withMap ? [tie("map")] : [], ...constraints.withSet ? [tie("set")] : [], ...constraints.withObjectString ? [tie("anything").map((o) => stringify(o))] : [], ...constraints.withTypedArray ? [typedArray({
			maxLength: maxKeys,
			size
		})] : [], ...constraints.withSparseArray ? [sparseArray(tie("anything"), {
			maxNumElements: maxKeys,
			size,
			depthIdentifier
		})] : []),
		keys: constraints.withObjectString ? oneof({
			arbitrary: constraints.key,
			weight: 10
		}, {
			arbitrary: tie("anything").map((o) => stringify(o)),
			weight: 1
		}) : constraints.key,
		array: array(tie("anything"), {
			maxLength: maxKeys,
			size,
			depthIdentifier
		}),
		set: set(tie("anything"), {
			maxLength: maxKeys,
			size,
			depthIdentifier
		}),
		map: oneof(map(tie("keys"), tie("anything"), {
			maxKeys,
			size,
			depthIdentifier
		}), map(tie("anything"), tie("anything"), {
			maxKeys,
			size,
			depthIdentifier
		})),
		object: dictOf(tie("keys"), tie("anything"), maxKeys, size, depthIdentifier, constraints.withNullPrototype)
	})).anything;
}
//#endregion
//#region src/arbitrary/_internals/mappers/UnboxedToBoxed.ts
/** @internal */
function unboxedToBoxedMapper(value) {
	switch (typeof value) {
		case "boolean": return new SBoolean(value);
		case "number": return new SNumber(value);
		case "string": return new SString(value);
		default: return value;
	}
}
/** @internal */
function unboxedToBoxedUnmapper(value) {
	if (typeof value !== "object" || value === null || !("constructor" in value)) return value;
	return value.constructor === SBoolean || value.constructor === SNumber || value.constructor === SString ? value.valueOf() : value;
}
//#endregion
//#region src/arbitrary/_internals/builders/BoxedArbitraryBuilder.ts
/** @internal */
function boxedArbitraryBuilder(arb) {
	return arb.map(unboxedToBoxedMapper, unboxedToBoxedUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/helpers/QualifiedObjectConstraints.ts
/** @internal */
function defaultValues(constraints, stringArbitrary) {
	return [
		boolean(),
		maxSafeInteger(),
		double(),
		stringArbitrary(constraints),
		oneof(stringArbitrary(constraints), constant(null), constant(void 0))
	];
}
/** @internal */
function boxArbitraries(arbs) {
	return arbs.map((arb) => boxedArbitraryBuilder(arb));
}
/** @internal */
function boxArbitrariesIfNeeded(arbs, boxEnabled) {
	return boxEnabled ? boxArbitraries(arbs).concat(arbs) : arbs;
}
/**
* Convert constraints of type ObjectConstraints into fully qualified constraints
* @internal
*/
function toQualifiedObjectConstraints(settings = {}) {
	const valueConstraints = {
		size: settings.size,
		unit: "stringUnit" in settings ? settings.stringUnit : settings.withUnicodeString ? "binary" : void 0
	};
	return {
		key: settings.key !== void 0 ? settings.key : string(valueConstraints),
		values: boxArbitrariesIfNeeded(settings.values !== void 0 ? settings.values : defaultValues(valueConstraints, string), settings.withBoxedValues === true),
		depthSize: settings.depthSize,
		maxDepth: settings.maxDepth,
		maxKeys: settings.maxKeys,
		size: settings.size,
		withSet: settings.withSet === true,
		withMap: settings.withMap === true,
		withObjectString: settings.withObjectString === true,
		withNullPrototype: settings.withNullPrototype === true,
		withBigInt: settings.withBigInt === true,
		withDate: settings.withDate === true,
		withTypedArray: settings.withTypedArray === true,
		withSparseArray: settings.withSparseArray === true
	};
}
//#endregion
//#region src/arbitrary/object.ts
/** @internal */
function objectInternal(constraints) {
	return dictionary(constraints.key, anyArbitraryBuilder(constraints), {
		maxKeys: constraints.maxKeys,
		noNullPrototype: !constraints.withNullPrototype,
		size: constraints.size
	});
}
function object(constraints) {
	return objectInternal(toQualifiedObjectConstraints(constraints));
}
//#endregion
//#region src/arbitrary/_internals/helpers/JsonConstraintsBuilder.ts
/**
* Derive `ObjectConstraints` from a `JsonSharedConstraints`
* @internal
*/
function jsonConstraintsBuilder(stringArbitrary, constraints) {
	const { depthSize, maxDepth } = constraints;
	return {
		key: stringArbitrary,
		values: [
			boolean(),
			double({
				noDefaultInfinity: true,
				noNaN: true
			}),
			stringArbitrary,
			constant(null)
		],
		depthSize,
		maxDepth
	};
}
//#endregion
//#region src/arbitrary/anything.ts
function anything(constraints) {
	return anyArbitraryBuilder(toQualifiedObjectConstraints(constraints));
}
//#endregion
//#region src/arbitrary/jsonValue.ts
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
function jsonValue(constraints = {}) {
	const noUnicodeString = constraints.noUnicodeString === void 0 || constraints.noUnicodeString === true;
	return anything(jsonConstraintsBuilder("stringUnit" in constraints ? string({ unit: constraints.stringUnit }) : noUnicodeString ? string() : string({ unit: "binary" }), constraints));
}
//#endregion
//#region src/arbitrary/json.ts
/** @internal */
const safeJsonStringify = JSON.stringify;
/** @internal */
const safeJsonParse = JSON.parse;
/** @internal */
function jsonStringUnmapper(value) {
	if (typeof value !== "string") throw new SError("Cannot unmap the passed value");
	return safeJsonParse(value);
}
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
function json(constraints = {}) {
	return jsonValue(constraints).map(safeJsonStringify, jsonStringUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/StreamArbitrary.ts
const safeObjectDefineProperties = Object.defineProperties;
/** @internal */
function prettyPrint(numSeen, seenValuesStrings) {
	return `Stream(${seenValuesStrings !== void 0 ? `${safeJoin(seenValuesStrings, ",")}…` : `${numSeen} emitted`})`;
}
/** @internal */
var StreamArbitrary = class extends Arbitrary {
	constructor(arb, history) {
		super();
		this.arb = arb;
		this.history = history;
	}
	generate(mrng, biasFactor) {
		const appliedBiasFactor = biasFactor !== void 0 && mrng.nextInt(1, biasFactor) === 1 ? biasFactor : void 0;
		const enrichedProducer = () => {
			const seenValues = this.history ? [] : null;
			let numSeenValues = 0;
			const g = function* (arb, clonedMrng) {
				while (true) {
					const value = arb.generate(clonedMrng, appliedBiasFactor).value;
					numSeenValues++;
					if (seenValues !== null) safePush(seenValues, value);
					yield value;
				}
			};
			const s = new Stream(g(this.arb, mrng.clone()));
			return safeObjectDefineProperties(s, {
				toString: { value: () => prettyPrint(numSeenValues, seenValues !== null ? seenValues.map(stringify) : void 0) },
				[toStringMethod]: { value: () => prettyPrint(numSeenValues, seenValues !== null ? seenValues.map(stringify) : void 0) },
				[asyncToStringMethod]: { value: async () => prettyPrint(numSeenValues, seenValues !== null ? await Promise.all(seenValues.map(asyncStringify)) : void 0) },
				[cloneMethod]: {
					value: enrichedProducer,
					enumerable: true
				}
			});
		};
		return new Value(enrichedProducer(), void 0);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	shrink(_value, _context) {
		return Stream.nil();
	}
};
//#endregion
//#region src/arbitrary/infiniteStream.ts
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
function infiniteStream(arb, constraints) {
	return new StreamArbitrary(arb, constraints !== void 0 && typeof constraints === "object" && "noHistory" in constraints ? !constraints.noHistory : true);
}
//#endregion
//#region src/arbitrary/_internals/mappers/CodePointsToString.ts
/** @internal - tab is supposed to be composed of valid code-points, not halved surrogate pairs */
function codePointsToStringMapper(tab) {
	return safeJoin(tab, "");
}
/** @internal */
function codePointsToStringUnmapper(value) {
	if (typeof value !== "string") throw new Error("Cannot unmap the passed value");
	return [...value];
}
//#endregion
//#region src/arbitrary/_internals/mappers/StringToBase64.ts
/** @internal - s is supposed to be composed of valid base64 values, not any '=' */
function stringToBase64Mapper(s) {
	switch (s.length % 4) {
		case 0: return s;
		case 3: return `${s}=`;
		case 2: return `${s}==`;
		default: return safeSubstring(s, 1);
	}
}
/** @internal */
function stringToBase64Unmapper(value) {
	if (typeof value !== "string" || value.length % 4 !== 0) throw new Error("Invalid string received");
	const lastTrailingIndex = value.indexOf("=");
	if (lastTrailingIndex === -1) return value;
	if (value.length - lastTrailingIndex > 2) throw new Error("Cannot unmap the passed value");
	return safeSubstring(value, 0, lastTrailingIndex);
}
//#endregion
//#region src/arbitrary/base64String.ts
const safeStringFromCharCode = String.fromCharCode;
/** @internal */
function base64Mapper(v) {
	if (v < 26) return safeStringFromCharCode(v + 65);
	if (v < 52) return safeStringFromCharCode(v + 97 - 26);
	if (v < 62) return safeStringFromCharCode(v + 48 - 52);
	return v === 62 ? "+" : "/";
}
/** @internal */
function base64Unmapper(s) {
	if (typeof s !== "string" || s.length !== 1) throw new SError("Invalid entry");
	const v = safeCharCodeAt(s, 0);
	if (v >= 65 && v <= 90) return v - 65;
	if (v >= 97 && v <= 122) return v - 97 + 26;
	if (v >= 48 && v <= 57) return v - 48 + 52;
	return v === 43 ? 62 : v === 47 ? 63 : -1;
}
/** @internal */
function base64() {
	return integer({
		min: 0,
		max: 63
	}).map(base64Mapper, base64Unmapper);
}
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
function base64String(constraints = {}) {
	const { minLength: unscaledMinLength = 0, maxLength: unscaledMaxLength = MaxLengthUpperBound, size } = constraints;
	const minLength = unscaledMinLength + 3 - (unscaledMinLength + 3) % 4;
	const maxLength = unscaledMaxLength - unscaledMaxLength % 4;
	const requestedSize = constraints.maxLength === void 0 && size === void 0 ? "=" : size;
	if (minLength > maxLength) throw new SError("Minimal length should be inferior or equal to maximal length");
	if (minLength % 4 !== 0) throw new SError("Minimal length of base64 strings must be a multiple of 4");
	if (maxLength % 4 !== 0) throw new SError("Maximal length of base64 strings must be a multiple of 4");
	const charArbitrary = base64();
	return array(charArbitrary, {
		minLength,
		maxLength,
		size: requestedSize,
		experimentalCustomSlices: createSlicesForStringLegacy(charArbitrary, codePointsToStringUnmapper)
	}).map(codePointsToStringMapper, codePointsToStringUnmapper).map(stringToBase64Mapper, stringToBase64Unmapper);
}
//#endregion
//#region src/arbitrary/_internals/helpers/IsSubarrayOf.ts
const safeObjectIs = Object.is;
function isSubarrayOf(source, small) {
	const countMap = new SMap$2();
	let countMinusZero = 0;
	for (const sourceEntry of source) if (safeObjectIs(sourceEntry, -0)) ++countMinusZero;
	else safeMapSet(countMap, sourceEntry, (safeMapGet(countMap, sourceEntry) || 0) + 1);
	for (let index = 0; index !== small.length; ++index) {
		if (!(index in small)) return false;
		const smallEntry = small[index];
		if (safeObjectIs(smallEntry, -0)) {
			if (countMinusZero === 0) return false;
			--countMinusZero;
		} else {
			const oldCount = safeMapGet(countMap, smallEntry) || 0;
			if (oldCount === 0) return false;
			safeMapSet(countMap, smallEntry, oldCount - 1);
		}
	}
	return true;
}
//#endregion
//#region src/arbitrary/_internals/SubarrayArbitrary.ts
const safeMathFloor$1 = Math.floor;
const safeMathLog = Math.log;
const safeArrayIsArray = Array.isArray;
/** @internal */
var SubarrayArbitrary = class extends Arbitrary {
	constructor(originalArray, isOrdered, minLength, maxLength) {
		super();
		this.originalArray = originalArray;
		this.isOrdered = isOrdered;
		this.minLength = minLength;
		this.maxLength = maxLength;
		if (minLength < 0 || minLength > originalArray.length) throw new Error("fc.*{s|S}ubarrayOf expects the minimal length to be between 0 and the size of the original array");
		if (maxLength < 0 || maxLength > originalArray.length) throw new Error("fc.*{s|S}ubarrayOf expects the maximal length to be between 0 and the size of the original array");
		if (minLength > maxLength) throw new Error("fc.*{s|S}ubarrayOf expects the minimal length to be inferior or equal to the maximal length");
		this.lengthArb = new IntegerArbitrary(minLength, maxLength);
		this.biasedLengthArb = minLength !== maxLength ? new IntegerArbitrary(minLength, minLength + safeMathFloor$1(safeMathLog(maxLength - minLength) / safeMathLog(2))) : this.lengthArb;
	}
	generate(mrng, biasFactor) {
		const size = (biasFactor !== void 0 && mrng.nextInt(1, biasFactor) === 1 ? this.biasedLengthArb : this.lengthArb).generate(mrng, void 0);
		const sizeValue = size.value;
		const remainingElements = safeMap(this.originalArray, (_v, idx) => idx);
		const ids = [];
		for (let index = 0; index !== sizeValue; ++index) {
			const selectedIdIndex = mrng.nextInt(0, remainingElements.length - 1);
			safePush(ids, remainingElements[selectedIdIndex]);
			safeSplice(remainingElements, selectedIdIndex, 1);
		}
		if (this.isOrdered) safeSort(ids, (a, b) => a - b);
		return new Value(safeMap(ids, (i) => this.originalArray[i]), size.context);
	}
	canShrinkWithoutContext(value) {
		if (!safeArrayIsArray(value)) return false;
		if (!this.lengthArb.canShrinkWithoutContext(value.length)) return false;
		return isSubarrayOf(this.originalArray, value);
	}
	shrink(value, context) {
		if (value.length === 0) return Stream.nil();
		return this.lengthArb.shrink(value.length, context).map((newSize) => {
			return new Value(safeSlice(value, value.length - newSize.value), newSize.context);
		}).join(value.length > this.minLength ? makeLazy(() => this.shrink(safeSlice(value, 1), void 0).filter((newValue) => this.minLength <= newValue.value.length + 1).map((newValue) => new Value([value[0], ...newValue.value], void 0))) : Stream.nil());
	}
};
//#endregion
//#region src/arbitrary/subarray.ts
/**
* For subarrays of `originalArray` (keeps ordering)
*
* @param originalArray - Original array
* @param constraints - Constraints to apply when building instances (since 2.4.0)
*
* @remarks Since 1.5.0
* @public
*/
function subarray(originalArray, constraints = {}) {
	const { minLength = 0, maxLength = originalArray.length } = constraints;
	return new SubarrayArbitrary(originalArray, true, minLength, maxLength);
}
//#endregion
//#region src/arbitrary/shuffledSubarray.ts
/**
* For subarrays of `originalArray`
*
* @param originalArray - Original array
* @param constraints - Constraints to apply when building instances (since 2.4.0)
*
* @remarks Since 1.5.0
* @public
*/
function shuffledSubarray(originalArray, constraints = {}) {
	const { minLength = 0, maxLength = originalArray.length } = constraints;
	return new SubarrayArbitrary(originalArray, false, minLength, maxLength);
}
//#endregion
//#region src/arbitrary/_internals/mappers/UintToBase32String.ts
/** @internal */
const encodeSymbolLookupTable = {
	10: "A",
	11: "B",
	12: "C",
	13: "D",
	14: "E",
	15: "F",
	16: "G",
	17: "H",
	18: "J",
	19: "K",
	20: "M",
	21: "N",
	22: "P",
	23: "Q",
	24: "R",
	25: "S",
	26: "T",
	27: "V",
	28: "W",
	29: "X",
	30: "Y",
	31: "Z"
};
/** @internal */
const decodeSymbolLookupTable = {
	"0": 0,
	"1": 1,
	"2": 2,
	"3": 3,
	"4": 4,
	"5": 5,
	"6": 6,
	"7": 7,
	"8": 8,
	"9": 9,
	A: 10,
	B: 11,
	C: 12,
	D: 13,
	E: 14,
	F: 15,
	G: 16,
	H: 17,
	J: 18,
	K: 19,
	M: 20,
	N: 21,
	P: 22,
	Q: 23,
	R: 24,
	S: 25,
	T: 26,
	V: 27,
	W: 28,
	X: 29,
	Y: 30,
	Z: 31
};
/** @internal */
function encodeSymbol(symbol) {
	return symbol < 10 ? SString(symbol) : encodeSymbolLookupTable[symbol];
}
/** @internal */
function pad(value, paddingLength) {
	let extraPadding = "";
	while (value.length + extraPadding.length < paddingLength) extraPadding += "0";
	return extraPadding + value;
}
/** @internal */
function smallUintToBase32StringMapper(num) {
	let base32Str = "";
	for (let remaining = num; remaining !== 0;) {
		const next = remaining >> 5;
		base32Str = encodeSymbol(remaining - (next << 5)) + base32Str;
		remaining = next;
	}
	return base32Str;
}
/** @internal */
function uintToBase32StringMapper(num, paddingLength) {
	const head = ~~(num / 1073741824);
	const tail = num & 1073741823;
	return pad(smallUintToBase32StringMapper(head), paddingLength - 6) + pad(smallUintToBase32StringMapper(tail), 6);
}
/** @internal */
function paddedUintToBase32StringMapper(paddingLength) {
	return function padded(num) {
		return uintToBase32StringMapper(num, paddingLength);
	};
}
/** @internal */
function uintToBase32StringUnmapper(value) {
	if (typeof value !== "string") throw new SError("Unsupported type");
	let accumulated = 0;
	let power = 1;
	for (let index = value.length - 1; index >= 0; --index) {
		const char = value[index];
		const numericForChar = decodeSymbolLookupTable[char];
		if (numericForChar === void 0) throw new SError("Unsupported type");
		accumulated += numericForChar * power;
		power *= 32;
	}
	return accumulated;
}
//#endregion
//#region src/arbitrary/ulid.ts
const padded10Mapper = paddedUintToBase32StringMapper(10);
const padded8Mapper = paddedUintToBase32StringMapper(8);
function ulidMapper(parts) {
	return padded10Mapper(parts[0]) + padded8Mapper(parts[1]) + padded8Mapper(parts[2]);
}
function ulidUnmapper(value) {
	if (typeof value !== "string" || value.length !== 26) throw new Error("Unsupported type");
	return [
		uintToBase32StringUnmapper(value.slice(0, 10)),
		uintToBase32StringUnmapper(value.slice(10, 18)),
		uintToBase32StringUnmapper(value.slice(18))
	];
}
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
function ulid() {
	return tuple(integer({
		min: 0,
		max: 0xffffffffffff
	}), integer({
		min: 0,
		max: 0xffffffffff
	}), integer({
		min: 0,
		max: 0xffffffffff
	})).map(ulidMapper, ulidUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/mappers/NumberToPaddedEight.ts
/** @internal */
function numberToPaddedEightMapper(n) {
	return safePadStart(safeNumberToString(n, 16), 8, "0");
}
/** @internal */
function numberToPaddedEightUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported type");
	if (value.length !== 8) throw new Error("Unsupported value: invalid length");
	const n = parseInt(value, 16);
	if (value !== numberToPaddedEightMapper(n)) throw new Error("Unsupported value: invalid content");
	return n;
}
//#endregion
//#region src/arbitrary/_internals/builders/PaddedNumberArbitraryBuilder.ts
/** @internal */
function buildPaddedNumberArbitrary(min, max) {
	return integer({
		min,
		max
	}).map(numberToPaddedEightMapper, numberToPaddedEightUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/mappers/PaddedEightsToUuid.ts
/** @internal */
function paddedEightsToUuidMapper(t) {
	return `${t[0]}-${safeSubstring(t[1], 4)}-${safeSubstring(t[1], 0, 4)}-${safeSubstring(t[2], 0, 4)}-${safeSubstring(t[2], 4)}${t[3]}`;
}
/** @internal */
const UuidRegex = /^([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/;
/** @internal */
function paddedEightsToUuidUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported type");
	const m = UuidRegex.exec(value);
	if (m === null) throw new Error("Unsupported type");
	return [
		m[1],
		m[3] + m[2],
		m[4] + safeSubstring(m[5], 0, 4),
		safeSubstring(m[5], 4)
	];
}
//#endregion
//#region src/arbitrary/_internals/mappers/VersionsApplierForUuid.ts
/** @internal */
const quickNumberToHexaString = "0123456789abcdef";
/** @internal */
function buildVersionsAppliersForUuid(versions) {
	const mapping = {};
	const reversedMapping = {};
	for (let index = 0; index !== versions.length; ++index) {
		const from = quickNumberToHexaString[index];
		const to = quickNumberToHexaString[versions[index]];
		mapping[from] = to;
		reversedMapping[to] = from;
	}
	function versionsApplierMapper(value) {
		return mapping[value[0]] + safeSubstring(value, 1);
	}
	function versionsApplierUnmapper(value) {
		if (typeof value !== "string") throw new SError("Cannot produce non-string values");
		const rev = reversedMapping[value[0]];
		if (rev === void 0) throw new SError("Cannot produce strings not starting by the version in hexa code");
		return rev + safeSubstring(value, 1);
	}
	return {
		versionsApplierMapper,
		versionsApplierUnmapper
	};
}
//#endregion
//#region src/arbitrary/uuid.ts
/** @internal */
function assertValidVersions(versions) {
	const found = {};
	for (const version of versions) {
		if (found[version]) throw new SError(`Version ${version} has been requested at least twice for uuid`);
		found[version] = true;
		if (version < 1 || version > 15) throw new SError(`Version must be a value in [1-15] for uuid, but received ${version}`);
		if (~~version !== version) throw new SError(`Version must be an integer value for uuid, but received ${version}`);
	}
	if (versions.length === 0) throw new SError(`Must provide at least one version for uuid`);
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
function uuid(constraints = {}) {
	const padded = buildPaddedNumberArbitrary(0, 4294967295);
	const version = constraints.version !== void 0 ? typeof constraints.version === "number" ? [constraints.version] : constraints.version : [
		1,
		2,
		3,
		4,
		5,
		6,
		7,
		8
	];
	assertValidVersions(version);
	const { versionsApplierMapper, versionsApplierUnmapper } = buildVersionsAppliersForUuid(version);
	return tuple(padded, buildPaddedNumberArbitrary(0, 268435456 * version.length - 1).map(versionsApplierMapper, versionsApplierUnmapper), buildPaddedNumberArbitrary(2147483648, 3221225471), padded).map(paddedEightsToUuidMapper, paddedEightsToUuidUnmapper);
}
//#endregion
//#region src/arbitrary/webAuthority.ts
/** @internal */
function hostUserInfo(size) {
	return string({
		unit: getOrCreateAlphaNumericPercentArbitrary("-._~!$&'()*+,;=:"),
		size
	});
}
/** @internal */
function userHostPortMapper([u, h, p]) {
	return (u === null ? "" : `${u}@`) + h + (p === null ? "" : `:${p}`);
}
/** @internal */
function userHostPortUnmapper(value) {
	if (typeof value !== "string") throw new Error("Unsupported");
	const atPosition = value.indexOf("@");
	const user = atPosition !== -1 ? value.substring(0, atPosition) : null;
	const m = /:(\d+)$/.exec(value);
	const port = m !== null ? Number(m[1]) : null;
	return [
		user,
		m !== null ? value.substring(atPosition + 1, value.length - m[1].length - 1) : value.substring(atPosition + 1),
		port
	];
}
/** @internal */
function bracketedMapper(s) {
	return `[${s}]`;
}
/** @internal */
function bracketedUnmapper(value) {
	if (typeof value !== "string" || value[0] !== "[" || value[value.length - 1] !== "]") throw new Error("Unsupported");
	return value.substring(1, value.length - 1);
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
function webAuthority(constraints) {
	const c = constraints || {};
	const size = c.size;
	const hostnameArbs = [
		domain({ size }),
		...c.withIPv4 === true ? [ipV4()] : [],
		...c.withIPv6 === true ? [ipV6().map(bracketedMapper, bracketedUnmapper)] : [],
		...c.withIPv4Extended === true ? [ipV4Extended()] : []
	];
	return tuple(c.withUserInfo === true ? option(hostUserInfo(size)) : constant(null), oneof(...hostnameArbs), c.withPort === true ? option(nat(65535)) : constant(null)).map(userHostPortMapper, userHostPortUnmapper);
}
//#endregion
//#region src/arbitrary/_internals/builders/UriQueryOrFragmentArbitraryBuilder.ts
/** @internal */
function buildUriQueryOrFragmentArbitrary(size) {
	return string({
		unit: getOrCreateAlphaNumericPercentArbitrary("-._~!$&'()*+,;=:@/?"),
		size
	});
}
//#endregion
//#region src/arbitrary/webFragments.ts
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
function webFragments(constraints = {}) {
	return buildUriQueryOrFragmentArbitrary(constraints.size);
}
//#endregion
//#region src/arbitrary/webSegment.ts
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
function webSegment(constraints = {}) {
	return string({
		unit: getOrCreateAlphaNumericPercentArbitrary("-._~!$&'()*+,;=:@"),
		size: constraints.size
	});
}
//#endregion
//#region src/arbitrary/_internals/mappers/SegmentsToPath.ts
/** @internal */
function segmentsToPathMapper(segments) {
	let path = "";
	for (let index = 0; index !== segments.length; ++index) path += "/" + segments[index];
	return path;
}
/** @internal */
function segmentsToPathUnmapper(value) {
	if (typeof value !== "string") throw new Error("Incompatible value received: type");
	if (value.length !== 0 && value[0] !== "/") throw new Error("Incompatible value received: start");
	return safeSplice(safeSplit(value, "/"), 1);
}
//#endregion
//#region src/arbitrary/_internals/builders/UriPathArbitraryBuilder.ts
/** @internal */
function sqrtSize(size) {
	switch (size) {
		case "xsmall": return ["xsmall", "xsmall"];
		case "small": return ["small", "xsmall"];
		case "medium": return ["small", "small"];
		case "large": return ["medium", "small"];
		case "xlarge": return ["medium", "medium"];
	}
}
/** @internal */
function buildUriPathArbitraryInternal(segmentSize, numSegmentSize) {
	return array(webSegment({ size: segmentSize }), { size: numSegmentSize }).map(segmentsToPathMapper, segmentsToPathUnmapper);
}
/** @internal */
function buildUriPathArbitrary(resolvedSize) {
	const [segmentSize, numSegmentSize] = sqrtSize(resolvedSize);
	if (segmentSize === numSegmentSize) return buildUriPathArbitraryInternal(segmentSize, numSegmentSize);
	return oneof(buildUriPathArbitraryInternal(segmentSize, numSegmentSize), buildUriPathArbitraryInternal(numSegmentSize, segmentSize));
}
//#endregion
//#region src/arbitrary/webPath.ts
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
function webPath(constraints) {
	return buildUriPathArbitrary(resolveSize((constraints || {}).size));
}
//#endregion
//#region src/arbitrary/webQueryParameters.ts
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
function webQueryParameters(constraints = {}) {
	return buildUriQueryOrFragmentArbitrary(constraints.size);
}
//#endregion
//#region src/arbitrary/_internals/mappers/PartsToUrl.ts
/** @internal */
function partsToUrlMapper(data) {
	const [scheme, authority, path] = data;
	return `${scheme}://${authority}${path}${data[3] === null ? "" : `?${data[3]}`}${data[4] === null ? "" : `#${data[4]}`}`;
}
/** @internal More details on RFC 3986, https://www.ietf.org/rfc/rfc3986.txt */
const UrlSplitRegex = /^([[A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)([^?#]*)(\?[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]*)?(#[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]*)?$/;
/** @internal */
function partsToUrlUnmapper(value) {
	if (typeof value !== "string") throw new Error("Incompatible value received: type");
	const m = UrlSplitRegex.exec(value);
	if (m === null) throw new Error("Incompatible value received");
	const scheme = m[1];
	const authority = m[2];
	const path = m[3];
	const query = m[4];
	const fragments = m[5];
	return [
		scheme,
		authority,
		path,
		query !== void 0 ? query.substring(1) : null,
		fragments !== void 0 ? fragments.substring(1) : null
	];
}
//#endregion
//#region src/arbitrary/webUrl.ts
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
function webUrl(constraints) {
	const c = constraints || {};
	const resolvedSize = resolveSize(c.size);
	const resolvedAuthoritySettingsSize = c.authoritySettings !== void 0 && c.authoritySettings.size !== void 0 ? relativeSizeToSize(c.authoritySettings.size, resolvedSize) : resolvedSize;
	const resolvedAuthoritySettings = {
		...c.authoritySettings,
		size: resolvedAuthoritySettingsSize
	};
	return tuple(constantFrom(...c.validSchemes || ["http", "https"]), webAuthority(resolvedAuthoritySettings), webPath({ size: resolvedSize }), c.withQueryParameters === true ? option(webQueryParameters({ size: resolvedSize })) : constant(null), c.withFragments === true ? option(webFragments({ size: resolvedSize })) : constant(null)).map(partsToUrlMapper, partsToUrlUnmapper);
}
//#endregion
//#region src/check/model/commands/CommandsIterable.ts
/**
* Iterable datastructure accepted as input for asyncModelRun and modelRun
*/
var CommandsIterable = class CommandsIterable {
	constructor(commands, metadataForReplay) {
		this.commands = commands;
		this.metadataForReplay = metadataForReplay;
		this[cloneMethod] = function() {
			return new CommandsIterable(this.commands.map((c) => c.clone()), this.metadataForReplay);
		};
	}
	[Symbol.iterator]() {
		return this.commands[Symbol.iterator]();
	}
	toString() {
		const serializedCommands = this.commands.filter((c) => c.hasRan).map((c) => c.toString()).join(",");
		const metadata = this.metadataForReplay();
		return metadata.length !== 0 ? `${serializedCommands} /*${metadata}*/` : serializedCommands;
	}
};
//#endregion
//#region src/check/model/commands/CommandWrapper.ts
/**
* Wrapper around commands used internally by fast-check to wrap existing commands
* in order to add them a flag to know whether or not they already have been executed
*/
var CommandWrapper = class CommandWrapper {
	constructor(cmd) {
		this.cmd = cmd;
		this.hasRan = false;
		if (hasToStringMethod(cmd)) {
			const method = cmd[toStringMethod];
			this[toStringMethod] = function toStringMethod() {
				return method.call(cmd);
			};
		}
		if (hasAsyncToStringMethod(cmd)) {
			const method = cmd[asyncToStringMethod];
			this[asyncToStringMethod] = function asyncToStringMethod() {
				return method.call(cmd);
			};
		}
	}
	check(m) {
		return this.cmd.check(m);
	}
	run(m, r) {
		this.hasRan = true;
		return this.cmd.run(m, r);
	}
	clone() {
		if (hasCloneMethod(this.cmd)) return new CommandWrapper(this.cmd[cloneMethod]());
		return new CommandWrapper(this.cmd);
	}
	toString() {
		return this.cmd.toString();
	}
};
//#endregion
//#region src/check/model/ReplayPath.ts
/** @internal */
var ReplayPath = class {
	/** Parse a serialized replayPath */
	static parse(replayPathStr) {
		const [serializedCount, serializedChanges] = replayPathStr.split(":");
		const counts = this.parseCounts(serializedCount);
		const changes = this.parseChanges(serializedChanges);
		return this.parseOccurences(counts, changes);
	}
	/** Stringify a replayPath */
	static stringify(replayPath) {
		const occurences = this.countOccurences(replayPath);
		return `${this.stringifyCounts(occurences)}:${this.stringifyChanges(occurences)}`;
	}
	/** Number to Base64 value */
	static intToB64(n) {
		if (n < 26) return String.fromCharCode(n + 65);
		if (n < 52) return String.fromCharCode(n + 97 - 26);
		if (n < 62) return String.fromCharCode(n + 48 - 52);
		return String.fromCharCode(n === 62 ? 43 : 47);
	}
	/** Base64 value to number */
	static b64ToInt(c) {
		if (c >= "a") return c.charCodeAt(0) - 97 + 26;
		if (c >= "A") return c.charCodeAt(0) - 65;
		if (c >= "0") return c.charCodeAt(0) - 48 + 52;
		return c === "+" ? 62 : 63;
	}
	/**
	* Divide an incoming replayPath into an array of {value, count}
	* with count is the number of consecutive occurences of value (with a max set to 64)
	*
	* Above 64, another {value, count} is created
	*/
	static countOccurences(replayPath) {
		return replayPath.reduce((counts, cur) => {
			if (counts.length === 0 || counts[counts.length - 1].count === 64 || counts[counts.length - 1].value !== cur) counts.push({
				value: cur,
				count: 1
			});
			else counts[counts.length - 1].count += 1;
			return counts;
		}, []);
	}
	/**
	* Serialize an array of {value, count} back to its replayPath
	*/
	static parseOccurences(counts, changes) {
		const replayPath = [];
		for (let idx = 0; idx !== counts.length; ++idx) {
			const count = counts[idx];
			const value = changes[idx];
			for (let num = 0; num !== count; ++num) replayPath.push(value);
		}
		return replayPath;
	}
	/**
	* Stringify the switch from true to false of occurences
	*
	* {value: 0}, {value: 1}, {value: 1}, {value: 0}
	* will be stringified as: 6 = (1 * 0) + (2 * 1) + (4 * 1) + (8 * 0)
	*
	* {value: 0}, {value: 1}, {value: 1}, {value: 0}, {value: 1}, {value: 0}, {value: 1}, {value: 0}
	* will be stringified as: 22, 1 [only 6 values encoded in one number]
	*/
	static stringifyChanges(occurences) {
		let serializedChanges = "";
		for (let idx = 0; idx < occurences.length; idx += 6) {
			const changesInt = occurences.slice(idx, idx + 6).reduceRight((prev, cur) => (prev << 1) + (cur.value ? 1 : 0), 0);
			serializedChanges += this.intToB64(changesInt);
		}
		return serializedChanges;
	}
	/**
	* Parse switch of value
	*/
	static parseChanges(serializedChanges) {
		const changesInt = serializedChanges.split("").map((c) => this.b64ToInt(c));
		const changes = [];
		for (let idx = 0; idx !== changesInt.length; ++idx) {
			let current = changesInt[idx];
			for (let n = 0; n !== 6; ++n, current >>= 1) changes.push(current % 2 === 1);
		}
		return changes;
	}
	/**
	* Stringify counts of occurences
	*/
	static stringifyCounts(occurences) {
		return occurences.map(({ count }) => this.intToB64(count - 1)).join("");
	}
	/**
	* Parse counts
	*/
	static parseCounts(serializedCount) {
		return serializedCount.split("").map((c) => this.b64ToInt(c) + 1);
	}
};
//#endregion
//#region src/arbitrary/_internals/CommandsArbitrary.ts
/** @internal */
var CommandsArbitrary = class extends Arbitrary {
	constructor(commandArbs, maxGeneratedCommands, maxCommands, sourceReplayPath, disableReplayLog) {
		super();
		this.sourceReplayPath = sourceReplayPath;
		this.disableReplayLog = disableReplayLog;
		this.oneCommandArb = oneof(...commandArbs).map((c) => new CommandWrapper(c));
		this.lengthArb = restrictedIntegerArbitraryBuilder(0, maxGeneratedCommands, maxCommands);
		this.replayPath = [];
		this.replayPathPosition = 0;
	}
	metadataForReplay() {
		return this.disableReplayLog ? "" : `replayPath=${JSON.stringify(ReplayPath.stringify(this.replayPath))}`;
	}
	buildValueFor(items, shrunkOnce) {
		const commands = items.map((item) => item.value_);
		const context = {
			shrunkOnce,
			items
		};
		return new Value(new CommandsIterable(commands, () => this.metadataForReplay()), context);
	}
	generate(mrng) {
		const sizeValue = this.lengthArb.generate(mrng, void 0).value;
		const items = Array(sizeValue);
		for (let idx = 0; idx !== sizeValue; ++idx) {
			const item = this.oneCommandArb.generate(mrng, void 0);
			items[idx] = item;
		}
		this.replayPathPosition = 0;
		return this.buildValueFor(items, false);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	/** Filter commands based on the real status of the execution */
	filterOnExecution(itemsRaw) {
		const items = [];
		for (const c of itemsRaw) if (c.value_.hasRan) {
			this.replayPath.push(true);
			items.push(c);
		} else this.replayPath.push(false);
		return items;
	}
	/** Filter commands based on the internal replay state */
	filterOnReplay(itemsRaw) {
		return itemsRaw.filter((c, idx) => {
			const state = this.replayPath[this.replayPathPosition + idx];
			if (state === void 0) throw new Error(`Too short replayPath`);
			if (!state && c.value_.hasRan) throw new Error(`Mismatch between replayPath and real execution`);
			return state;
		});
	}
	/** Filter commands for shrinking purposes */
	filterForShrinkImpl(itemsRaw) {
		if (this.replayPathPosition === 0) this.replayPath = this.sourceReplayPath !== null ? ReplayPath.parse(this.sourceReplayPath) : [];
		const items = this.replayPathPosition < this.replayPath.length ? this.filterOnReplay(itemsRaw) : this.filterOnExecution(itemsRaw);
		this.replayPathPosition += itemsRaw.length;
		return items;
	}
	shrink(_value, context) {
		if (context === void 0) return Stream.nil();
		const safeContext = context;
		const shrunkOnce = safeContext.shrunkOnce;
		const itemsRaw = safeContext.items;
		const items = this.filterForShrinkImpl(itemsRaw);
		if (items.length === 0) return Stream.nil();
		const rootShrink = shrunkOnce ? Stream.nil() : new Stream([[]][Symbol.iterator]());
		const nextShrinks = [];
		for (let numToKeep = 0; numToKeep !== items.length; ++numToKeep) nextShrinks.push(makeLazy(() => {
			const fixedStart = items.slice(0, numToKeep);
			return this.lengthArb.shrink(items.length - 1 - numToKeep, void 0).map((l) => fixedStart.concat(items.slice(items.length - (l.value + 1))));
		}));
		for (let itemAt = 0; itemAt !== items.length; ++itemAt) nextShrinks.push(makeLazy(() => this.oneCommandArb.shrink(items[itemAt].value_, items[itemAt].context).map((v) => items.slice(0, itemAt).concat([v], items.slice(itemAt + 1)))));
		return rootShrink.join(...nextShrinks).map((shrinkables) => {
			return this.buildValueFor(shrinkables.map((c) => new Value(c.value_.clone(), c.context)), true);
		});
	}
};
//#endregion
//#region src/arbitrary/commands.ts
function commands(commandArbs, constraints = {}) {
	const { size, maxCommands = MaxLengthUpperBound, disableReplayLog = false, replayPath = null } = constraints;
	return new CommandsArbitrary(commandArbs, maxGeneratedLengthFromSizeForArbitrary(size, 0, maxCommands, constraints.maxCommands !== void 0), maxCommands, replayPath, disableReplayLog);
}
//#endregion
//#region src/check/model/commands/ScheduledCommand.ts
/** @internal */
var ScheduledCommand = class {
	constructor(s, cmd) {
		this.s = s;
		this.cmd = cmd;
	}
	async check(m) {
		let error = null;
		let checkPassed = false;
		if ((await this.s.scheduleSequence([{
			label: `check@${this.cmd.toString()}`,
			builder: async () => {
				try {
					checkPassed = await Promise.resolve(this.cmd.check(m));
				} catch (err) {
					error = err;
					throw err;
				}
			}
		}]).task).faulty) throw error;
		return checkPassed;
	}
	async run(m, r) {
		let error = null;
		if ((await this.s.scheduleSequence([{
			label: `run@${this.cmd.toString()}`,
			builder: async () => {
				try {
					await this.cmd.run(m, r);
				} catch (err) {
					error = err;
					throw err;
				}
			}
		}]).task).faulty) throw error;
	}
};
/** @internal */
const scheduleCommands = function* (s, cmds) {
	for (const cmd of cmds) yield new ScheduledCommand(s, cmd);
};
//#endregion
//#region src/check/model/ModelRunner.ts
/** @internal */
const genericModelRun = (s, cmds, initialValue, runCmd, then) => {
	return s.then((o) => {
		const { model, real } = o;
		let state = initialValue;
		for (const c of cmds) state = then(state, () => {
			return runCmd(c, model, real);
		});
		return state;
	});
};
/** @internal */
const internalModelRun = (s, cmds) => {
	const then = (_p, c) => c();
	const setupProducer = { then: (fun) => {
		fun(s());
	} };
	const runSync = (cmd, m, r) => {
		if (cmd.check(m)) cmd.run(m, r);
	};
	return genericModelRun(setupProducer, cmds, void 0, runSync, then);
};
/** @internal */
const isAsyncSetup = (s) => {
	return typeof s.then === "function";
};
/** @internal */
const internalAsyncModelRun = async (s, cmds, defaultPromise = Promise.resolve()) => {
	const then = (p, c) => p.then(c);
	const setupProducer = { then: (fun) => {
		const out = s();
		if (isAsyncSetup(out)) return out.then(fun);
		else return fun(out);
	} };
	const runAsync = async (cmd, m, r) => {
		if (await cmd.check(m)) await cmd.run(m, r);
	};
	return await genericModelRun(setupProducer, cmds, defaultPromise, runAsync, then);
};
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
function modelRun(s, cmds) {
	internalModelRun(s, cmds);
}
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
async function asyncModelRun(s, cmds) {
	await internalAsyncModelRun(s, cmds);
}
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
async function scheduledModelRun(scheduler, s, cmds) {
	const scheduledCommands = scheduleCommands(scheduler, cmds);
	const out = internalAsyncModelRun(s, scheduledCommands, scheduler.schedule(Promise.resolve(), "startModel"));
	await scheduler.waitFor(out);
	await scheduler.waitAll();
}
//#endregion
//#region src/arbitrary/_internals/implementations/SchedulerImplem.ts
const defaultSchedulerAct = (f) => f();
/** @internal */
var SchedulerImplem = class SchedulerImplem {
	constructor(act, taskSelector) {
		this.act = act;
		this.taskSelector = taskSelector;
		this.lastTaskId = 0;
		this.sourceTaskSelector = taskSelector.clone();
		this.scheduledTasks = [];
		this.triggeredTasks = [];
		this.scheduledWatchers = [];
		this[cloneMethod] = function() {
			return new SchedulerImplem(this.act, this.sourceTaskSelector);
		};
	}
	static buildLog(reportItem) {
		return `[task\${${reportItem.taskId}}] ${reportItem.label.length !== 0 ? `${reportItem.schedulingType}::${reportItem.label}` : reportItem.schedulingType} ${reportItem.status}${reportItem.outputValue !== void 0 ? ` with value ${escapeForTemplateString(reportItem.outputValue)}` : ""}`;
	}
	log(schedulingType, taskId, label, metadata, status, data) {
		this.triggeredTasks.push({
			status,
			schedulingType,
			taskId,
			label,
			metadata,
			outputValue: data !== void 0 ? stringify(data) : void 0
		});
	}
	scheduleInternal(schedulingType, label, task, metadata, customAct, thenTaskToBeAwaited) {
		const taskId = ++this.lastTaskId;
		let trigger = void 0;
		const scheduledPromise = new Promise((resolve, reject) => {
			trigger = () => {
				const promise = Promise.resolve(thenTaskToBeAwaited !== void 0 ? task.then(() => thenTaskToBeAwaited()) : task);
				promise.then((data) => {
					this.log(schedulingType, taskId, label, metadata, "resolved", data);
					resolve(data);
				}, (err) => {
					this.log(schedulingType, taskId, label, metadata, "rejected", err);
					reject(err);
				});
				return promise;
			};
		});
		this.scheduledTasks.push({
			original: task,
			trigger,
			schedulingType,
			taskId,
			label,
			metadata,
			customAct
		});
		if (this.scheduledWatchers.length !== 0) this.scheduledWatchers[0]();
		return scheduledPromise;
	}
	schedule(task, label, metadata, customAct) {
		return this.scheduleInternal("promise", label || "", task, metadata, customAct || defaultSchedulerAct);
	}
	scheduleFunction(asyncFunction, customAct) {
		return (...args) => this.scheduleInternal("function", `${asyncFunction.name}(${args.map(stringify).join(",")})`, asyncFunction(...args), void 0, customAct || defaultSchedulerAct);
	}
	scheduleSequence(sequenceBuilders, customAct) {
		const status = {
			done: false,
			faulty: false
		};
		const dummyResolvedPromise = { then: (f) => f() };
		let resolveSequenceTask = () => {};
		const sequenceTask = new Promise((resolve) => {
			resolveSequenceTask = () => resolve({
				done: status.done,
				faulty: status.faulty
			});
		});
		const onFaultyItemNoThrow = () => {
			status.faulty = true;
			resolveSequenceTask();
		};
		const onDone = () => {
			status.done = true;
			resolveSequenceTask();
		};
		const registerNextBuilder = (index, previous) => {
			if (index >= sequenceBuilders.length) {
				previous.then(onDone, onFaultyItemNoThrow);
				return;
			}
			previous.then(() => {
				const item = sequenceBuilders[index];
				const [builder, label, metadata] = typeof item === "function" ? [
					item,
					item.name,
					void 0
				] : [
					item.builder,
					item.label,
					item.metadata
				];
				const scheduled = this.scheduleInternal("sequence", label, dummyResolvedPromise, metadata, customAct || defaultSchedulerAct, () => builder());
				registerNextBuilder(index + 1, scheduled);
			}, onFaultyItemNoThrow);
		};
		registerNextBuilder(0, dummyResolvedPromise);
		return Object.assign(status, { task: sequenceTask });
	}
	count() {
		return this.scheduledTasks.length;
	}
	internalWaitOne() {
		if (this.scheduledTasks.length === 0) throw new Error("No task scheduled");
		const taskIndex = this.taskSelector.nextTaskIndex(this.scheduledTasks);
		const [scheduledTask] = this.scheduledTasks.splice(taskIndex, 1);
		return scheduledTask.customAct(() => {
			return scheduledTask.trigger().catch((_err) => {});
		});
	}
	waitOne(customAct) {
		const waitAct = customAct || defaultSchedulerAct;
		return this.act(() => waitAct(() => this.internalWaitOne()));
	}
	async waitAll(customAct) {
		while (this.scheduledTasks.length > 0) await this.waitOne(customAct);
	}
	async internalWaitFor(unscheduledTask, options) {
		let taskResolved = false;
		const customAct = options.customAct;
		const onWaitStart = options.onWaitStart;
		const onWaitIdle = options.onWaitIdle;
		const launchAwaiterOnInit = options.launchAwaiterOnInit;
		let resolveFinal = void 0;
		let rejectFinal = void 0;
		let awaiterTicks = 0;
		let awaiterPromise = null;
		let awaiterScheduledTaskPromise = null;
		const awaiter = async () => {
			awaiterTicks = 50;
			for (awaiterTicks = 50; !taskResolved && awaiterTicks > 0; --awaiterTicks) await Promise.resolve();
			if (!taskResolved && this.scheduledTasks.length > 0) {
				if (onWaitStart !== void 0) onWaitStart();
				awaiterScheduledTaskPromise = this.waitOne(customAct);
				return awaiterScheduledTaskPromise.then(() => {
					awaiterScheduledTaskPromise = null;
					return awaiter();
				}, (err) => {
					awaiterScheduledTaskPromise = null;
					taskResolved = true;
					rejectFinal(err);
					throw err;
				});
			}
			if (!taskResolved && onWaitIdle !== void 0) onWaitIdle();
			awaiterPromise = null;
		};
		const handleNotified = () => {
			if (awaiterPromise !== null) {
				awaiterTicks = 51;
				return;
			}
			awaiterPromise = awaiter().catch(() => {});
		};
		const clearAndReplaceWatcher = () => {
			const handleNotifiedIndex = this.scheduledWatchers.indexOf(handleNotified);
			if (handleNotifiedIndex !== -1) this.scheduledWatchers.splice(handleNotifiedIndex, 1);
			if (handleNotifiedIndex === 0 && this.scheduledWatchers.length !== 0) this.scheduledWatchers[0]();
		};
		const finalTask = new Promise((resolve, reject) => {
			resolveFinal = (value) => {
				clearAndReplaceWatcher();
				resolve(value);
			};
			rejectFinal = (error) => {
				clearAndReplaceWatcher();
				reject(error);
			};
		});
		unscheduledTask.then((ret) => {
			taskResolved = true;
			if (awaiterScheduledTaskPromise === null) resolveFinal(ret);
			else awaiterScheduledTaskPromise.then(() => resolveFinal(ret), (error) => rejectFinal(error));
		}, (err) => {
			taskResolved = true;
			if (awaiterScheduledTaskPromise === null) rejectFinal(err);
			else awaiterScheduledTaskPromise.then(() => rejectFinal(err), () => rejectFinal(err));
		});
		if ((this.scheduledTasks.length > 0 || launchAwaiterOnInit) && this.scheduledWatchers.length === 0) handleNotified();
		this.scheduledWatchers.push(handleNotified);
		return finalTask;
	}
	waitNext(count, customAct) {
		let resolver = void 0;
		let remaining = count;
		const awaited = remaining <= 0 ? Promise.resolve() : new Promise((r) => {
			resolver = () => {
				if (--remaining <= 0) r();
			};
		});
		return this.internalWaitFor(awaited, {
			customAct,
			onWaitStart: resolver,
			onWaitIdle: void 0,
			launchAwaiterOnInit: false
		});
	}
	waitIdle(customAct) {
		let resolver = void 0;
		const awaited = new Promise((r) => resolver = r);
		return this.internalWaitFor(awaited, {
			customAct,
			onWaitStart: void 0,
			onWaitIdle: resolver,
			launchAwaiterOnInit: true
		});
	}
	waitFor(unscheduledTask, customAct) {
		return this.internalWaitFor(unscheduledTask, {
			customAct,
			onWaitStart: void 0,
			onWaitIdle: void 0,
			launchAwaiterOnInit: false
		});
	}
	report() {
		return [...this.triggeredTasks, ...this.scheduledTasks.map((t) => ({
			status: "pending",
			schedulingType: t.schedulingType,
			taskId: t.taskId,
			label: t.label,
			metadata: t.metadata
		}))];
	}
	toString() {
		return "schedulerFor()`\n" + this.report().map(SchedulerImplem.buildLog).map((log) => `-> ${log}`).join("\n") + "`";
	}
};
//#endregion
//#region src/arbitrary/_internals/helpers/BuildSchedulerFor.ts
/** @internal */
function buildNextTaskIndex$1(ordering) {
	let numTasks = 0;
	return {
		clone: () => buildNextTaskIndex$1(ordering),
		nextTaskIndex: (scheduledTasks) => {
			if (ordering.length <= numTasks) throw new Error(`Invalid schedulerFor defined: too many tasks have been scheduled`);
			const taskIndex = scheduledTasks.findIndex((t) => t.taskId === ordering[numTasks]);
			if (taskIndex === -1) throw new Error(`Invalid schedulerFor defined: unable to find next task`);
			++numTasks;
			return taskIndex;
		}
	};
}
/** @internal */
function buildSchedulerFor(act, ordering) {
	return new SchedulerImplem(act, buildNextTaskIndex$1(ordering));
}
//#endregion
//#region src/arbitrary/_internals/SchedulerArbitrary.ts
/**
* @internal
* Passed instance of mrng should never be altered from the outside.
* Passed instance will never be affected by current code but always cloned before usage.
*/
function buildNextTaskIndex(mrng) {
	const clonedMrng = mrng.clone();
	return {
		clone: () => buildNextTaskIndex(clonedMrng),
		nextTaskIndex: (scheduledTasks) => {
			return mrng.nextInt(0, scheduledTasks.length - 1);
		}
	};
}
/** @internal */
var SchedulerArbitrary = class extends Arbitrary {
	constructor(act) {
		super();
		this.act = act;
	}
	generate(mrng, _biasFactor) {
		return new Value(new SchedulerImplem(this.act, buildNextTaskIndex(mrng.clone())), void 0);
	}
	canShrinkWithoutContext(_value) {
		return false;
	}
	shrink(_value, _context) {
		return Stream.nil();
	}
};
//#endregion
//#region src/arbitrary/scheduler.ts
/**
* For scheduler of promises
* @remarks Since 1.20.0
* @public
*/
function scheduler(constraints) {
	const { act = (f) => f() } = constraints || {};
	return new SchedulerArbitrary(act);
}
function schedulerFor(customOrderingOrConstraints, constraintsOrUndefined) {
	const { act = (f) => f() } = Array.isArray(customOrderingOrConstraints) ? constraintsOrUndefined || {} : customOrderingOrConstraints || {};
	if (Array.isArray(customOrderingOrConstraints)) return buildSchedulerFor(act, customOrderingOrConstraints);
	return function(_strs, ...ordering) {
		return buildSchedulerFor(act, ordering);
	};
}
//#endregion
//#region src/arbitrary/bigInt64Array.ts
/**
* For BigInt64Array
* @remarks Since 3.0.0
* @public
*/
function bigInt64Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, SBigInt("-9223372036854775808"), SBigInt("9223372036854775807"), SBigInt64Array, bigInt);
}
//#endregion
//#region src/arbitrary/bigUint64Array.ts
/**
* For BigUint64Array
* @remarks Since 3.0.0
* @public
*/
function bigUint64Array(constraints = {}) {
	return typedIntArrayArbitraryArbitraryBuilder(constraints, SBigInt(0), SBigInt("18446744073709551615"), SBigUint64Array, bigInt);
}
//#endregion
//#region src/utils/noSuchValue.ts
/**
* Typeguard to ensure a value is never there
* @param value The value that should not exist
* @param returnedValue The value to be returned
*/
function noSuchValue(_value, returnedValue) {
	return returnedValue;
}
//#endregion
//#region src/arbitrary/_internals/helpers/ClampRegexAst.ts
const safeMathFloor = Math.floor;
const safeMathMin = Math.min;
/** @internal */
function clampRegexAstInternal(astNode, maxLength) {
	switch (astNode.type) {
		case "Char": return {
			astNode,
			minLength: 1
		};
		case "Repetition": switch (astNode.quantifier.kind) {
			case "*": {
				const clamped = clampRegexAstInternal(astNode.expression, maxLength);
				return {
					astNode: {
						type: "Repetition",
						quantifier: {
							...astNode.quantifier,
							kind: "Range",
							from: 0,
							to: maxLength
						},
						expression: clamped.astNode
					},
					minLength: 0
				};
			}
			case "+": {
				const clamped = clampRegexAstInternal(astNode.expression, maxLength);
				const scaledClampedMinLength = clamped.minLength > 1 ? clamped.minLength : 1;
				return {
					astNode: {
						type: "Repetition",
						quantifier: {
							...astNode.quantifier,
							kind: "Range",
							from: 1,
							to: safeMathFloor(maxLength / scaledClampedMinLength)
						},
						expression: clamped.astNode
					},
					minLength: clamped.minLength
				};
			}
			case "?": {
				const clamped = clampRegexAstInternal(astNode.expression, maxLength);
				if (maxLength < clamped.minLength) return {
					astNode: {
						type: "Repetition",
						quantifier: {
							...astNode.quantifier,
							kind: "Range",
							from: 0,
							to: 0
						},
						expression: clamped.astNode
					},
					minLength: 0
				};
				return {
					astNode: {
						...astNode,
						expression: clamped.astNode
					},
					minLength: 0
				};
			}
			case "Range": {
				const scaledMaxLength = astNode.quantifier.from > 1 ? safeMathFloor(maxLength / astNode.quantifier.from) : maxLength;
				const clamped = clampRegexAstInternal(astNode.expression, scaledMaxLength);
				const scaledClampedMinLength = clamped.minLength > 1 ? clamped.minLength : 1;
				if (astNode.quantifier.to === void 0 || astNode.quantifier.to * scaledClampedMinLength > maxLength) return {
					astNode: {
						type: "Repetition",
						quantifier: {
							...astNode.quantifier,
							kind: "Range",
							to: safeMathFloor(maxLength / scaledClampedMinLength)
						},
						expression: clamped.astNode
					},
					minLength: astNode.quantifier.from * clamped.minLength
				};
				return {
					astNode: {
						...astNode,
						expression: clamped.astNode
					},
					minLength: astNode.quantifier.from * clamped.minLength
				};
			}
			default: return noSuchValue(astNode.quantifier, {
				astNode,
				minLength: 0
			});
		}
		case "Quantifier": return {
			astNode,
			minLength: 0
		};
		case "Alternative": {
			let totalMinLength = 0;
			const extendedClampeds = [];
			for (let index = 0; index !== astNode.expressions.length; ++index) {
				const temporaryAllowance = maxLength - totalMinLength;
				const clamped = clampRegexAstInternal(astNode.expressions[index], temporaryAllowance);
				totalMinLength += clamped.minLength;
				safePush(extendedClampeds, {
					value: clamped,
					allowance: temporaryAllowance
				});
			}
			const refinedExpressions = [];
			for (let index = 0; index !== extendedClampeds.length; ++index) {
				const current = extendedClampeds[index].value;
				const pastAllowance = extendedClampeds[index].allowance;
				const allowance = maxLength - totalMinLength + current.minLength;
				safePush(refinedExpressions, (allowance !== pastAllowance ? clampRegexAstInternal(current.astNode, allowance) : current).astNode);
			}
			return {
				astNode: {
					...astNode,
					expressions: refinedExpressions
				},
				minLength: totalMinLength
			};
		}
		case "CharacterClass": return {
			astNode,
			minLength: 1
		};
		case "ClassRange": return {
			astNode,
			minLength: 1
		};
		case "Group": {
			const clamped = clampRegexAstInternal(astNode.expression, maxLength);
			return {
				astNode: {
					...astNode,
					expression: clamped.astNode
				},
				minLength: clamped.minLength
			};
		}
		case "Disjunction": {
			if (astNode.left === null) {
				if (astNode.right === null) return {
					astNode,
					minLength: 0
				};
				const clampedRight = clampRegexAstInternal(astNode.right, maxLength);
				const refinedRight = clampedRight.minLength > maxLength ? null : clampedRight.astNode;
				return {
					astNode: {
						...astNode,
						left: null,
						right: refinedRight
					},
					minLength: 0
				};
			}
			if (astNode.right === null) {
				const clampLeft = clampRegexAstInternal(astNode.left, maxLength);
				const refinedLeft = clampLeft.minLength > maxLength ? null : clampLeft.astNode;
				return {
					astNode: {
						...astNode,
						left: refinedLeft,
						right: null
					},
					minLength: 0
				};
			}
			const clampedLeft = clampRegexAstInternal(astNode.left, maxLength);
			const clampedRight = clampRegexAstInternal(astNode.right, maxLength);
			if (clampedLeft.minLength > maxLength) return clampedRight;
			if (clampedRight.minLength > maxLength) return clampedLeft;
			return {
				astNode: {
					...astNode,
					left: clampedLeft.astNode,
					right: clampedRight.astNode
				},
				minLength: safeMathMin(clampedLeft.minLength, clampedRight.minLength)
			};
		}
		case "Assertion": return {
			astNode,
			minLength: 0
		};
		case "Backreference": return {
			astNode,
			minLength: 0
		};
		case "UnicodeProperty": return {
			astNode,
			minLength: 1
		};
	}
}
/**
* Adapt an AST Node to fit within a maxLength constraint
* @param astNode - The AST to be adapted
* @param maxLength - The max authorized length
*/
function clampRegexAst(astNode, maxLength) {
	return clampRegexAstInternal(astNode, maxLength).astNode;
}
//#endregion
//#region src/arbitrary/_internals/helpers/SanitizeRegexAst.ts
function raiseUnsupportedASTNode$1(astNode) {
	return /* @__PURE__ */ new Error(`Unsupported AST node! Received: ${stringify(astNode)}`);
}
function addMissingDotStarTraversalAddMissing(astNode, isFirst, isLast) {
	if (!isFirst && !isLast) return astNode;
	const traversalResults = {
		hasStart: false,
		hasEnd: false
	};
	const revampedNode = addMissingDotStarTraversal(astNode, isFirst, isLast, traversalResults);
	const missingStart = isFirst && !traversalResults.hasStart;
	const missingEnd = isLast && !traversalResults.hasEnd;
	if (!missingStart && !missingEnd) return revampedNode;
	const expressions = [];
	if (missingStart) {
		expressions.push({
			type: "Assertion",
			kind: "^"
		});
		expressions.push({
			type: "Repetition",
			quantifier: {
				type: "Quantifier",
				kind: "*",
				greedy: true
			},
			expression: {
				type: "Char",
				kind: "meta",
				symbol: ".",
				value: ".",
				codePoint: NaN
			}
		});
	}
	expressions.push(revampedNode);
	if (missingEnd) {
		expressions.push({
			type: "Repetition",
			quantifier: {
				type: "Quantifier",
				kind: "*",
				greedy: true
			},
			expression: {
				type: "Char",
				kind: "meta",
				symbol: ".",
				value: ".",
				codePoint: NaN
			}
		});
		expressions.push({
			type: "Assertion",
			kind: "$"
		});
	}
	return {
		type: "Group",
		capturing: false,
		expression: {
			type: "Alternative",
			expressions
		}
	};
}
function addMissingDotStarTraversal(astNode, isFirst, isLast, traversalResults) {
	switch (astNode.type) {
		case "Char": return astNode;
		case "Repetition": return astNode;
		case "Quantifier": throw new Error(`Wrongly defined AST tree, Quantifier nodes not supposed to be scanned!`);
		case "Alternative":
			traversalResults.hasStart = true;
			traversalResults.hasEnd = true;
			return {
				...astNode,
				expressions: astNode.expressions.map((node, index) => addMissingDotStarTraversalAddMissing(node, isFirst && index === 0, isLast && index === astNode.expressions.length - 1))
			};
		case "CharacterClass": return astNode;
		case "ClassRange": return astNode;
		case "Group": return {
			...astNode,
			expression: addMissingDotStarTraversal(astNode.expression, isFirst, isLast, traversalResults)
		};
		case "Disjunction":
			traversalResults.hasStart = true;
			traversalResults.hasEnd = true;
			return {
				...astNode,
				left: astNode.left !== null ? addMissingDotStarTraversalAddMissing(astNode.left, isFirst, isLast) : null,
				right: astNode.right !== null ? addMissingDotStarTraversalAddMissing(astNode.right, isFirst, isLast) : null
			};
		case "Assertion": if (astNode.kind === "^" || astNode.kind === "Lookahead") {
			traversalResults.hasStart = true;
			return astNode;
		} else if (astNode.kind === "$" || astNode.kind === "Lookbehind") {
			traversalResults.hasEnd = true;
			return astNode;
		} else throw new Error(`Assertions of kind ${astNode.kind} not implemented yet!`);
		case "Backreference": return astNode;
		case "UnicodeProperty": return astNode;
		default: throw raiseUnsupportedASTNode$1(astNode);
	}
}
/**
* Revamp a regex token tree into one featuring missing ^ and $ assertions.
*
* WARNING: The produced tree may not define the same groups.
* Refer to the unit tests for more details on this limitation.
*
* @internal
*/
function addMissingDotStar(astNode) {
	return addMissingDotStarTraversalAddMissing(astNode, true, true);
}
//#endregion
//#region src/arbitrary/_internals/helpers/ReadRegex.ts
/**
* Internal helper used to compute the size in bytes of one character
*/
function charSizeAt(text, pos) {
	return text[pos] >= "\ud800" && text[pos] <= "\udbff" && text[pos + 1] >= "\udc00" && text[pos + 1] <= "\udfff" ? 2 : 1;
}
/**
* Internal helper checking if a character is an hexadecimal one, ie: a-fA-F0-9
*/
function isHexaDigit(char) {
	return char >= "0" && char <= "9" || char >= "a" && char <= "f" || char >= "A" && char <= "F";
}
/**
* Internal helper checking if a character is a decimal one, ie: 0-9
*/
function isDigit$1(char) {
	return char >= "0" && char <= "9";
}
/**
* Find the index of the last character of a squared-bracket "[]" block.
* The returned index corresponds to the one of the ] closing the block.
*/
function squaredBracketBlockContentEndFrom(text, from) {
	for (let index = from; index !== text.length; ++index) {
		const char = text[index];
		if (char === "\\") index += 1;
		else if (char === "]") return index;
	}
	throw new Error(`Missing closing ']'`);
}
/**
* Find the index of the last character of a parenthesis "()" block.
* The returned index corresponds to the one of the ) closing the block.
*/
function parenthesisBlockContentEndFrom(text, from) {
	let numExtraOpened = 0;
	for (let index = from; index !== text.length; ++index) {
		const char = text[index];
		if (char === "\\") index += 1;
		else if (char === ")") {
			if (numExtraOpened === 0) return index;
			numExtraOpened -= 1;
		} else if (char === "[") index = squaredBracketBlockContentEndFrom(text, index);
		else if (char === "(") numExtraOpened += 1;
	}
	throw new Error(`Missing closing ')'`);
}
/**
* Find the index of the last character of a culry-bracket "{}" block.
* The returned index corresponds to the one of the } closing the blockor -1 if the opening { does not make a block.
*/
function curlyBracketBlockContentEndFrom(text, from) {
	let foundComma = false;
	for (let index = from; index !== text.length; ++index) {
		const char = text[index];
		if (isDigit$1(char)) {} else if (from === index) return -1;
		else if (char === ",") {
			if (foundComma) return -1;
			foundComma = true;
		} else if (char === "}") return index;
		else return -1;
	}
	return -1;
}
/**
* Find the index past-one of the last character of the block starting at index "from" in "text"
*/
function blockEndFrom(text, from, unicodeMode, mode) {
	switch (text[from]) {
		case "[":
			if (mode === 1) return from + 1;
			return squaredBracketBlockContentEndFrom(text, from + 1) + 1;
		case "{": {
			if (mode === 1) return from + 1;
			const foundEnd = curlyBracketBlockContentEndFrom(text, from + 1);
			if (foundEnd === -1) return from + 1;
			return foundEnd + 1;
		}
		case "(":
			if (mode === 1) return from + 1;
			return parenthesisBlockContentEndFrom(text, from + 1) + 1;
		case "]":
		case "}":
		case ")": return from + 1;
		case "\\": {
			const next1 = text[from + 1];
			switch (next1) {
				case "x":
					if (isHexaDigit(text[from + 2]) && isHexaDigit(text[from + 3])) return from + 4;
					throw new Error(`Unexpected token '${text.substring(from, from + 4)}' found`);
				case "u":
					if (text[from + 2] === "{") {
						if (!unicodeMode) return from + 2;
						if (text[from + 4] === "}") {
							if (isHexaDigit(text[from + 3])) return from + 5;
							throw new Error(`Unexpected token '${text.substring(from, from + 5)}' found`);
						}
						if (text[from + 5] === "}") {
							if (isHexaDigit(text[from + 3]) && isHexaDigit(text[from + 4])) return from + 6;
							throw new Error(`Unexpected token '${text.substring(from, from + 6)}' found`);
						}
						if (text[from + 6] === "}") {
							if (isHexaDigit(text[from + 3]) && isHexaDigit(text[from + 4]) && isHexaDigit(text[from + 5])) return from + 7;
							throw new Error(`Unexpected token '${text.substring(from, from + 7)}' found`);
						}
						if (text[from + 7] === "}") {
							if (isHexaDigit(text[from + 3]) && isHexaDigit(text[from + 4]) && isHexaDigit(text[from + 5]) && isHexaDigit(text[from + 6])) return from + 8;
							throw new Error(`Unexpected token '${text.substring(from, from + 8)}' found`);
						}
						if (text[from + 8] === "}" && isHexaDigit(text[from + 3]) && isHexaDigit(text[from + 4]) && isHexaDigit(text[from + 5]) && isHexaDigit(text[from + 6]) && isHexaDigit(text[from + 7])) return from + 9;
						throw new Error(`Unexpected token '${text.substring(from, from + 9)}' found`);
					}
					if (isHexaDigit(text[from + 2]) && isHexaDigit(text[from + 3]) && isHexaDigit(text[from + 4]) && isHexaDigit(text[from + 5])) return from + 6;
					throw new Error(`Unexpected token '${text.substring(from, from + 6)}' found`);
				case "p":
				case "P": {
					if (!unicodeMode) return from + 2;
					let subIndex = from + 2;
					for (; subIndex < text.length && text[subIndex] !== "}"; subIndex += text[subIndex] === "\\" ? 2 : 1);
					if (text[subIndex] !== "}") throw new Error(`Invalid \\P definition`);
					return subIndex + 1;
				}
				case "k": {
					let subIndex = from + 2;
					for (; subIndex < text.length && text[subIndex] !== ">"; ++subIndex);
					if (text[subIndex] !== ">") {
						if (!unicodeMode) return from + 2;
						throw new Error(`Invalid \\k definition`);
					}
					return subIndex + 1;
				}
				default:
					if (isDigit$1(next1)) {
						const maxIndex = unicodeMode ? text.length : Math.min(from + 4, text.length);
						let subIndex = from + 2;
						for (; subIndex < maxIndex && isDigit$1(text[subIndex]); ++subIndex);
						return subIndex;
					}
					return from + (unicodeMode ? charSizeAt(text, from + 1) : 1) + 1;
			}
		}
		default: return from + (unicodeMode ? charSizeAt(text, from) : 1);
	}
}
/**
* Extract the block starting at "from" in "text"
* @internal
*/
function readFrom(text, from, unicodeMode, mode) {
	const to = blockEndFrom(text, from, unicodeMode, mode);
	return text.substring(from, to);
}
//#endregion
//#region src/arbitrary/_internals/helpers/UnicodePropertyData.ts
/** @internal */
const NON_BINARY_ALIASES_TO_PROP_NAMES = {
	gc: "General_Category",
	sc: "Script",
	scx: "Script_Extensions"
};
/** @internal */
const BINARY_PROP_NAMES_TO_ALIASES = {
	ASCII: "ASCII",
	ASCII_Hex_Digit: "AHex",
	Alphabetic: "Alpha",
	Any: "Any",
	Assigned: "Assigned",
	Bidi_Control: "Bidi_C",
	Bidi_Mirrored: "Bidi_M",
	Case_Ignorable: "CI",
	Cased: "Cased",
	Changes_When_Casefolded: "CWCF",
	Changes_When_Casemapped: "CWCM",
	Changes_When_Lowercased: "CWL",
	Changes_When_NFKC_Casefolded: "CWKCF",
	Changes_When_Titlecased: "CWT",
	Changes_When_Uppercased: "CWU",
	Dash: "Dash",
	Default_Ignorable_Code_Point: "DI",
	Deprecated: "Dep",
	Diacritic: "Dia",
	Emoji: "Emoji",
	Emoji_Component: "Emoji_Component",
	Emoji_Modifier: "Emoji_Modifier",
	Emoji_Modifier_Base: "Emoji_Modifier_Base",
	Emoji_Presentation: "Emoji_Presentation",
	Extended_Pictographic: "Extended_Pictographic",
	Extender: "Ext",
	Grapheme_Base: "Gr_Base",
	Grapheme_Extend: "Gr_Ext",
	Hex_Digit: "Hex",
	IDS_Binary_Operator: "IDSB",
	IDS_Trinary_Operator: "IDST",
	ID_Continue: "IDC",
	ID_Start: "IDS",
	Ideographic: "Ideo",
	Join_Control: "Join_C",
	Logical_Order_Exception: "LOE",
	Lowercase: "Lower",
	Math: "Math",
	Noncharacter_Code_Point: "NChar",
	Pattern_Syntax: "Pat_Syn",
	Pattern_White_Space: "Pat_WS",
	Quotation_Mark: "QMark",
	Radical: "Radical",
	Regional_Indicator: "RI",
	Sentence_Terminal: "STerm",
	Soft_Dotted: "SD",
	Terminal_Punctuation: "Term",
	Unified_Ideograph: "UIdeo",
	Uppercase: "Upper",
	Variation_Selector: "VS",
	White_Space: "space",
	XID_Continue: "XIDC",
	XID_Start: "XIDS"
};
/** @internal */
const BINARY_ALIASES_TO_PROP_NAMES = inverseMap(BINARY_PROP_NAMES_TO_ALIASES);
/** @internal */
const GENERAL_CATEGORY_VALUE_TO_ALIASES = {
	Cased_Letter: "LC",
	Close_Punctuation: "Pe",
	Connector_Punctuation: "Pc",
	Control: ["Cc", "cntrl"],
	Currency_Symbol: "Sc",
	Dash_Punctuation: "Pd",
	Decimal_Number: ["Nd", "digit"],
	Enclosing_Mark: "Me",
	Final_Punctuation: "Pf",
	Format: "Cf",
	Initial_Punctuation: "Pi",
	Letter: "L",
	Letter_Number: "Nl",
	Line_Separator: "Zl",
	Lowercase_Letter: "Ll",
	Mark: ["M", "Combining_Mark"],
	Math_Symbol: "Sm",
	Modifier_Letter: "Lm",
	Modifier_Symbol: "Sk",
	Nonspacing_Mark: "Mn",
	Number: "N",
	Open_Punctuation: "Ps",
	Other: "C",
	Other_Letter: "Lo",
	Other_Number: "No",
	Other_Punctuation: "Po",
	Other_Symbol: "So",
	Paragraph_Separator: "Zp",
	Private_Use: "Co",
	Punctuation: ["P", "punct"],
	Separator: "Z",
	Space_Separator: "Zs",
	Spacing_Mark: "Mc",
	Surrogate: "Cs",
	Symbol: "S",
	Titlecase_Letter: "Lt",
	Unassigned: "Cn",
	Uppercase_Letter: "Lu"
};
/** @internal */
const GENERAL_CATEGORY_VALUE_ALIASES_TO_VALUES = inverseMap(GENERAL_CATEGORY_VALUE_TO_ALIASES);
/** @internal */
const SCRIPT_VALUE_TO_ALIASES = {
	Adlam: "Adlm",
	Ahom: "Ahom",
	Anatolian_Hieroglyphs: "Hluw",
	Arabic: "Arab",
	Armenian: "Armn",
	Avestan: "Avst",
	Balinese: "Bali",
	Bamum: "Bamu",
	Bassa_Vah: "Bass",
	Batak: "Batk",
	Bengali: "Beng",
	Bhaiksuki: "Bhks",
	Bopomofo: "Bopo",
	Brahmi: "Brah",
	Braille: "Brai",
	Buginese: "Bugi",
	Buhid: "Buhd",
	Canadian_Aboriginal: "Cans",
	Carian: "Cari",
	Caucasian_Albanian: "Aghb",
	Chakma: "Cakm",
	Cham: "Cham",
	Cherokee: "Cher",
	Common: "Zyyy",
	Coptic: ["Copt", "Qaac"],
	Cuneiform: "Xsux",
	Cypriot: "Cprt",
	Cyrillic: "Cyrl",
	Deseret: "Dsrt",
	Devanagari: "Deva",
	Dogra: "Dogr",
	Duployan: "Dupl",
	Egyptian_Hieroglyphs: "Egyp",
	Elbasan: "Elba",
	Ethiopic: "Ethi",
	Georgian: "Geor",
	Glagolitic: "Glag",
	Gothic: "Goth",
	Grantha: "Gran",
	Greek: "Grek",
	Gujarati: "Gujr",
	Gunjala_Gondi: "Gong",
	Gurmukhi: "Guru",
	Han: "Hani",
	Hangul: "Hang",
	Hanifi_Rohingya: "Rohg",
	Hanunoo: "Hano",
	Hatran: "Hatr",
	Hebrew: "Hebr",
	Hiragana: "Hira",
	Imperial_Aramaic: "Armi",
	Inherited: ["Zinh", "Qaai"],
	Inscriptional_Pahlavi: "Phli",
	Inscriptional_Parthian: "Prti",
	Javanese: "Java",
	Kaithi: "Kthi",
	Kannada: "Knda",
	Katakana: "Kana",
	Kayah_Li: "Kali",
	Kharoshthi: "Khar",
	Khmer: "Khmr",
	Khojki: "Khoj",
	Khudawadi: "Sind",
	Lao: "Laoo",
	Latin: "Latn",
	Lepcha: "Lepc",
	Limbu: "Limb",
	Linear_A: "Lina",
	Linear_B: "Linb",
	Lisu: "Lisu",
	Lycian: "Lyci",
	Lydian: "Lydi",
	Mahajani: "Mahj",
	Makasar: "Maka",
	Malayalam: "Mlym",
	Mandaic: "Mand",
	Manichaean: "Mani",
	Marchen: "Marc",
	Medefaidrin: "Medf",
	Masaram_Gondi: "Gonm",
	Meetei_Mayek: "Mtei",
	Mende_Kikakui: "Mend",
	Meroitic_Cursive: "Merc",
	Meroitic_Hieroglyphs: "Mero",
	Miao: "Plrd",
	Modi: "Modi",
	Mongolian: "Mong",
	Mro: "Mroo",
	Multani: "Mult",
	Myanmar: "Mymr",
	Nabataean: "Nbat",
	New_Tai_Lue: "Talu",
	Newa: "Newa",
	Nko: "Nkoo",
	Nushu: "Nshu",
	Ogham: "Ogam",
	Ol_Chiki: "Olck",
	Old_Hungarian: "Hung",
	Old_Italic: "Ital",
	Old_North_Arabian: "Narb",
	Old_Permic: "Perm",
	Old_Persian: "Xpeo",
	Old_Sogdian: "Sogo",
	Old_South_Arabian: "Sarb",
	Old_Turkic: "Orkh",
	Oriya: "Orya",
	Osage: "Osge",
	Osmanya: "Osma",
	Pahawh_Hmong: "Hmng",
	Palmyrene: "Palm",
	Pau_Cin_Hau: "Pauc",
	Phags_Pa: "Phag",
	Phoenician: "Phnx",
	Psalter_Pahlavi: "Phlp",
	Rejang: "Rjng",
	Runic: "Runr",
	Samaritan: "Samr",
	Saurashtra: "Saur",
	Sharada: "Shrd",
	Shavian: "Shaw",
	Siddham: "Sidd",
	SignWriting: "Sgnw",
	Sinhala: "Sinh",
	Sogdian: "Sogd",
	Sora_Sompeng: "Sora",
	Soyombo: "Soyo",
	Sundanese: "Sund",
	Syloti_Nagri: "Sylo",
	Syriac: "Syrc",
	Tagalog: "Tglg",
	Tagbanwa: "Tagb",
	Tai_Le: "Tale",
	Tai_Tham: "Lana",
	Tai_Viet: "Tavt",
	Takri: "Takr",
	Tamil: "Taml",
	Tangut: "Tang",
	Telugu: "Telu",
	Thaana: "Thaa",
	Thai: "Thai",
	Tibetan: "Tibt",
	Tifinagh: "Tfng",
	Tirhuta: "Tirh",
	Ugaritic: "Ugar",
	Vai: "Vaii",
	Warang_Citi: "Wara",
	Yi: "Yiii",
	Zanabazar_Square: "Zanb"
};
/** @internal */
const SCRIPT_VALUE_ALIASES_TO_VALUES = inverseMap(SCRIPT_VALUE_TO_ALIASES);
function inverseMap(data) {
	const inverse = {};
	for (const name of Object.keys(data)) {
		const value = data[name];
		if (Array.isArray(value)) for (let i = 0; i !== value.length; ++i) inverse[value[i]] = name;
		else inverse[value] = name;
	}
	return inverse;
}
function isGeneralCategoryValue(value) {
	return value in GENERAL_CATEGORY_VALUE_TO_ALIASES || value in GENERAL_CATEGORY_VALUE_ALIASES_TO_VALUES;
}
function isBinaryPropertyName(name) {
	return name in BINARY_PROP_NAMES_TO_ALIASES || name in BINARY_ALIASES_TO_PROP_NAMES;
}
function getCanonicalName(name) {
	if (name in NON_BINARY_ALIASES_TO_PROP_NAMES) return NON_BINARY_ALIASES_TO_PROP_NAMES[name];
	if (name in BINARY_ALIASES_TO_PROP_NAMES) return BINARY_ALIASES_TO_PROP_NAMES[name];
	if (name in BINARY_PROP_NAMES_TO_ALIASES || name === "General_Category" || name === "Script" || name === "Script_Extensions") return name;
	throw new Error(`Unknown Unicode property name: ${name}`);
}
function getCanonicalValue(value) {
	if (value in GENERAL_CATEGORY_VALUE_ALIASES_TO_VALUES) return GENERAL_CATEGORY_VALUE_ALIASES_TO_VALUES[value];
	if (value in SCRIPT_VALUE_ALIASES_TO_VALUES) return SCRIPT_VALUE_ALIASES_TO_VALUES[value];
	if (value in BINARY_ALIASES_TO_PROP_NAMES) return BINARY_ALIASES_TO_PROP_NAMES[value];
	if (value in GENERAL_CATEGORY_VALUE_TO_ALIASES || value in SCRIPT_VALUE_TO_ALIASES || value in BINARY_PROP_NAMES_TO_ALIASES) return value;
	throw new Error(`Unknown Unicode property value: ${value}`);
}
/**
* Resolve a Unicode property escape specification into a structured token
* that matches the regexp-tree AST format.
*
* @param propertySpec - The content between \p\{ and \}, e.g. "Letter", "Script=Latin", "Emoji"
* @param negative - true for \P\{\}, false for \p\{\}
* @internal
*/
function resolveUnicodeProperty(propertySpec, negative) {
	const equalIndex = propertySpec.indexOf("=");
	if (equalIndex !== -1) {
		const name = propertySpec.substring(0, equalIndex);
		const value = propertySpec.substring(equalIndex + 1);
		return {
			type: "UnicodeProperty",
			name,
			value,
			negative,
			shorthand: false,
			binary: false,
			canonicalName: getCanonicalName(name),
			canonicalValue: getCanonicalValue(value)
		};
	}
	if (isGeneralCategoryValue(propertySpec)) return {
		type: "UnicodeProperty",
		name: "General_Category",
		value: propertySpec,
		negative,
		shorthand: true,
		binary: false,
		canonicalName: "General_Category",
		canonicalValue: getCanonicalValue(propertySpec)
	};
	if (isBinaryPropertyName(propertySpec)) {
		const canonicalName = getCanonicalName(propertySpec);
		return {
			type: "UnicodeProperty",
			name: propertySpec,
			value: propertySpec,
			negative,
			shorthand: false,
			binary: true,
			canonicalName,
			canonicalValue: canonicalName
		};
	}
	throw new Error(`Invalid Unicode property: ${propertySpec}`);
}
//#endregion
//#region src/arbitrary/_internals/helpers/TokenizeRegex.ts
const safeStringFromCodePoint$2 = String.fromCodePoint;
/**
* Pop the last pushed token and return it,
* Throw if unable to pop it.
*/
function safePop(tokens) {
	const previous = tokens.pop();
	if (previous === void 0) throw new Error("Unable to extract token preceeding the currently parsed one");
	return previous;
}
/**
* Internal helper checking if a character is a decimal one, ie: 0-9
*/
function isDigit(char) {
	return char >= "0" && char <= "9";
}
/**
* Create a simple char token
*/
function simpleChar(char, escaped) {
	return {
		type: "Char",
		kind: "simple",
		symbol: char,
		value: char,
		codePoint: char.codePointAt(0) || -1,
		escaped
	};
}
/**
* Create a meta char token corresponding to things such as \t, \n...
*/
function metaEscapedChar(block, symbol) {
	return {
		type: "Char",
		kind: "meta",
		symbol,
		value: block,
		codePoint: symbol.codePointAt(0) || -1
	};
}
function toSingleToken(tokens, allowEmpty) {
	if (tokens.length > 1) return {
		type: "Alternative",
		expressions: tokens
	};
	if (!allowEmpty && tokens.length === 0) throw new Error(`Unsupported no token`);
	return tokens[0];
}
/**
* Create a character token based on a full block.
* This function does not check the block itself, only call it with valid blocks.
*/
function blockToCharToken(block) {
	if (block[0] === "\\") {
		const next = block[1];
		switch (next) {
			case "x": {
				const allDigits = block.substring(2);
				const codePoint = Number.parseInt(allDigits, 16);
				return {
					type: "Char",
					kind: "hex",
					symbol: safeStringFromCodePoint$2(codePoint),
					value: block,
					codePoint
				};
			}
			case "u": {
				if (block === "\\u") return simpleChar("u", true);
				const allDigits = block[2] === "{" ? block.substring(3, block.length - 1) : block.substring(2);
				const codePoint = Number.parseInt(allDigits, 16);
				return {
					type: "Char",
					kind: "unicode",
					symbol: safeStringFromCodePoint$2(codePoint),
					value: block,
					codePoint
				};
			}
			case "0": return metaEscapedChar(block, "\0");
			case "n": return metaEscapedChar(block, "\n");
			case "f": return metaEscapedChar(block, "\f");
			case "r": return metaEscapedChar(block, "\r");
			case "t": return metaEscapedChar(block, "	");
			case "v": return metaEscapedChar(block, "\v");
			case "w":
			case "W":
			case "d":
			case "D":
			case "s":
			case "S":
			case "b":
			case "B": return {
				type: "Char",
				kind: "meta",
				symbol: void 0,
				value: block,
				codePoint: NaN
			};
			default:
				if (isDigit(next)) {
					const allDigits = block.substring(1);
					const codePoint = Number(allDigits);
					return {
						type: "Char",
						kind: "decimal",
						symbol: safeStringFromCodePoint$2(codePoint),
						value: block,
						codePoint
					};
				}
				if (block.length > 2 && (next === "p" || next === "P")) {
					const negative = next === "P";
					return resolveUnicodeProperty(block.substring(3, block.length - 1), negative);
				}
				return simpleChar(block.substring(1), true);
		}
	}
	return simpleChar(block);
}
/**
* Build tokens corresponding to the received regex and push them into the passed array of tokens
*/
function pushTokens(tokens, regexSource, unicodeMode, groups) {
	let disjunctions = null;
	for (let index = 0, block = readFrom(regexSource, index, unicodeMode, 0); index !== regexSource.length; index += block.length, block = readFrom(regexSource, index, unicodeMode, 0)) {
		const firstInBlock = block[0];
		switch (firstInBlock) {
			case "|":
				if (disjunctions === null) disjunctions = [];
				disjunctions.push(toSingleToken(tokens.splice(0), true) || null);
				break;
			case ".":
				tokens.push({
					type: "Char",
					kind: "meta",
					symbol: block,
					value: block,
					codePoint: NaN
				});
				break;
			case "*":
			case "+": {
				const previous = safePop(tokens);
				tokens.push({
					type: "Repetition",
					expression: previous,
					quantifier: {
						type: "Quantifier",
						kind: firstInBlock,
						greedy: true
					}
				});
				break;
			}
			case "?": {
				const previous = safePop(tokens);
				if (previous.type === "Repetition") {
					previous.quantifier.greedy = false;
					tokens.push(previous);
				} else tokens.push({
					type: "Repetition",
					expression: previous,
					quantifier: {
						type: "Quantifier",
						kind: firstInBlock,
						greedy: true
					}
				});
				break;
			}
			case "{": {
				if (block === "{") {
					tokens.push(simpleChar(block));
					break;
				}
				const previous = safePop(tokens);
				const quantifierTokens = block.substring(1, block.length - 1).split(",");
				const from = Number(quantifierTokens[0]);
				const to = quantifierTokens.length === 1 ? from : quantifierTokens[1].length !== 0 ? Number(quantifierTokens[1]) : void 0;
				tokens.push({
					type: "Repetition",
					expression: previous,
					quantifier: {
						type: "Quantifier",
						kind: "Range",
						greedy: true,
						from,
						to
					}
				});
				break;
			}
			case "[": {
				const blockContent = block.substring(1, block.length - 1);
				const subTokens = [];
				let negative = void 0;
				let previousWasSimpleDash = false;
				for (let subIndex = 0, subBlock = readFrom(blockContent, subIndex, unicodeMode, 1); subIndex !== blockContent.length; subIndex += subBlock.length, subBlock = readFrom(blockContent, subIndex, unicodeMode, 1)) {
					if (subIndex === 0 && subBlock === "^") {
						negative = true;
						continue;
					}
					const newToken = blockToCharToken(subBlock);
					if (subBlock === "-") {
						subTokens.push(newToken);
						previousWasSimpleDash = true;
					} else {
						const operand1Token = subTokens.length >= 2 ? subTokens[subTokens.length - 2] : void 0;
						if (previousWasSimpleDash && operand1Token !== void 0 && operand1Token.type === "Char" && newToken.type === "Char") {
							subTokens.pop();
							subTokens.pop();
							subTokens.push({
								type: "ClassRange",
								from: operand1Token,
								to: newToken
							});
						} else subTokens.push(newToken);
						previousWasSimpleDash = false;
					}
				}
				tokens.push({
					type: "CharacterClass",
					expressions: subTokens,
					negative
				});
				break;
			}
			case "(": {
				const blockContent = block.substring(1, block.length - 1);
				const subTokens = [];
				if (blockContent[0] === "?") {
					if (blockContent[1] === ":") {
						pushTokens(subTokens, blockContent.substring(2), unicodeMode, groups);
						tokens.push({
							type: "Group",
							capturing: false,
							expression: toSingleToken(subTokens)
						});
					} else if (blockContent[1] === "=" || blockContent[1] === "!") {
						pushTokens(subTokens, blockContent.substring(2), unicodeMode, groups);
						tokens.push({
							type: "Assertion",
							kind: "Lookahead",
							negative: blockContent[1] === "!" ? true : void 0,
							assertion: toSingleToken(subTokens)
						});
					} else if (blockContent[1] === "<" && (blockContent[2] === "=" || blockContent[2] === "!")) {
						pushTokens(subTokens, blockContent.substring(3), unicodeMode, groups);
						tokens.push({
							type: "Assertion",
							kind: "Lookbehind",
							negative: blockContent[2] === "!" ? true : void 0,
							assertion: toSingleToken(subTokens)
						});
					} else {
						const chunks = blockContent.split(">");
						if (chunks.length < 2 || chunks[0][1] !== "<") throw new Error(`Unsupported regex content found at ${JSON.stringify(block)}`);
						const groupIndex = ++groups.lastIndex;
						const nameRaw = chunks[0].substring(2);
						groups.named.set(nameRaw, groupIndex);
						pushTokens(subTokens, chunks.slice(1).join(">"), unicodeMode, groups);
						tokens.push({
							type: "Group",
							capturing: true,
							nameRaw,
							name: nameRaw,
							number: groupIndex,
							expression: toSingleToken(subTokens)
						});
					}
				} else {
					const groupIndex = ++groups.lastIndex;
					pushTokens(subTokens, blockContent, unicodeMode, groups);
					tokens.push({
						type: "Group",
						capturing: true,
						number: groupIndex,
						expression: toSingleToken(subTokens)
					});
				}
				break;
			}
			default: if (block === "^") tokens.push({
				type: "Assertion",
				kind: block
			});
			else if (block === "$") tokens.push({
				type: "Assertion",
				kind: block
			});
			else if (block[0] === "\\" && isDigit(block[1])) {
				const reference = Number(block.substring(1));
				if (unicodeMode || reference <= groups.lastIndex) tokens.push({
					type: "Backreference",
					kind: "number",
					number: reference,
					reference
				});
				else tokens.push(blockToCharToken(block));
			} else if (block[0] === "\\" && block[1] === "k" && block.length !== 2) {
				const referenceRaw = block.substring(3, block.length - 1);
				tokens.push({
					type: "Backreference",
					kind: "name",
					number: groups.named.get(referenceRaw) || 0,
					referenceRaw,
					reference: referenceRaw
				});
			} else tokens.push(blockToCharToken(block));
		}
	}
	if (disjunctions !== null) {
		disjunctions.push(toSingleToken(tokens.splice(0), true) || null);
		let currentDisjunction = {
			type: "Disjunction",
			left: disjunctions[0],
			right: disjunctions[1]
		};
		for (let index = 2; index < disjunctions.length; ++index) currentDisjunction = {
			type: "Disjunction",
			left: currentDisjunction,
			right: disjunctions[index]
		};
		tokens.push(currentDisjunction);
	}
}
/**
* Build the AST corresponding to the passed instance of RegExp
*/
function tokenizeRegex(regex) {
	const unicodeMode = safeIndexOf([...regex.flags], "u") !== -1;
	const regexSource = regex.source;
	const tokens = [];
	pushTokens(tokens, regexSource, unicodeMode, {
		lastIndex: 0,
		named: /* @__PURE__ */ new Map()
	});
	return toSingleToken(tokens);
}
//#endregion
//#region src/arbitrary/_internals/helpers/UnicodePropertyArbitraryHelper.ts
/** @internal */
const safeStringFromCodePoint$1 = String.fromCodePoint;
/** @internal */
function getPropertySpec(astNode) {
	if (astNode.binary || astNode.shorthand) return astNode.canonicalValue;
	return `${astNode.canonicalName}=${astNode.canonicalValue}`;
}
/** @internal */
function appendRangesForRegex(regex, from, to, ranges) {
	let currentRangeStart = -1;
	for (let cp = from; cp <= to; ++cp) if (regex.test(safeStringFromCodePoint$1(cp))) {
		if (currentRangeStart === -1) currentRangeStart = cp;
	} else if (currentRangeStart !== -1) {
		const rangeEnd = cp - 1;
		ranges.push(currentRangeStart === rangeEnd ? [rangeEnd] : [currentRangeStart, rangeEnd]);
		currentRangeStart = -1;
	}
	if (currentRangeStart !== -1) ranges.push(currentRangeStart === to ? [to] : [currentRangeStart, to]);
}
/** @internal */
function extractRangesForProperty(propertySpec, negative) {
	const regex = new RegExp(`^\\${negative ? "P" : "p"}{${propertySpec}}$`, "u");
	const ranges = [];
	appendRangesForRegex(regex, 0, 55295, ranges);
	appendRangesForRegex(regex, 57344, 1114111, ranges);
	return ranges;
}
/** @internal */
const cache = /* @__PURE__ */ new Map();
/** @internal */
function extractRangesForPropertyOrFromCache(propertySpec, negative) {
	const cacheKey = `${negative ? "P" : "p"}:${propertySpec}`;
	const cachedRanges = cache.get(cacheKey);
	if (cachedRanges !== void 0) return cachedRanges;
	const ranges = extractRangesForProperty(propertySpec, negative);
	cache.set(cacheKey, ranges);
	return ranges;
}
/**
* Build an arbitrary producing characters matching a Unicode property (`\p{…}` / `\P{…}`).
* @internal
*/
function unicodePropertyArbitrary(astNode) {
	return mapToConstant(...safeMap(extractRangesForPropertyOrFromCache(getPropertySpec(astNode), astNode.negative), (range) => convertGraphemeRangeToMapToConstantEntry(range)));
}
//#endregion
//#region src/arbitrary/stringMatching.ts
const safeStringFromCodePoint = String.fromCodePoint;
const wordChars = [..."abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"];
const digitChars = [..."0123456789"];
const spaceChars = [..." 	\r\n\v\f"];
const newLineChars = [..."\r\n"];
const terminatorChars = [...""];
const newLineAndTerminatorChars = [...newLineChars, ...terminatorChars];
const wordCharsSet = new SSet(wordChars);
const digitCharsSet = new SSet(digitChars);
const spaceCharsSet = new SSet(spaceChars);
const terminatorCharsSet = new SSet(terminatorChars);
const newLineAndTerminatorCharsSet = new SSet(newLineAndTerminatorChars);
const defaultChar = () => string({
	unit: "grapheme-ascii",
	minLength: 1,
	maxLength: 1
});
function raiseUnsupportedASTNode(astNode) {
	return new SError(`Unsupported AST node! Received: ${stringify(astNode)}`);
}
/**
* Convert an AST of tokens into an arbitrary able to produce the requested pattern
* @internal
*/
function toMatchingArbitrary(astNode, constraints, flags) {
	switch (astNode.type) {
		case "Char":
			if (astNode.kind === "meta") switch (astNode.value) {
				case "\\w": return constantFrom(...wordChars);
				case "\\W": return defaultChar().filter((c) => !safeHas(wordCharsSet, c));
				case "\\d": return constantFrom(...digitChars);
				case "\\D": return defaultChar().filter((c) => !safeHas(digitCharsSet, c));
				case "\\s": return constantFrom(...spaceChars);
				case "\\S": return defaultChar().filter((c) => !safeHas(spaceCharsSet, c));
				case "\\b":
				case "\\B": throw new SError(`Meta character ${astNode.value} not implemented yet!`);
				case ".": {
					const forbiddenChars = flags.dotAll ? terminatorCharsSet : newLineAndTerminatorCharsSet;
					return defaultChar().filter((c) => !safeHas(forbiddenChars, c));
				}
			}
			if (astNode.symbol === void 0) throw new SError(`Unexpected undefined symbol received for non-meta Char! Received: ${stringify(astNode)}`);
			return constant(astNode.symbol);
		case "Repetition": {
			const node = toMatchingArbitrary(astNode.expression, constraints, flags);
			switch (astNode.quantifier.kind) {
				case "*": return string({
					...constraints,
					unit: node
				});
				case "+": return string({
					...constraints,
					minLength: 1,
					unit: node
				});
				case "?": return string({
					...constraints,
					minLength: 0,
					maxLength: 1,
					unit: node
				});
				case "Range": return string({
					...constraints,
					minLength: astNode.quantifier.from,
					maxLength: astNode.quantifier.to,
					unit: node
				});
				default: throw raiseUnsupportedASTNode(astNode.quantifier);
			}
		}
		case "Quantifier": throw new SError(`Wrongly defined AST tree, Quantifier nodes not supposed to be scanned!`);
		case "Alternative": {
			const childrenArbitraries = [];
			let pendingAggregatedValue = "";
			for (const n of astNode.expressions) if (n.type === "Char" && n.kind !== "meta" && n.symbol !== void 0) pendingAggregatedValue += n.symbol;
			else if (flags.multiline || n.type !== "Assertion" || n.kind !== "^" && n.kind !== "$") {
				if (pendingAggregatedValue !== "") {
					safePush(childrenArbitraries, constant(pendingAggregatedValue));
					pendingAggregatedValue = "";
				}
				safePush(childrenArbitraries, toMatchingArbitrary(n, constraints, flags));
			}
			if (pendingAggregatedValue !== "") safePush(childrenArbitraries, constant(pendingAggregatedValue));
			if (childrenArbitraries.length === 0) return constant("");
			if (childrenArbitraries.length === 1) return childrenArbitraries[0];
			return tuple(...childrenArbitraries).map((vs) => safeJoin(vs, ""));
		}
		case "CharacterClass":
			if (astNode.negative) {
				const childrenArbitraries = safeMap(astNode.expressions, (n) => toMatchingArbitrary(n, constraints, flags));
				return defaultChar().filter((c) => safeEvery(childrenArbitraries, (arb) => !arb.canShrinkWithoutContext(c)));
			}
			return oneof(...safeMap(astNode.expressions, (n) => toMatchingArbitrary(n, constraints, flags)));
		case "ClassRange": {
			const min = astNode.from.codePoint;
			const max = astNode.to.codePoint;
			return integer({
				min,
				max
			}).map((n) => safeStringFromCodePoint(n), (c) => {
				if (typeof c !== "string") throw new SError("Invalid type");
				if ([...c].length !== 1) throw new SError("Invalid length");
				return safeCharCodeAt(c, 0);
			});
		}
		case "Group": return toMatchingArbitrary(astNode.expression, constraints, flags);
		case "Disjunction": {
			const stack = [astNode.left, astNode.right];
			const branches = [];
			for (let i = 0; i !== stack.length; ++i) {
				const node = stack[i];
				if (node === null) safePush(branches, constant(""));
				else if (node.type === "Disjunction") {
					safePush(stack, node.left);
					safePush(stack, node.right);
				} else safePush(branches, toMatchingArbitrary(node, constraints, flags));
			}
			return oneof(...branches);
		}
		case "Assertion":
			if (astNode.kind === "^" || astNode.kind === "$") {
				if (flags.multiline) {
					if (astNode.kind === "^") return oneof(constant(""), tuple(string({ unit: defaultChar() }), constantFrom(...newLineChars)).map((t) => `${t[0]}${t[1]}`, (value) => {
						if (typeof value !== "string" || value.length === 0) throw new SError("Invalid type");
						return [safeSubstring(value, 0, value.length - 1), value[value.length - 1]];
					}));
					else return oneof(constant(""), tuple(constantFrom(...newLineChars), string({ unit: defaultChar() })).map((t) => `${t[0]}${t[1]}`, (value) => {
						if (typeof value !== "string" || value.length === 0) throw new SError("Invalid type");
						return [value[0], safeSubstring(value, 1)];
					}));
				}
				return constant("");
			}
			throw new SError(`Assertions of kind ${astNode.kind} not implemented yet!`);
		case "Backreference": throw new SError(`Backreference nodes not implemented yet!`);
		case "UnicodeProperty": return unicodePropertyArbitrary(astNode);
		default: throw raiseUnsupportedASTNode(astNode);
	}
}
/**
* For strings matching the provided regex
*
* @param regex - Arbitrary able to generate random strings (possibly multiple characters)
* @param constraints - Constraints to apply when building instances
*
* @remarks Since 3.10.0
* @public
*/
function stringMatching(regex, constraints = {}) {
	for (const flag of regex.flags) if (flag !== "d" && flag !== "g" && flag !== "m" && flag !== "s" && flag !== "u") throw new SError(`Unable to use "stringMatching" against a regex using the flag ${flag}`);
	const maxLength = constraints.maxLength;
	const sanitizedConstraints = {
		size: constraints.size,
		maxLength
	};
	const flags = {
		multiline: regex.multiline,
		dotAll: regex.dotAll
	};
	let regexRootToken = addMissingDotStar(tokenizeRegex(regex));
	if (maxLength !== void 0) regexRootToken = clampRegexAst(regexRootToken, maxLength);
	const baseArbitrary = toMatchingArbitrary(regexRootToken, sanitizedConstraints, flags);
	if (maxLength !== void 0) return baseArbitrary.filter((s) => [...s].length <= maxLength);
	return baseArbitrary;
}
//#endregion
//#region src/arbitrary/_internals/helpers/ZipIterableIterators.ts
/** @internal */
function initZippedValues(its) {
	const vs = [];
	for (let index = 0; index !== its.length; ++index) vs.push(its[index].next());
	return vs;
}
/** @internal */
function nextZippedValues(its, vs) {
	for (let index = 0; index !== its.length; ++index) vs[index] = its[index].next();
}
/** @internal */
function isDoneZippedValues(vs) {
	for (let index = 0; index !== vs.length; ++index) if (vs[index].done) return true;
	return false;
}
/** @internal */
function* zipIterableIterators(...its) {
	const vs = initZippedValues(its);
	while (!isDoneZippedValues(vs)) {
		yield vs.map((v) => v.value);
		nextZippedValues(its, vs);
	}
}
//#endregion
//#region src/arbitrary/_internals/LimitedShrinkArbitrary.ts
/** @internal */
function* iotaFrom(startValue) {
	let value = startValue;
	while (true) {
		yield value;
		++value;
	}
}
/** @internal */
var LimitedShrinkArbitrary = class extends Arbitrary {
	constructor(arb, maxShrinks) {
		super();
		this.arb = arb;
		this.maxShrinks = maxShrinks;
	}
	generate(mrng, biasFactor) {
		const value = this.arb.generate(mrng, biasFactor);
		return this.valueMapper(value, 0);
	}
	canShrinkWithoutContext(value) {
		return this.arb.canShrinkWithoutContext(value);
	}
	shrink(value, context) {
		if (this.isSafeContext(context)) return this.safeShrink(value, context.originalContext, context.length);
		return this.safeShrink(value, void 0, 0);
	}
	safeShrink(value, originalContext, currentLength) {
		const remaining = this.maxShrinks - currentLength;
		if (remaining <= 0) return Stream.nil();
		return new Stream(zipIterableIterators(this.arb.shrink(value, originalContext), iotaFrom(currentLength + 1))).take(remaining).map((valueAndLength) => this.valueMapper(valueAndLength[0], valueAndLength[1]));
	}
	valueMapper(v, newLength) {
		const context = {
			originalContext: v.context,
			length: newLength
		};
		return new Value(v.value, context);
	}
	isSafeContext(context) {
		return context !== null && context !== void 0 && typeof context === "object" && "originalContext" in context && "length" in context;
	}
};
//#endregion
//#region src/arbitrary/limitShrink.ts
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
function limitShrink(arbitrary, maxShrinks) {
	return new LimitedShrinkArbitrary(arbitrary, maxShrinks);
}
//#endregion
//#region src/check/plugin/LifeCyclePlugins.ts
const LifeCyclePluginSymbol = Symbol.for("fast-check/plugin/life-cycle");
function computeResultingAfterHooks(teardownFunctions, hooks) {
	if (teardownFunctions.length === 0) return hooks.afterHooks;
	if (hooks.afterHooks.length === 0) return teardownFunctions.map((details) => details.fn);
	const afterAndPluginIndices = [];
	for (const value of teardownFunctions) {
		const { index, fn } = value;
		afterAndPluginIndices.push({
			index: hooks.beforeHooksIndices[index],
			fn
		});
	}
	for (let index = 0; index !== hooks.afterHooks.length; ++index) afterAndPluginIndices.push({
		index: hooks.afterHooksIndices[index],
		fn: hooks.afterHooks[index]
	});
	afterAndPluginIndices.sort((a, b) => a.index - b.index);
	return afterAndPluginIndices.map((details) => details.fn);
}
function lifeCycleHooksRunner(hooks, nestedRun, value) {
	let wrappedRunOutput = null;
	let wrappedRunContinuation = void 0;
	const teardownFunctions = [];
	if (hooks.beforeHooks.length !== 0) try {
		for (let index = 0; index !== hooks.beforeHooks.length; ++index) {
			const before = hooks.beforeHooks[index];
			if (wrappedRunContinuation === void 0) {
				const out = before();
				if (typeof out === "function") teardownFunctions.push({
					index,
					fn: out
				});
				if (typeof out === "object") wrappedRunContinuation = out.then((beforeOut) => {
					if (beforeOut !== void 0) teardownFunctions.push({
						index,
						fn: beforeOut
					});
					return null;
				});
			} else wrappedRunContinuation = wrappedRunContinuation.then(() => {
				const beforeOut = before();
				if (beforeOut === void 0) return null;
				if (typeof beforeOut === "function") {
					teardownFunctions.push({
						index,
						fn: beforeOut
					});
					return null;
				}
				return beforeOut.then((beforeOutNested) => {
					if (beforeOutNested !== void 0) teardownFunctions.push({
						index,
						fn: beforeOutNested
					});
					return null;
				});
			});
		}
	} catch (error) {
		wrappedRunOutput = { error };
	}
	if (wrappedRunOutput === null) {
		if (wrappedRunContinuation === void 0) {
			const out = nestedRun(value);
			if (out !== null && "then" in out) wrappedRunContinuation = out;
			else wrappedRunOutput = out;
		} else wrappedRunContinuation = wrappedRunContinuation.then(() => nestedRun(value), (error) => ({ error }));
	}
	if (wrappedRunContinuation === void 0) {
		const resultingAfterHooks = computeResultingAfterHooks(teardownFunctions, hooks);
		for (let index = resultingAfterHooks.length - 1; index >= 0; --index) {
			const after = resultingAfterHooks[index];
			if (wrappedRunContinuation === void 0) try {
				const out = after();
				if (typeof out === "object") wrappedRunContinuation = out.then(() => wrappedRunOutput, (error) => wrappedRunOutput || { error });
			} catch (error) {
				wrappedRunOutput = { error };
			}
			else wrappedRunContinuation = wrappedRunContinuation.then((previous) => {
				try {
					const out = after();
					if (typeof out === "object") return out.then(() => previous, (error) => previous || { error });
					return previous;
				} catch (error) {
					return previous || { error };
				}
			});
		}
	} else wrappedRunContinuation = wrappedRunContinuation.then((previousBeforeAfters) => {
		const resultingAfterHooks = computeResultingAfterHooks(teardownFunctions, hooks);
		if (resultingAfterHooks.length === 0) return previousBeforeAfters;
		let afterContinuation = Promise.resolve(previousBeforeAfters);
		for (let index = resultingAfterHooks.length - 1; index >= 0; --index) {
			const after = resultingAfterHooks[index];
			afterContinuation = afterContinuation.then((previous) => {
				try {
					const out = after();
					return out === void 0 ? previous : out.then(() => previous, (error) => previous || { error });
				} catch (error) {
					return previous || { error };
				}
			});
		}
		return afterContinuation;
	});
	return wrappedRunContinuation === void 0 ? wrappedRunOutput : wrappedRunContinuation;
}
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
function beforeEach(fn) {
	return (pluginIndex, pluginStore) => {
		let lifeCycleHooks = pluginStore.get(LifeCyclePluginSymbol);
		if (lifeCycleHooks !== void 0 && lifeCycleHooks.lastPluginIndex === pluginIndex - 1) {
			lifeCycleHooks.lastPluginIndex = pluginIndex;
			lifeCycleHooks.beforeHooks.push(fn);
			lifeCycleHooks.beforeHooksIndices.push(pluginIndex);
			return {};
		}
		lifeCycleHooks = {
			lastPluginIndex: pluginIndex,
			beforeHooks: [fn],
			beforeHooksIndices: [pluginIndex],
			afterHooks: [],
			afterHooksIndices: []
		};
		pluginStore.set(LifeCyclePluginSymbol, lifeCycleHooks);
		return { decorateRun: (nestedRun) => (value) => lifeCycleHooksRunner(lifeCycleHooks, nestedRun, value) };
	};
}
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
function afterEach(fn) {
	return (pluginIndex, pluginStore) => {
		let lifeCycleHooks = pluginStore.get(LifeCyclePluginSymbol);
		if (lifeCycleHooks !== void 0 && lifeCycleHooks.lastPluginIndex === pluginIndex - 1) {
			lifeCycleHooks.lastPluginIndex = pluginIndex;
			lifeCycleHooks.afterHooks.push(fn);
			lifeCycleHooks.afterHooksIndices.push(pluginIndex);
			return {};
		}
		lifeCycleHooks = {
			lastPluginIndex: pluginIndex,
			beforeHooks: [],
			beforeHooksIndices: [],
			afterHooks: [fn],
			afterHooksIndices: [pluginIndex]
		};
		pluginStore.set(LifeCyclePluginSymbol, lifeCycleHooks);
		return { decorateRun: (nestedRun) => (value) => lifeCycleHooksRunner(lifeCycleHooks, nestedRun, value) };
	};
}
//#endregion
//#region src/check/plugin/UnbiasedPlugin.ts
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
function unbiased() {
	return () => {
		return { decorateGenerate: (nestedGenerate) => (mrng, _runId) => nestedGenerate(mrng, void 0) };
	};
}
//#endregion
//#region src/check/plugin/EqualValuesPlugins.ts
/** @internal */
function fromSyncCachedForAsyncPath(cachedValue) {
	return cachedValue === null ? new PreconditionFailure() : cachedValue;
}
/** @internal */
function fromCached(cachedValue) {
	if (cachedValue !== null) {
		if ("then" in cachedValue) return cachedValue.then(fromSyncCachedForAsyncPath);
		else return cachedValue;
	}
	return new PreconditionFailure();
}
/** @internal */
function equalValuesRunner(coveredCases, nestedRun, value, skipRuns) {
	const stringifiedValue = stringify(value);
	if (coveredCases.has(stringifiedValue)) {
		const lastOutput = coveredCases.get(stringifiedValue);
		return skipRuns ? fromCached(lastOutput) : lastOutput;
	}
	const out = nestedRun(value);
	coveredCases.set(stringifiedValue, out);
	return out;
}
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
function ignoreEqualValues() {
	return () => {
		const coveredCases = /* @__PURE__ */ new Map();
		return { decorateRun: (nestedRun) => (value) => equalValuesRunner(coveredCases, nestedRun, value, false) };
	};
}
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
function skipEqualValues() {
	return () => {
		const coveredCases = /* @__PURE__ */ new Map();
		return { decorateRun: (nestedRun) => (value) => equalValuesRunner(coveredCases, nestedRun, value, true) };
	};
}
//#endregion
//#region src/check/plugin/InterruptAfterTimeLimitPlugin.ts
const safeSetTimeout$1 = setTimeout;
const safeClearTimeout$1 = clearTimeout;
const safePerformanceNow = typeof performance !== "undefined" ? performance.now.bind(performance) : Date.now.bind(Date);
/** @internal */
function interruptAfterDelay(timeMs, probe) {
	const limitTime = safePerformanceNow() + timeMs;
	let timeoutHandle = void 0;
	return {
		expired: () => safePerformanceNow() >= limitTime,
		clear: () => safeClearTimeout$1(timeoutHandle),
		promise: new Promise((resolve) => {
			timeoutHandle = safeSetTimeout$1(() => {
				if (probe.running) probe.interruptedWhileRunning = true;
				resolve(new PreconditionFailure(true));
			}, timeMs);
		})
	};
}
/** @internal */
function timeLimitRunner(interrupt, nestedRun, value, probe) {
	probe.running = true;
	if (interrupt.expired()) {
		probe.interruptedWhileRunning = true;
		probe.running = false;
		return new PreconditionFailure(true);
	}
	const runOut = nestedRun(value);
	if (runOut === null || !("then" in runOut)) {
		probe.running = false;
		return runOut;
	}
	runOut.finally(() => probe.running = false);
	return Promise.race([runOut, interrupt.promise]);
}
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
function interruptAfterTimeLimit(timeLimitMs, options = {}) {
	return () => {
		const probe = {
			interruptedWhileRunning: false,
			running: false
		};
		const interrupt = interruptAfterDelay(timeLimitMs, probe);
		return {
			decorateRun: (nestedRun) => (value) => timeLimitRunner(interrupt, nestedRun, value, probe),
			onAllRunsComplete: (runDetails) => {
				interrupt.clear();
				if (options.failOnInterrupt && !runDetails.failed && runDetails.interrupted && probe.interruptedWhileRunning) return reportRunDetails({
					...runDetails,
					failed: true
				});
			}
		};
	};
}
//#endregion
//#region src/check/plugin/TimeoutPlugin.ts
const safeSetTimeout = setTimeout;
const safeClearTimeout = clearTimeout;
/** @internal */
function timeoutAfter(timeMs) {
	let timeoutHandle = void 0;
	return {
		clear: () => safeClearTimeout(timeoutHandle),
		promise: new Promise((resolve) => {
			timeoutHandle = safeSetTimeout(() => {
				resolve({ error: new SError(`Property timeout: exceeded limit of ${timeMs} milliseconds`) });
			}, timeMs);
		})
	};
}
/** @internal */
function timeoutRunner(timeMs, nestedRun, value) {
	const t = timeoutAfter(timeMs);
	const runOut = nestedRun(value);
	if (runOut === null || !("then" in runOut)) {
		t.clear();
		return runOut;
	}
	const propRun = Promise.race([runOut, t.promise]);
	propRun.then(t.clear, t.clear);
	return propRun;
}
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
function timeout(timeMs) {
	return () => {
		return { decorateRun: (nestedRun) => (value) => timeoutRunner(timeMs, nestedRun, value) };
	};
}
//#endregion
//#region src/fast-check-default.ts
var fast_check_default_exports = /* @__PURE__ */ __exportAll({
	Arbitrary: () => Arbitrary,
	ExecutionStatus: () => ExecutionStatus,
	PreconditionFailure: () => PreconditionFailure,
	Random: () => Random,
	Stream: () => Stream,
	Value: () => Value,
	VerbosityLevel: () => VerbosityLevel,
	__commitHash: () => __commitHash,
	__type: () => __type,
	__version: () => __version,
	afterEach: () => afterEach,
	anything: () => anything,
	array: () => array,
	assert: () => assert,
	asyncDefaultReportMessage: () => asyncDefaultReportMessage,
	asyncModelRun: () => asyncModelRun,
	asyncProperty: () => asyncProperty,
	asyncStringify: () => asyncStringify,
	asyncToStringMethod: () => asyncToStringMethod,
	base64String: () => base64String,
	beforeEach: () => beforeEach,
	bigInt: () => bigInt,
	bigInt64Array: () => bigInt64Array,
	bigUint64Array: () => bigUint64Array,
	boolean: () => boolean,
	chainUntil: () => chainUntil,
	check: () => check,
	clone: () => clone,
	cloneIfNeeded: () => cloneIfNeeded,
	cloneMethod: () => cloneMethod,
	commands: () => commands,
	compareBooleanFunc: () => compareBooleanFunc,
	compareFunc: () => compareFunc,
	configureGlobal: () => configureGlobal,
	constant: () => constant,
	constantFrom: () => constantFrom,
	context: () => context,
	createDepthIdentifier: () => createDepthIdentifier,
	date: () => date,
	defaultReportMessage: () => defaultReportMessage,
	dictionary: () => dictionary,
	domain: () => domain,
	double: () => double,
	emailAddress: () => emailAddress,
	entityGraph: () => entityGraph,
	falsy: () => falsy,
	float: () => float,
	float32Array: () => float32Array,
	float64Array: () => float64Array,
	func: () => func,
	gen: () => gen,
	getDepthContextFor: () => getDepthContextFor,
	hasAsyncToStringMethod: () => hasAsyncToStringMethod,
	hasCloneMethod: () => hasCloneMethod,
	hasToStringMethod: () => hasToStringMethod,
	hash: () => hash,
	ignoreEqualValues: () => ignoreEqualValues,
	infiniteStream: () => infiniteStream,
	installGlobalPlugin: () => installGlobalPlugin,
	int16Array: () => int16Array,
	int32Array: () => int32Array,
	int8Array: () => int8Array,
	integer: () => integer,
	interruptAfterTimeLimit: () => interruptAfterTimeLimit,
	ipV4: () => ipV4,
	ipV4Extended: () => ipV4Extended,
	ipV6: () => ipV6,
	json: () => json,
	jsonValue: () => jsonValue,
	letrec: () => letrec,
	limitShrink: () => limitShrink,
	lorem: () => lorem,
	map: () => map,
	mapToConstant: () => mapToConstant,
	maxSafeInteger: () => maxSafeInteger,
	maxSafeNat: () => maxSafeNat,
	memo: () => memo,
	mixedCase: () => mixedCase,
	modelRun: () => modelRun,
	nat: () => nat,
	noBias: () => noBias,
	noShrink: () => noShrink,
	object: () => object,
	oneof: () => oneof,
	option: () => option,
	pre: () => pre,
	property: () => property,
	readConfigureGlobal: () => readConfigureGlobal,
	record: () => record,
	resetConfigureGlobal: () => resetConfigureGlobal,
	sample: () => sample,
	scheduledModelRun: () => scheduledModelRun,
	scheduler: () => scheduler,
	schedulerFor: () => schedulerFor,
	set: () => set,
	shuffledSubarray: () => shuffledSubarray,
	skipEqualValues: () => skipEqualValues,
	sparseArray: () => sparseArray,
	statistics: () => statistics,
	stream: () => stream,
	string: () => string,
	stringMatching: () => stringMatching,
	stringify: () => stringify,
	subarray: () => subarray,
	timeout: () => timeout,
	toStringMethod: () => toStringMethod,
	tuple: () => tuple,
	uint16Array: () => uint16Array,
	uint32Array: () => uint32Array,
	uint8Array: () => uint8Array,
	uint8ClampedArray: () => uint8ClampedArray,
	ulid: () => ulid,
	unbiased: () => unbiased,
	uniqueArray: () => uniqueArray,
	uuid: () => uuid,
	webAuthority: () => webAuthority,
	webFragments: () => webFragments,
	webPath: () => webPath,
	webQueryParameters: () => webQueryParameters,
	webSegment: () => webSegment,
	webUrl: () => webUrl
});
/**
* Type of module (commonjs or module)
* @remarks Since 1.22.0
* @public
*/
const __type = "commonjs";
/**
* Version of fast-check used by your project (eg.: "4.10.2")
* @remarks Since 1.22.0
* @public
*/
const __version = "4.10.2";
/**
* Commit hash of the current code (eg.: "c77afa8277a67250d798c52e61343b8ed5fd268b")
* @remarks Since 2.7.0
* @public
*/
const __commitHash = "c77afa8277a67250d798c52e61343b8ed5fd268b";
//#endregion
//#region src/fast-check.ts
/** @deprecated Prefer a namespace import instead: `import * as fc from 'fast-check'` */
var fast_check_default = fast_check_default_exports;
//#endregion
exports.Arbitrary = Arbitrary;
exports.ExecutionStatus = ExecutionStatus;
exports.PreconditionFailure = PreconditionFailure;
exports.Random = Random;
exports.Stream = Stream;
exports.Value = Value;
exports.VerbosityLevel = VerbosityLevel;
exports.__commitHash = __commitHash;
exports.__type = __type;
exports.__version = __version;
exports.afterEach = afterEach;
exports.anything = anything;
exports.array = array;
exports.assert = assert;
exports.asyncDefaultReportMessage = asyncDefaultReportMessage;
exports.asyncModelRun = asyncModelRun;
exports.asyncProperty = asyncProperty;
exports.asyncStringify = asyncStringify;
exports.asyncToStringMethod = asyncToStringMethod;
exports.base64String = base64String;
exports.beforeEach = beforeEach;
exports.bigInt = bigInt;
exports.bigInt64Array = bigInt64Array;
exports.bigUint64Array = bigUint64Array;
exports.boolean = boolean;
exports.chainUntil = chainUntil;
exports.check = check;
exports.clone = clone;
exports.cloneIfNeeded = cloneIfNeeded;
exports.cloneMethod = cloneMethod;
exports.commands = commands;
exports.compareBooleanFunc = compareBooleanFunc;
exports.compareFunc = compareFunc;
exports.configureGlobal = configureGlobal;
exports.constant = constant;
exports.constantFrom = constantFrom;
exports.context = context;
exports.createDepthIdentifier = createDepthIdentifier;
exports.date = date;
exports.default = fast_check_default;
exports.defaultReportMessage = defaultReportMessage;
exports.dictionary = dictionary;
exports.domain = domain;
exports.double = double;
exports.emailAddress = emailAddress;
exports.entityGraph = entityGraph;
exports.falsy = falsy;
exports.float = float;
exports.float32Array = float32Array;
exports.float64Array = float64Array;
exports.func = func;
exports.gen = gen;
exports.getDepthContextFor = getDepthContextFor;
exports.hasAsyncToStringMethod = hasAsyncToStringMethod;
exports.hasCloneMethod = hasCloneMethod;
exports.hasToStringMethod = hasToStringMethod;
exports.hash = hash;
exports.ignoreEqualValues = ignoreEqualValues;
exports.infiniteStream = infiniteStream;
exports.installGlobalPlugin = installGlobalPlugin;
exports.int16Array = int16Array;
exports.int32Array = int32Array;
exports.int8Array = int8Array;
exports.integer = integer;
exports.interruptAfterTimeLimit = interruptAfterTimeLimit;
exports.ipV4 = ipV4;
exports.ipV4Extended = ipV4Extended;
exports.ipV6 = ipV6;
exports.json = json;
exports.jsonValue = jsonValue;
exports.letrec = letrec;
exports.limitShrink = limitShrink;
exports.lorem = lorem;
exports.map = map;
exports.mapToConstant = mapToConstant;
exports.maxSafeInteger = maxSafeInteger;
exports.maxSafeNat = maxSafeNat;
exports.memo = memo;
exports.mixedCase = mixedCase;
exports.modelRun = modelRun;
exports.nat = nat;
exports.noBias = noBias;
exports.noShrink = noShrink;
exports.object = object;
exports.oneof = oneof;
exports.option = option;
exports.pre = pre;
exports.property = property;
exports.readConfigureGlobal = readConfigureGlobal;
exports.record = record;
exports.resetConfigureGlobal = resetConfigureGlobal;
exports.sample = sample;
exports.scheduledModelRun = scheduledModelRun;
exports.scheduler = scheduler;
exports.schedulerFor = schedulerFor;
exports.set = set;
exports.shuffledSubarray = shuffledSubarray;
exports.skipEqualValues = skipEqualValues;
exports.sparseArray = sparseArray;
exports.statistics = statistics;
exports.stream = stream;
exports.string = string;
exports.stringMatching = stringMatching;
exports.stringify = stringify;
exports.subarray = subarray;
exports.timeout = timeout;
exports.toStringMethod = toStringMethod;
exports.tuple = tuple;
exports.uint16Array = uint16Array;
exports.uint32Array = uint32Array;
exports.uint8Array = uint8Array;
exports.uint8ClampedArray = uint8ClampedArray;
exports.ulid = ulid;
exports.unbiased = unbiased;
exports.uniqueArray = uniqueArray;
exports.uuid = uuid;
exports.webAuthority = webAuthority;
exports.webFragments = webFragments;
exports.webPath = webPath;
exports.webQueryParameters = webQueryParameters;
exports.webSegment = webSegment;
exports.webUrl = webUrl;
