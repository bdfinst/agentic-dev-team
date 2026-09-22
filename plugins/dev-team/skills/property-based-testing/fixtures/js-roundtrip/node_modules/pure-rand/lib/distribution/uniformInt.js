Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/distribution/internals/uniformIntInternal.ts
/**
* Uniformly generate number in range [0 ; rangeSize[
* With rangeSize <= 0x100000000
* @internal
*/
function uniformIntInternal(rng, rangeSize) {
	const MaxAllowed = rangeSize > 2 ? ~~(4294967296 / rangeSize) * rangeSize : 4294967296;
	let deltaV = rng.next() + 2147483648;
	while (deltaV >= MaxAllowed) deltaV = rng.next() + 2147483648;
	return deltaV % rangeSize;
}
//#endregion
//#region src/distribution/internals/ArrayInt64.ts
/**
* We only accept safe integers here
* @internal
*/
function fromNumberToArrayInt64(out, n) {
	if (n < 0) {
		const posN = -n;
		out.sign = -1;
		out.data[0] = ~~(posN / 4294967296);
		out.data[1] = posN >>> 0;
	} else {
		out.sign = 1;
		out.data[0] = ~~(n / 4294967296);
		out.data[1] = n >>> 0;
	}
	return out;
}
/**
* Substract two ArrayInt of 64 bits on 64 bits.
* With arrayIntA - arrayIntB >= 0
* @internal
*/
function substractArrayInt64(out, arrayIntA, arrayIntB) {
	const lowA = arrayIntA.data[1];
	const highA = arrayIntA.data[0];
	const signA = arrayIntA.sign;
	const lowB = arrayIntB.data[1];
	const highB = arrayIntB.data[0];
	const signB = arrayIntB.sign;
	out.sign = 1;
	if (signA === 1 && signB === -1) {
		const low = lowA + lowB;
		const high = highA + highB + (low > 4294967295 ? 1 : 0);
		out.data[0] = high >>> 0;
		out.data[1] = low >>> 0;
		return out;
	}
	let lowFirst = lowA;
	let highFirst = highA;
	let lowSecond = lowB;
	let highSecond = highB;
	if (signA === -1) {
		lowFirst = lowB;
		highFirst = highB;
		lowSecond = lowA;
		highSecond = highA;
	}
	let reminderLow = 0;
	let low = lowFirst - lowSecond;
	if (low < 0) {
		reminderLow = 1;
		low = low >>> 0;
	}
	out.data[0] = highFirst - highSecond - reminderLow;
	out.data[1] = low;
	return out;
}
//#endregion
//#region src/distribution/internals/uniformArrayIntInternal.ts
/**
* Uniformly generate ArrayInt64 in range [0 ; rangeSize[
*
* @remarks
* In the worst case scenario it may discard half of the randomly generated value.
* Worst case being: most significant number is 1 and remaining part evaluates to 0.
*
* @internal
*/
function uniformArrayIntInternal(rng, out, rangeSize) {
	const maxIndex0 = rangeSize[0] + 1;
	out[0] = uniformIntInternal(rng, maxIndex0);
	out[1] = uniformIntInternal(rng, 4294967296);
	while (out[0] >= rangeSize[0] && (out[0] !== rangeSize[0] || out[1] >= rangeSize[1])) {
		out[0] = uniformIntInternal(rng, maxIndex0);
		out[1] = uniformIntInternal(rng, 4294967296);
	}
	return out;
}
//#endregion
//#region src/distribution/uniformInt.ts
const safeNumberMaxSafeInteger = Number.MAX_SAFE_INTEGER;
const sharedA = {
	sign: 1,
	data: [0, 0]
};
const sharedB = {
	sign: 1,
	data: [0, 0]
};
const sharedC = {
	sign: 1,
	data: [0, 0]
};
const sharedData = [0, 0];
function uniformLargeIntInternal(rng, from, to, rangeSize) {
	const rangeSizeArrayIntValue = rangeSize <= safeNumberMaxSafeInteger ? fromNumberToArrayInt64(sharedC, rangeSize) : substractArrayInt64(sharedC, fromNumberToArrayInt64(sharedA, to), fromNumberToArrayInt64(sharedB, from));
	if (rangeSizeArrayIntValue.data[1] === 4294967295) {
		rangeSizeArrayIntValue.data[0] += 1;
		rangeSizeArrayIntValue.data[1] = 0;
	} else rangeSizeArrayIntValue.data[1] += 1;
	uniformArrayIntInternal(rng, sharedData, rangeSizeArrayIntValue.data);
	return sharedData[0] * 4294967296 + sharedData[1] + from;
}
/**
* Uniformly generate random integer values between `from` (included) and `to` (included)
*
* @param rng - Instance of RandomGenerator to extract random values from
* @param from - Lower bound of the range (included)
* @param to - Upper bound of the range (included)
*
* @public
*/
function uniformInt(rng, from, to) {
	const rangeSize = to - from;
	if (rangeSize <= 4294967295) return uniformIntInternal(rng, rangeSize + 1) + from;
	return uniformLargeIntInternal(rng, from, to, rangeSize);
}
//#endregion
exports.uniformInt = uniformInt;
