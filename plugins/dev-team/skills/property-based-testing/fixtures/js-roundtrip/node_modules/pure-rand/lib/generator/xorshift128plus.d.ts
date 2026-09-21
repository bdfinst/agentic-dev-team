import { JumpableRandomGenerator } from "../types/JumpableRandomGenerator.js";

//#region src/generator/xorshift128plus.d.ts
declare function xorshift128plusFromState(state: readonly number[]): JumpableRandomGenerator;
declare function xorshift128plus(seed: number): JumpableRandomGenerator;
//#endregion
export { xorshift128plus, xorshift128plusFromState };