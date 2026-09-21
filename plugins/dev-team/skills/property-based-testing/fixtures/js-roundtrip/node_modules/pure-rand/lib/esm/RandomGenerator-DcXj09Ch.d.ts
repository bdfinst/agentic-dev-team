//#region src/types/RandomGenerator.d.ts
interface RandomGenerator {
  /** Produce a fully independent clone of the current instance */
  clone(): RandomGenerator;
  /**
  * Generate next value BUT alters current generator.
  * Values uniform in range -0x8000_0000 (included) to 0x7fff_ffff (included)
  */
  next(): number;
  /** Access to the internal state of a RandomGenerator in a read-only fashion */
  getState(): readonly number[];
}
//#endregion
export { RandomGenerator as t };