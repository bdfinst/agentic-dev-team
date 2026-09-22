Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/generator/mersenne.ts
const N = 624;
const M = 397;
const A = 2567483615;
const F = 1812433253;
const U = 11;
const S = 7;
const B = 2636928640;
const T = 15;
const C = 4022730752;
const L = 18;
const MASK_LOWER = 2147483647;
const MASK_UPPER = 2147483648;
const JUMP_COEFS = "SUSgbA\\W`E[]KN2RUSo8XVU?HKBFRl11E\\KoWOg5B]XEWG;BE;1:oVK[`B^Z9Qd23^XTnhL>]Unda4f[X;_j9H5QD=cN<5H`3bW>9bk1mjoI2fK0obmAAINOV:>Mek_V9dd<hZ\\gC3?Fm7FEk07QH_3PLm^@?^i\\QMkgP<]oLHmFnlecg5F@7U^@4jhZ?WZS0k@GHehmM36:5^9;>Hmm`co>k:KOSkSbIINb1VFf>LXgP>GUAQTD>Ci>XMGkUflLlb?_FaFUk@?5N7i70@;1o68ah@I<HFH7R2^J:G][Gf962ITWID9GWK8ElD2G5=DcHcL]cA]P2n7A=[<bInM;IHDQnJMReRXDWbVldnGEIPij`E08Xdci3@0c:IBbD4:Nk]?lEN9j^;T`0blZX7eiWE8c`<ak7j05FZi>AjUDh?M1B?^??FAXKThf<aBOXZf7jXYGK>R<;NHk3S9YhM7STJ6`:MIE`S@7298X8W>PNK=@;lLX<i\\TXLL<W@X[X54H]in8M;;n?kkQbajgAMY=Tf9b;ZKf0QUB2FHYWfnfkDoU9YkcLd95T>lK6GM1YL\\lid:J>KYS=iJ]Y>QlF>?R5_[5QeYC=66;A32Ac>OHk_ne^0g>bK:g;KFPgbGUcPR_Z=TX3H9d03bKZ2IhEPKBo>LSGWd0iFdV8C<Y:<>T[O6lC\\blaZ>GoAYP4clf^j1IfnZJ]QeDe2X<HE[LJNWnaCg[P]Co^:IRbWPY?97UePBlZNNHY6LOBM8P>=h?Ye:_f_Sb9Ki5GDYBF4dWeMfdg^ccPllNWM7G1\\UMdoYeOOD5^e@foA22G?ADYo5:FVG[bWo96;>3kc_c1Ab30>30;1@4F8g2hY?DJ4[LOL;ZLLKo2]jo>[KMDUcR279N_kF=3WL@Dd620bMTdA\\U9k``ef2iD9JgJ8CZBHS>F^Uk;<laeaeHS<15OSeS`PcSSKBRBFY]aQ=EgUXGNg=?d56`KA@2BejY0^[_DCX`L=CGMT=BW^6S1i@2ATBVk>3_ocRA>2U:4GPQ6o>5jX2HIcV3S@On6KB<[SKB?FC_AAji9agbBFkAi\\;4I\\UJ]c36Ub@[;gQACVGY<V]SDJBUU]La\\_a@JdOO8gm2T0DJMa:8Hf7>E]noQ[1Kambn??QQ]S?1i0oMGOijb\\aGY6lQ^CJ?9bFle8<eH4UUjBINX;n8@VOA5ah^URV49B[A?ONHhHAC1J5;;h0SXYlG^0W=eJdHh^K4SGe=1HZLLam;D<Q3AOdbPcdX``82\\jo0En8jRVGC73WMCF9`d:0heS?80?C188cSn7H9<daZ]MgS4Pb^1HkA:1PU^5>^h_g[RQV@PnYBRI_]`B]Bh@Uk03eXGY`I16L76H28X`R>IROMeNVUdU[:lghLhPCQZ:4a<30YBZCYnXe[?;jc8gKI2QH2MjnWBm4nGCZW`aVU2a;P<AMI25mlW_Nm][2?b6o851X@lAm]YZ`bWRF1g<Ga:T]1NXH5Veja5P9S9>:aNg:Th1Y=5o78K>LQ8hW@5S?I83Lk5Xk;j5@I3o[d:4RjE^oS30:WP9gC\\i8aSI>QRE@4lP:7lDg8g2`Ql[2I8aBU\\BQ?B4_clL9Q]S;^e1Ob5[>3JER2`c7B=o]fPOWO<DGi;Niba1PoWPPE_Q3aX0OB0mZej\\f_M[J4Y6]1`h2MkF[GiW8Q^d3^_=<I1N2Q7]2<2j[iP7V3V821FaI]A`93bC^Z\\G=WJ;^Ih?B97_iIF@\\Dl<eK1je8SNTWo_=XFMZH<<JYLZ^YQMPgYOV45K_:]kSI8^XlO0]GY=VUfe_C_F6TOcoAlVUH:o=WhhT@K`2KFhe<3\\KXQ>W:M?S_4S5d@J^`[AGA7@3]DnGSCO`\\?E8HT75^d9\\:m\\m1egIfk8cd6bD9\\eU8\\n[Pb0Cgd^S0n9kGJHb]i5XodlKHc34Fhi9K>0U5WK`>7Ff2^KL=WC6:kc?e5C^a1T1:4:^S5flXlGNIj08AfO?Dh7T7dWO>E]NI9?ob7B7P_h[4TEP[EU;GllFTnSmg9:\\[N]<SAoKP_kPlG56A:I3T6EG8Hj=XnUE`KT5U@OQ?]7[N^MFN1_NU4KO_3::Le`8IL9[1Z1H1;V3SC\\N3]S@4U[F2mhT5dYM7[4Pg_Na0_8WTH0`bgceQS8]EG;XgD4Ib4iLTP@kE79Mn>AYRJA1U5^Blhgno:aHVYc03c3J0Vc9FjEV^M75Zfd8kVC9>iJDk`AJ[6f7DK2D^DL\\AX:6b5h31XH;RQB\\N<ZSM=J;6L[`UW^eOIFc1Y]6_dfedIe4ARh72mTXC0WND_IDHVCZRDE0eODARCEETQI5TPUQE=jEH5bS?LP[ai`F5ABRYDo2o\\@=]GT?_9;hc4Lm:\\SF9k1T<0E@fX9BG[]g0nY7k[Qmi@la8`PF0j6@Q?Ii7bLkXQ<lLHf]`:DCh@9JY5>hEVLTdhL\\b1EB0lLh<=WaO@F<;8g<d:@e:LA:cFIEdmQh7hNHfSRToW?8N4:Z1K;XEDRO;OIDh<UdVln?bjgL>?VE98[B\\K<BVjkG8LiSX;fb>jf?DUK00Aih<WY6QD6cEnHBZ8iN_fd<G8Ci`11RUW2QlW]IXV:m?;J0GXXHfGNQ>:D`=fLPbO?VOTEYLj^cNj5PM>jKB5HVjJ4U7lXaTQNL9<@\\1`m\\Ug@VQHd7>jW=ca0`miF7;N0F=GjoQ`RFchKMGTmn8cF@Oh4GGCm7m2`U9j93Tb>=kSERjE_J939F01I1;`<ijk_=_Vn=7RVAI6fnQI5KlF:C44bN<<8K=Z<2TP<1]5?<dB>^LA=ebloE2Y2:9lkh0\\<YKbHD97iE`<C5oj^1>X:??`H6BXF2hG1Q[dF0Q=>W=J?7C\\k1T?<;R44oW?1hY^G8Zm]ZKnfOf0eCFYo6?=D8?<`6HU5SXh1;=:23LmV_FSi;OJfV<^?GkIDPISeHg1LaGE:V3Y3K3H<QJfbY?=;ldZRhnhQT_mGXDLFXXhSONE6Do_0iNZagB:BPGOTH;VhHUTd6LhQm^[;dO]5Hlkg<R:F<Kn\\:I:EGojgWZ2X@SYO_dlH;G8S<>oEKabY`:oU;=JW7ig?S?EYb86b7n8ce\\]IRa]koiWY<RfO;5kUI;7lVeC?[@ZaXDiF04B8R]bg@>O<mQDoUcBLcf^f>m2kMBUloD>Ze@NN^Z11TM`inXYhE_I=kA`:ZF4d\\>`L@;ZP[`ENU5cL[BV6\\Z?Di76:jg3hE6oG6jFc8kP=[GS1;WSedYQW1:U4\\OF32GgmMC<AjO]872bdBb`bKAA?8j78b>T3VfcUB2m4J^CPRU;8dScI]LU]^bBYA5_3:Y0N5i^?200000";
var MersenneTwister = class MersenneTwister {
	constructor(states, index) {
		this.states = states;
		this.index = index;
	}
	clone() {
		return new MersenneTwister(this.states.slice(), this.index);
	}
	next() {
		let y = this.states[this.index];
		y ^= y >>> U;
		y ^= y << S & B;
		y ^= y << T & C;
		y ^= y >>> L;
		this.index = twistedNext(this.states, this.index);
		return y;
	}
	getState() {
		return [this.index, ...this.states];
	}
	jump() {
		const originalStates = this.states.slice();
		const originalIndex = this.index;
		this.index = twistedNext(this.states, this.index);
		for (let i = 19932; i > 0; --i) {
			if (JUMP_COEFS.charCodeAt(i / 6 | 0) - 48 & 1 << i % 6) addState(this.states, this.index, originalStates, originalIndex);
			this.index = twistedNext(this.states, this.index);
		}
		addState(this.states, this.index, originalStates, originalIndex);
	}
};
function addState(mt, idx, originalMt, originalIdx) {
	let i = 0;
	if (originalIdx >= idx) {
		for (; i < N - originalIdx; i++) mt[i + idx] ^= originalMt[i + originalIdx];
		for (; i < N - idx; i++) mt[i + idx] ^= originalMt[i + originalIdx - N];
		for (; i < N; i++) mt[i + idx - N] ^= originalMt[i + originalIdx - N];
	} else {
		for (; i < N - idx; i++) mt[i + idx] ^= originalMt[i + originalIdx];
		for (; i < N - originalIdx; i++) mt[i + idx - N] ^= originalMt[i + originalIdx];
		for (; i < N; i++) mt[i + idx - N] ^= originalMt[i + originalIdx - N];
	}
}
function twistedNext(mt, idx) {
	if (idx < N - M) {
		const y = mt[idx] & MASK_UPPER | mt[idx + 1] & MASK_LOWER;
		mt[idx] = mt[idx + M] ^ y >>> 1 ^ -(y & 1) & A;
		return idx + 1;
	} else if (idx < N - 1) {
		const y = mt[idx] & MASK_UPPER | mt[idx + 1] & MASK_LOWER;
		mt[idx] = mt[idx + M - N] ^ y >>> 1 ^ -(y & 1) & A;
		return idx + 1;
	} else {
		const y = mt[idx] & MASK_UPPER | mt[0] & MASK_LOWER;
		mt[idx] = mt[M - 1] ^ y >>> 1 ^ -(y & 1) & A;
		return 0;
	}
}
function twist(mt) {
	for (let idx = 0; idx !== N; ++idx) twistedNext(mt, idx);
}
function mersenneFromState(state) {
	if (!(state.length === 625 && state[0] >= 0 && state[0] < N)) throw new Error("The state must have been produced by a mersenne RandomGenerator");
	return new MersenneTwister(state.slice(1), state[0]);
}
function mersenne(seed) {
	const out = [seed | 0];
	for (let idx = 1; idx !== N; ++idx) {
		const xored = out[idx - 1] ^ out[idx - 1] >>> 30;
		out.push(Math.imul(F, xored) + idx | 0);
	}
	twist(out);
	return new MersenneTwister(out, 0);
}
//#endregion
exports.mersenne = mersenne;
exports.mersenneFromState = mersenneFromState;
