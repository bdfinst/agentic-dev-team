import { JumpableRandomGenerator } from "../types/JumpableRandomGenerator.js";

//#region src/generator/congruential32.d.ts
declare function congruential32FromState(state: readonly number[]): JumpableRandomGenerator;
declare function congruential32(seed: number): JumpableRandomGenerator;
//#endregion
export { congruential32, congruential32FromState };