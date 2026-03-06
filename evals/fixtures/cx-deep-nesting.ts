// FAIL: Functions with >4 levels of nesting (nested if/for/while)

interface DataRow {
  category: string;
  region: string;
  values: number[];
  active: boolean;
}

function aggregateByRegion(
  rows: DataRow[],
  targetCategories: string[],
  minValue: number
): Record<string, number[]> {
  const result: Record<string, number[]> = {};
  for (const row of rows) {
    if (row.active) {
      for (const category of targetCategories) {
        if (row.category === category) {
          if (!result[row.region]) {
            result[row.region] = [];
          }
          for (const value of row.values) {
            if (value >= minValue) {
              result[row.region].push(value);
            }
          }
        }
      }
    }
  }
  return result;
}

function findDuplicateEntries(matrix: string[][]): Array<[number, number]> {
  const duplicates: Array<[number, number]> = [];
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      for (let k = i; k < matrix.length; k++) {
        const startCol = k === i ? j + 1 : 0;
        for (let l = startCol; l < matrix[k].length; l++) {
          if (matrix[i][j] === matrix[k][l]) {
            duplicates.push([i, j]);
          }
        }
      }
    }
  }
  return duplicates;
}

function processNestedConfig(config: Record<string, any>): string[] {
  const warnings: string[] = [];
  for (const section of Object.keys(config)) {
    if (typeof config[section] === "object") {
      for (const key of Object.keys(config[section])) {
        if (Array.isArray(config[section][key])) {
          for (const item of config[section][key]) {
            if (typeof item === "string" && item.includes("deprecated")) {
              warnings.push(`${section}.${key} contains deprecated value`);
            }
          }
        }
      }
    }
  }
  return warnings;
}
