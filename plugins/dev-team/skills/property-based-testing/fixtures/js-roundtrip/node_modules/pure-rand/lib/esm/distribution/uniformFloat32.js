//#region src/distribution/uniformFloat32.ts
const scale = 5.960464477539063e-8;
const mask = 16777215;
/**
* Uniformly generate random 32-bit floating point values between 0 (included) and 1 (excluded)
*
* @remarks Generated values are multiples of 2**-24, providing 24 bits of randomness.
*
* @param rng - Instance of RandomGenerator to extract random values from
*
* @public
*/
function uniformFloat32(rng) {
	return (rng.next() & mask) * scale;
}
//#endregion
export { uniformFloat32 };
