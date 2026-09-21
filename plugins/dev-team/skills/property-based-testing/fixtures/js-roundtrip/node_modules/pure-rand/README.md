<h1>
  <img src="https://raw.githubusercontent.com/dubzzz/pure-rand/main/assets/logo.svg" alt="pure-rand logo" />
</h1>

Fast Pseudorandom number generators (aka PRNG) with purity in mind!

[![Build Status](https://github.com/dubzzz/pure-rand/actions/workflows/build-status.yml/badge.svg?branch=main)](https://github.com/dubzzz/pure-rand/actions)
[![NPM Version](https://badge.fury.io/js/pure-rand.svg)](https://badge.fury.io/js/pure-rand)
[![Monthly Downloads](https://img.shields.io/npm/dm/pure-rand)](https://www.npmjs.com/package/pure-rand)

[![Codecov](https://codecov.io/gh/dubzzz/pure-rand/branch/main/graph/badge.svg)](https://codecov.io/gh/dubzzz/pure-rand)
[![Package Quality](https://packagequality.com/shield/pure-rand.svg)](https://packagequality.com/#?package=pure-rand)
[![Tested with fast-check](https://img.shields.io/badge/tested%20with-fast%E2%80%91check%20%F0%9F%90%92-%23282ea9?style=flat&logoSize=auto&labelColor=%231b1b1d)](https://fast-check.dev/)

[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/dubzzz/pure-rand/labels/good%20first%20issue)
[![License](https://img.shields.io/npm/l/pure-rand.svg)](https://github.com/dubzzz/pure-rand/blob/main/LICENSE)
[![Share on Bluesky](https://img.shields.io/badge/share%20on-Bluesky-0285FF?logo=bluesky&logoColor=white)](https://bsky.app/intent/compose?text=pure-rand%20%E2%80%94%20fast%20and%20pure%20pseudorandom%20number%20generators%20for%20JS%2FTS.%20Perfect%20for%20reproducible%20randomness!%20%F0%9F%8E%B2%0A%0Ahttps%3A%2F%2Fgithub.com%2Fdubzzz%2Fpure-rand%0A%0Aby%20%40nicolas.dubien.me)

## Getting started

**Install it in node via:**

`npm install pure-rand` or `yarn add pure-rand`

## Usage

**Simple usage**

```javascript
import { uniformInt } from 'pure-rand/distribution/uniformInt';
import { xoroshiro128plus } from 'pure-rand/generator/xoroshiro128plus';

const seed = 42;
const rng = xoroshiro128plus(seed);
const firstDiceValue = uniformInt(rng, 1, 6); // value in {1..6}, here: 2
const secondDiceValue = uniformInt(rng, 1, 6); // value in {1..6}, here: 4
const thirdDiceValue = uniformInt(rng, 1, 6); // value in {1..6}, here: 6
```

**Pure usage**

Pure means that the instance `rng` will never be altered in-place. It can be called again and again and it will always return the same value. But it will also return the next `rng`. Here is an example showing how the code above can be translated into its pure version:

```javascript
import { uniformIntDistribution } from 'pure-rand/distribution/UniformIntDistribution';
import { xoroshiro128plus } from 'pure-rand/generator/xoroshiro128plus';
import { purify } from 'pure-rand/utils/purify';

const uniformIntDistributionPure = purify(uniformIntDistribution);

const seed = 42;
const rng1 = xoroshiro128plus(seed);
const [firstDiceValue, rng2] = uniformIntDistributionPure(rng1, 1, 6); // value in {1..6}, here: 2
const [secondDiceValue, rng3] = uniformIntDistributionPure(rng2, 1, 6); // value in {1..6}, here: 4
const [thirdDiceValue, rng4] = uniformIntDistributionPure(rng3, 1, 6); // value in {1..6}, here: 6

// You can call: uniformIntDistributionPure(rng1, 1, 6);
// over and over it will always give you back the same value along with a new rng (always producing the same values too).
```

**Independent simulations**

In order to produce independent simulations it can be tempting to instanciate several PRNG based on totally different seeds. While it would produce distinct set of values, the best way to ensure fully unrelated sequences is rather to use jumps. Jump just consists into moving far away from the current position in the generator (eg.: jumping in Xoroshiro 128+ will move you 2<sup>64</sup> generations away from the current one on a generator having a sequence of 2<sup>128</sup> elements).

```javascript
import { uniformInt } from 'pure-rand/distribution/uniformInt';
import { xoroshiro128plus } from 'pure-rand/generator/xoroshiro128plus';
import { purify } from 'pure-rand/utils/purify';

const pureJump = purify((rng) => rng.jump());
const createAnotherSimulation = (rng) => pureJump(rng)[1];

const seed = 42;
const rngSimulation1 = xoroshiro128plus(seed);
const rngSimulation2 = createAnotherSimulation(rngSimulation1); // not in-place, creates a new instance
const rngSimulation3 = createAnotherSimulation(rngSimulation2); // not in-place, creates a new instance

const diceSim1Value = uniformInt(rngSimulation1, 1, 6); // value in {1..6}, here: 2
const diceSim2Value = uniformInt(rngSimulation2, 1, 6); // value in {1..6}, here: 5
const diceSim3Value = uniformInt(rngSimulation3, 1, 6); // value in {1..6}, here: 6
```

**Non-uniform usage**

While not recommended as non-uniform distribution implies that one or several values from the range will be more likely than others, it might be tempting for people wanting to maximize the throughput.

```javascript
import { xoroshiro128plus } from 'pure-rand/generator/xoroshiro128plus';

const seed = 42;
const rng = xoroshiro128plus(seed);
const rand = (min, max) => {
  const out = (rng.next() >>> 0) / 0x100000000;
  return min + Math.floor(out * (max - min + 1));
};
const firstDiceValue = rand(1, 6); // value in {1..6}, here: 6
```

**Select your seed**

While not perfect, here is a rather simple way to generate a seed for your PNRG.

```javascript
const seed = Date.now() ^ (Math.random() * 0x100000000);
```

## Documentation

### Pseudorandom number generators

In computer science most random number generators<sup>(1)</sup> are [pseudorandom number generators](https://en.wikipedia.org/wiki/Pseudorandom_number_generator) (abbreviated: PRNG). In other words, they are fully deterministic and given the original seed one can rebuild the whole sequence.

Each PRNG algorithm has to deal with tradeoffs in terms of randomness quality, speed, length of the sequence<sup>(2)</sup>... In other words, it's important to compare relative speed of libraries with that in mind. Indeed, a Mersenne Twister PRNG will not have the same strenghts and weaknesses as a Xoroshiro PRNG, so depending on what you need exactly you might prefer one PRNG over another even if it will be slower.

4 PRNGs come with pure-rand:

- `congruential32`: Linear Congruential generator — \[[more](https://en.wikipedia.org/wiki/Linear_congruential_generator)\]
- `mersenne`: Mersenne Twister generator — \[[more](https://en.wikipedia.org/wiki/Mersenne_Twister)\]
- `xorshift128plus`: Xorshift 128+ generator — \[[more](https://en.wikipedia.org/wiki/Xorshift)\]
- `xoroshiro128plus`: Xoroshiro 128+ generator — \[[more](https://en.wikipedia.org/wiki/Xorshift)\]

Our recommendation is `xoroshiro128plus`. But if you want to use another one, you can replace it by any other PRNG provided by pure-rand in the examples above.

Each of these generators come with its own import: `pure-rand/generator/<name>`.

### Distributions

Once you are able to generate random values, next step is to scale them into the range you want. Indeed, you probably don't want a floating point value between 0 (included) and 1 (excluded) but rather an integer value between 1 and 6 if you emulate a dice or any other range based on your needs.

At this point, simple way would be to do `min + floor(random() * (max - min + 1))` but actually it will not generate the values with equal probabilities even if you use the best PRNG in the world to back `random()`. In order to have equal probabilities you need to rely on uniform distributions<sup>(3)</sup> which comes built-in in some PNRG libraries.

pure-rand provides 4 built-in functions for uniform distributions of values:

- `uniformInt(rng, min, max)`
- `uniformBigInt(rng, min, max)` - with `min` and `max` being `bigint`
- `uniformFloat32(rng)` - to generate value between 0 (included) and 1 (excluded)
- `uniformFloat64(rng)` - to generate value between 0 (included) and 1 (excluded)

Each of these distributions come with its own import: `pure-rand/distribution/<name>`.

### Extra helpers

Some helpers are also provided in order to ease the use of `RandomGenerator` instances:

- `generateN(rng: RandomGenerator, num: number): number[]`: generates `num` random values using `rng` and return them
- `skipN(rng: RandomGenerator, num: number): void`: skips `num` random values

And one last helper responsible to change any function accepting an instance of `RandomGenerator` as a first argument into a pure version of it:

- `purify<TArgs extends unknown[], TReturn>(action: (rng: RandomGenerator, ...args: TArgs) => TReturn): (rng: RandomGenerator, ...args: TArgs) => [TReturn, RandomGenerator]`: purifies the action

Each of these helpers come with its own import: `pure-rand/utils/<name>`.

## Comparison

pure-rand offers competitive performance compared to other PRNG libraries, with built-in support for uniform distributions — ensuring unbiased results out of the box.

<img src="https://raw.githubusercontent.com/dubzzz/pure-rand/main/assets/comparison.svg" alt="Comparison against other libraries" />

For detailed benchmark results and methodology, see the [full comparison](./COMPARISON.md).

---

(1) — Not all as there are also [hardware-based random number generator](https://en.wikipedia.org/wiki/Hardware_random_number_generator).

(2) — How long it takes to reapeat itself?

(3) — While most users don't really think of it, uniform distribution is key! Without it entries might be biased towards some values and make some others less probable. The naive `rand() % numValues` is a good example of biased version as if `rand()` is uniform in `0, 1, 2` and `numValues` is `2`, the probabilities are: `P(0) = 67%`, `P(1) = 33%` causing `1` to be less probable than `0`
