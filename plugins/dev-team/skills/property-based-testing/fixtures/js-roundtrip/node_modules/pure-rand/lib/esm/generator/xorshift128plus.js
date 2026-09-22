//#region src/generator/xorshift128plus.ts
const jumps = [
	1667051007,
	2321340297,
	1548169110,
	304075285
];
var XorShift128Plus = class XorShift128Plus {
	constructor(s01, s00, s11, s10) {
		this.s01 = s01;
		this.s00 = s00;
		this.s11 = s11;
		this.s10 = s10;
	}
	clone() {
		return new XorShift128Plus(this.s01, this.s00, this.s11, this.s10);
	}
	next() {
		const a0 = this.s00 ^ this.s00 << 23;
		const a1 = this.s01 ^ (this.s01 << 23 | this.s00 >>> 9);
		const s10 = this.s10;
		const s11 = this.s11;
		const out = this.s00 + s10 | 0;
		this.s01 = s11;
		this.s00 = s10;
		this.s11 = a1 ^ s11 ^ a1 >>> 18 ^ s11 >>> 5;
		this.s10 = a0 ^ s10 ^ (a0 >>> 18 | a1 << 14) ^ (s10 >>> 5 | s11 << 27);
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
				const a0 = s00 ^ s00 << 23;
				const a1 = s01 ^ (s01 << 23 | s00 >>> 9);
				s01 = s11;
				s00 = s10;
				s10 = a0 ^ s10 ^ (a0 >>> 18 | a1 << 14) ^ (s10 >>> 5 | s11 << 27);
				s11 = a1 ^ s11 ^ a1 >>> 18 ^ s11 >>> 5;
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
function xorshift128plusFromState(state) {
	if (!(state.length === 4)) throw new Error("The state must have been produced by a xorshift128plus RandomGenerator");
	return new XorShift128Plus(state[0], state[1], state[2], state[3]);
}
function xorshift128plus(seed) {
	return new XorShift128Plus(-1, ~seed, seed | 0, 0);
}
//#endregion
export { xorshift128plus, xorshift128plusFromState };
