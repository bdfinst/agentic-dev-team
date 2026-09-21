Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
//#region src/utils/purify.ts
function purify(action) {
	return (rng, ...args) => {
		const clonedRng = rng.clone();
		return [action(clonedRng, ...args), clonedRng];
	};
}
//#endregion
exports.purify = purify;
