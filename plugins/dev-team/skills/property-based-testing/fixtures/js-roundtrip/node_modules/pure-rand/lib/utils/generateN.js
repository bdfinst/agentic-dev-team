Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/utils/generateN.ts
function generateN(rng, num) {
	const out = [];
	for (let idx = 0; idx !== num; ++idx) out.push(rng.next());
	return out;
}
//#endregion
exports.generateN = generateN;
