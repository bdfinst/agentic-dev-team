import { JumpableRandomGenerator } from "../types/JumpableRandomGenerator.js";

//#region src/generator/mersenne.d.ts
declare function mersenneFromState(state: readonly number[]): JumpableRandomGenerator;
declare function mersenne(seed: number): JumpableRandomGenerator;
//#endregion
export { mersenne, mersenneFromState };