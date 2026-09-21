import { t as RandomGenerator } from "../RandomGenerator-DcXj09Ch.js";

//#region src/types/JumpableRandomGenerator.d.ts
interface JumpableRandomGenerator extends RandomGenerator {
  /** Produce a fully independent clone of the current instance */
  clone(): JumpableRandomGenerator;
  /**
  * Jump current generator
  *
  * Move the generator forward by an extremely large number of steps in its sequence.
  * This is typically a number so large that it would be infeasible to reach by repeated `next()` calls.
  */
  jump(): void;
}
//#endregion
export { JumpableRandomGenerator };