import { JumpableRandomGenerator } from "../types/JumpableRandomGenerator.js";

//#region src/generator/xoroshiro128plus.d.ts
declare function xoroshiro128plusFromState(state: readonly number[]): JumpableRandomGenerator;
declare function xoroshiro128plus(seed: number): JumpableRandomGenerator;
//#endregion
export { xoroshiro128plus, xoroshiro128plusFromState };