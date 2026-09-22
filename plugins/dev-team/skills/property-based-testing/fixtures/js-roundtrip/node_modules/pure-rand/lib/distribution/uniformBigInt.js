Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/distribution/uniformBigInt.ts
const SBigInt = BigInt;
const NumValues = 4294967296n;
/**
* Uniformly generate random bigint values between `from` (included) and `to` (included)
*
* @param rng - Instance of RandomGenerator to extract random values from
* @param from - Lower bound of the range (included)
* @param to - Upper bound of the range (included)
*
* @public
*/
function uniformBigInt(rng, from, to) {
	const diff = to - from + 1n;
	let FinalNumValues = NumValues;
	let NumIterations = 1;
	while (FinalNumValues < diff) {
		FinalNumValues <<= 32n;
		++NumIterations;
	}
	let value = generateNext(NumIterations, rng);
	if (value < diff) return value + from;
	if (value + diff < FinalNumValues) return value % diff + from;
	const MaxAcceptedRandom = FinalNumValues - FinalNumValues % diff;
	while (value >= MaxAcceptedRandom) value = generateNext(NumIterations, rng);
	return value % diff + from;
}
function generateNext(NumIterations, rng) {
	let value = SBigInt(rng.next() + 2147483648);
	for (let num = 1; num < NumIterations; ++num) {
		const out = rng.next();
		value = (value << 32n) + SBigInt(out + 2147483648);
	}
	return value;
}
//#endregion
exports.uniformBigInt = uniformBigInt;
