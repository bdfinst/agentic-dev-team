import { t as RandomGenerator } from "../RandomGenerator-DcXj09Ch.js";

//#region src/distribution/uniformFloat64.d.ts
/**
* Uniformly generate random 64-bit floating point values between 0 (included) and 1 (excluded)
*
* @remarks Generated values are multiples of 2**-53, providing 53 bits of randomness.
*
* @param rng - Instance of RandomGenerator to extract random values from
*
* @public
*/
declare function uniformFloat64(rng: RandomGenerator): number;
//#endregion
export { uniformFloat64 };