import { t as RandomGenerator } from "../RandomGenerator-DcXj09Ch.js";

//#region src/distribution/uniformBigInt.d.ts
/**
* Uniformly generate random bigint values between `from` (included) and `to` (included)
*
* @param rng - Instance of RandomGenerator to extract random values from
* @param from - Lower bound of the range (included)
* @param to - Upper bound of the range (included)
*
* @public
*/
declare function uniformBigInt(rng: RandomGenerator, from: bigint, to: bigint): bigint;
//#endregion
export { uniformBigInt };