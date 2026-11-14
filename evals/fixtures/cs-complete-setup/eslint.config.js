import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/"] },
  { files: ["**/*.{ts,tsx}"], extends: [tseslint.configs.recommended] },
);
