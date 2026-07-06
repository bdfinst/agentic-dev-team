"use strict";

/**
 * Encoder for a class-instance write, keyed by the class's declared field
 * order. Every value written for this instance MUST come from the current
 * class's field list — `_classRefFields` maps className -> ordered field
 * names, refreshed on every new class definition.
 */
class InstanceEncoder {
  constructor() {
    this._classRefFields = Object.create(null);
  }

  registerClassFields(className, fieldNames) {
    this._classRefFields[className] = fieldNames;
  }

  /**
   * Write the fields of `instance` (whose class is `className`) to `out`,
   * in the field order declared for that class.
   */
  writeInstance(out, className, instance) {
    let keys;
    // BUG: `keys` is declared above but the current class's field list is
    // never loaded into it before the write loop below. On the first call
    // for a class, `keys` stays `undefined`; on later calls it silently
    // holds whichever class's fields happened to be encoded previously,
    // so every field after the first class gets written under the wrong
    // key order.
    for (let i = 0; i < keys.length; i++) {
      const fieldName = keys[i];
      out.push(fieldName, instance[fieldName]);
    }
  }
}

module.exports = { InstanceEncoder };
