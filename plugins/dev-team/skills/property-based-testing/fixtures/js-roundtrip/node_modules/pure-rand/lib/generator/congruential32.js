Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/generator/congruential32.ts
const MULTIPLIER = 214013;
const INCREMENT = 2531011;
const MASK = 4294967295;
const MASK_2 = -2147483649;
const MULTIPLIER_2 = -1443076087;
const INCREMENT_2 = 505908858;
const MULTIPLIER_3 = 1170746341;
const INCREMENT_3 = -755606699;
const JUMP_MULTIPLIER = 1994129409;
const JUMP_INCREMENT = 916127744;
var LinearCongruential32 = class LinearCongruential32 {
	constructor(seed) {
		this.seed = seed;
	}
	clone() {
		return new LinearCongruential32(this.seed);
	}
	next() {
		const s0 = this.seed;
		const s1 = Math.imul(s0, MULTIPLIER) + INCREMENT | 0;
		const s2 = Math.imul(s0, MULTIPLIER_2) + INCREMENT_2 | 0;
		const s3 = Math.imul(s0, MULTIPLIER_3) + INCREMENT_3 | 0;
		this.seed = s3;
		const v1 = (s1 & MASK_2) >> 16;
		const v2 = (s2 & MASK_2) >> 16;
		return (s3 & MASK_2) >> 16 | v2 << 15 | v1 << 30;
	}
	jump() {
		this.seed = Math.imul(this.seed, JUMP_MULTIPLIER) + JUMP_INCREMENT & MASK;
	}
	getState() {
		return [this.seed];
	}
};
function congruential32FromState(state) {
	if (!(state.length === 1)) throw new Error("The state must have been produced by a congruential32 RandomGenerator");
	return new LinearCongruential32(state[0]);
}
function congruential32(seed) {
	return new LinearCongruential32(seed);
}
//#endregion
exports.congruential32 = congruential32;
exports.congruential32FromState = congruential32FromState;
