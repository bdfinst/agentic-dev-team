//#region src/utils/skipN.ts
function skipN(rng, num) {
	for (let idx = 0; idx !== num; ++idx) rng.next();
}
//#endregion
export { skipN };
