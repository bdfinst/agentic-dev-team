Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/utils/skipN.ts
function skipN(rng, num) {
	for (let idx = 0; idx !== num; ++idx) rng.next();
}
//#endregion
exports.skipN = skipN;
