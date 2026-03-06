// PASS: Safe sorting and reversing — toSorted, toReversed, spread-copy patterns

interface Employee {
  id: number;
  name: string;
  department: string;
  salary: number;
  hireDate: string;
}

const sortByName = (employees: Employee[]): Employee[] =>
  employees.toSorted((a, b) => a.name.localeCompare(b.name));

const sortBySalaryDesc = (employees: Employee[]): Employee[] =>
  employees.toSorted((a, b) => b.salary - a.salary);

const sortByHireDate = (employees: Employee[]): Employee[] =>
  [...employees].sort(
    (a, b) => new Date(a.hireDate).getTime() - new Date(b.hireDate).getTime(),
  );

const reverseOrder = (employees: Employee[]): Employee[] =>
  employees.toReversed();

const topEarners = (employees: Employee[], count: number): Employee[] =>
  sortBySalaryDesc(employees).slice(0, count);

const sortByDepartmentThenName = (employees: Employee[]): Employee[] =>
  employees.toSorted((a, b) => {
    const deptCompare = a.department.localeCompare(b.department);
    return deptCompare !== 0 ? deptCompare : a.name.localeCompare(b.name);
  });

const sortNumbers = (values: number[]): number[] =>
  values.toSorted((a, b) => a - b);

const reverseStrings = (items: string[]): string[] =>
  items.toReversed();

const medianSalary = (employees: Employee[]): number => {
  const sorted = sortBySalaryDesc(employees);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1].salary + sorted[mid].salary) / 2
    : sorted[mid].salary;
};

const rankEmployees = (employees: Employee[]): (Employee & { rank: number })[] =>
  sortBySalaryDesc(employees).map((emp, index) => ({
    ...emp,
    rank: index + 1,
  }));

export {
  sortByName,
  sortBySalaryDesc,
  sortByHireDate,
  reverseOrder,
  topEarners,
  sortByDepartmentThenName,
  sortNumbers,
  reverseStrings,
  medianSalary,
  rankEmployees,
};
