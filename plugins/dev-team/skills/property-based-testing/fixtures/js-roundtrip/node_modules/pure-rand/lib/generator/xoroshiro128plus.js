Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/generator/xoroshiro128plus.ts
const jumps = [
	3639956645,
	3750757012,
	1261568508,
	386426335
];
var XoroShiro128Plus = class XoroShiro128Plus {
	constructor(s01, s00, s11, s10) {
		this.s01 = s01;
		this.s00 = s00;
		this.s11 = s11;
		this.s10 = s10;
	}
	clone() {
		return new XoroShiro128Plus(this.s01, this.s00, this.s11, this.s10);
	}
	next() {
		const out = this.s00 + this.s10 | 0;
		const a0 = this.s10 ^ this.s00;
		const a1 = this.s11 ^ this.s01;
		const s00 = this.s00;
		const s01 = this.s01;
		this.s00 = s00 << 24 ^ s01 >>> 8 ^ a0 ^ a0 << 16;
		this.s01 = s01 << 24 ^ s00 >>> 8 ^ a1 ^ (a1 << 16 | a0 >>> 16);
		this.s10 = a1 << 5 ^ a0 >>> 27;
		this.s11 = a0 << 5 ^ a1 >>> 27;
		return out;
	}
	jump() {
		let ns01 = 0;
		let ns00 = 0;
		let ns11 = 0;
		let ns10 = 0;
		let s01 = this.s01;
		let s00 = this.s00;
		let s11 = this.s11;
		let s10 = this.s10;
		for (let i = 0; i !== 4; ++i) {
			const ji = jumps[i];
			for (let mask = 1; mask; mask <<= 1) {
				if (ji & mask) {
					ns01 ^= s01;
					ns00 ^= s00;
					ns11 ^= s11;
					ns10 ^= s10;
				}
				const a0 = s10 ^ s00;
				const a1 = s11 ^ s01;
				const s00_ = s00;
				const s01_ = s01;
				s00 = s00_ << 24 ^ s01_ >>> 8 ^ a0 ^ a0 << 16;
				s01 = s01_ << 24 ^ s00_ >>> 8 ^ a1 ^ (a1 << 16 | a0 >>> 16);
				s10 = a1 << 5 ^ a0 >>> 27;
				s11 = a0 << 5 ^ a1 >>> 27;
			}
		}
		this.s01 = ns01;
		this.s00 = ns00;
		this.s11 = ns11;
		this.s10 = ns10;
	}
	getState() {
		return [
			this.s01,
			this.s00,
			this.s11,
			this.s10
		];
	}
};
function xoroshiro128plusFromState(state) {
	if (!(state.length === 4)) throw new Error("The state must have been produced by a xoroshiro128plus RandomGenerator");
	return new XoroShiro128Plus(state[0], state[1], state[2], state[3]);
}
function xoroshiro128plus(seed) {
	return new XoroShiro128Plus(-1, ~seed, seed | 0, 0);
}
//#endregion
exports.xoroshiro128plus = xoroshiro128plus;
exports.xoroshiro128plusFromState = xoroshiro128plusFromState;
