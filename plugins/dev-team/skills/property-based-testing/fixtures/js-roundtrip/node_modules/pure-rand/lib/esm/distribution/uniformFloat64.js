//#region src/distribution/uniformFloat64.ts
const scale26 = 1.4901161193847656e-8;
const scale53 = 11102230246251565e-32;
const mask1 = 67108863;
const mask2 = 134217727;
/**
* Uniformly generate random 64-bit floating point values between 0 (included) and 1 (excluded)
*
* @remarks Generated values are multiples of 2**-53, providing 53 bits of randomness.
*
* @param rng - Instance of RandomGenerator to extract random values from
*
* @public
*/
function uniformFloat64(rng) {
	const value1 = rng.next() & mask1;
	const value2 = rng.next() & mask2;
	return value1 * scale26 + value2 * scale53;
}
//#endregion
export { uniformFloat64 };
