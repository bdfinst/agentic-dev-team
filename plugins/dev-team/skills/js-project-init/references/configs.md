# Configuration File Templates

Exact contents for each config file created by the js-project-init skill. Use these as-is unless the user requested customizations in Step 1.

## eslint.config.js

```js
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'

export default [
  js.configs.recommended,
  prettier,
  {
    rules: {
      // Functional style: no classes
      'no-restricted-syntax': [
        'error',
        {
          selector: 'ClassDeclaration',
          message: 'Use functions and closures instead of classes.',
        },
        {
          selector: 'ClassExpression',
          message: 'Use functions and closures instead of classes.',
        },
        {
          selector: 'ThisExpression',
          message: 'Avoid "this" — use closures and explicit parameters instead.',
        },
      ],

      // Immutability
      'prefer-const': 'error',
      'no-var': 'error',
      'no-param-reassign': 'error',

      // Clean code
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
      'no-console': 'warn',
    },
  },
  {
    ignores: ['node_modules/', 'dist/', 'build/', 'coverage/'],
  },
]
```

## prettier.config.js

```js
export default {
  semi: false,
  singleQuote: true,
  trailingComma: 'all',
  printWidth: 100,
  tabWidth: 2,
  useTabs: false,
  arrowParens: 'always',
  endOfLine: 'lf',
}
```

## .editorconfig

```ini
root = true

[*]
indent_style = space
indent_size = 2
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.md]
trim_trailing_whitespace = false
```

## .gitignore

```
# Dependencies
node_modules/

# Build output
dist/
build/

# Test coverage
coverage/

# Environment variables
.env
.env.*
!.env.example

# OS files
.DS_Store
Thumbs.db

# Editor directories
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log
npm-debug.log*
```

## vitest.config.js

```js
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.test.js'],
  },
})
```

## playwright.config.js (frontend projects only)

```js
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 0,
  use: {
    headless: true,
    baseURL: 'http://localhost:3000',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
})
```

## .husky/pre-push

```bash
npm run lint
npm run format:check
npm test
```

## src/index.js (starter file)

```js
/**
 * Add two numbers together.
 *
 * @param {number} a
 * @param {number} b
 * @returns {number} The sum of a and b
 */
export const add = (a, b) => a + b
```

## src/index.test.js (starter test)

```js
import { describe, it, expect } from 'vitest'
import { add } from './index.js'

describe('add', () => {
  it('adds two positive numbers', () => {
    expect(add(2, 3)).toBe(5)
  })

  it('handles zero', () => {
    expect(add(0, 5)).toBe(5)
  })

  it('handles negative numbers', () => {
    expect(add(-1, 1)).toBe(0)
  })
})
```

## e2e/example.spec.js (frontend projects only)

```js
import { test, expect } from '@playwright/test'

test('homepage loads', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/.+/)
})
```
