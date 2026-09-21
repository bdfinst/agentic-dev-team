import { t as RandomGenerator } from "../RandomGenerator-DcXj09Ch.js";
import { JumpableRandomGenerator } from "../types/JumpableRandomGenerator.js";

//#region src/utils/purify.d.ts
/**
* Transform an operation on a RandomGenerator into a pure version of it
* @param action - The transform operation to make pure
*/
declare function purify<TArgs extends unknown[], TReturn>(action: (rng: RandomGenerator, ...args: TArgs) => TReturn): (rng: RandomGenerator, ...args: TArgs) => [TReturn, RandomGenerator];
declare function purify<TArgs extends unknown[], TReturn>(action: (rng: JumpableRandomGenerator, ...args: TArgs) => TReturn): (rng: JumpableRandomGenerator, ...args: TArgs) => [TReturn, JumpableRandomGenerator];
//#endregion
export { purify };