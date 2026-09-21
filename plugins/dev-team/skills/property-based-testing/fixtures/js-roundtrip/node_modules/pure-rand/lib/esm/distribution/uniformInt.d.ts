import { t as RandomGenerator } from "../RandomGenerator-DcXj09Ch.js";

//#region src/distribution/uniformInt.d.ts
/**
* Uniformly generate random integer values between `from` (included) and `to` (included)
*
* @param rng - Instance of RandomGenerator to extract random values from
* @param from - Lower bound of the range (included)
* @param to - Upper bound of the range (included)
*
* @public
*/
declare function uniformInt(rng: RandomGenerator, from: number, to: number): number;
//#endregion
export { uniformInt };