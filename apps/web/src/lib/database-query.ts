import type {
  CellValue,
  DbProperty,
  DbRow,
  PropertyType,
  ViewFilter,
  ViewSort,
} from "./types";

/** Client-side view evaluation: filters (ANDed) then sorts. Workspaces at v1
 * scale fit comfortably in memory; the server stays a dumb value store. */

export const FILTER_OPS: Record<PropertyType, { op: string; label: string; needsValue: boolean }[]> = {
  text: [
    { op: "contains", label: "contains", needsValue: true },
    { op: "not_contains", label: "does not contain", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
    { op: "not_empty", label: "is not empty", needsValue: false },
  ],
  url: [
    { op: "contains", label: "contains", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
    { op: "not_empty", label: "is not empty", needsValue: false },
  ],
  number: [
    { op: "eq", label: "=", needsValue: true },
    { op: "neq", label: "≠", needsValue: true },
    { op: "gt", label: ">", needsValue: true },
    { op: "lt", label: "<", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
  ],
  select: [
    { op: "is", label: "is", needsValue: true },
    { op: "is_not", label: "is not", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
  ],
  multi_select: [
    { op: "has", label: "contains", needsValue: true },
    { op: "not_has", label: "does not contain", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
  ],
  date: [
    { op: "is", label: "is", needsValue: true },
    { op: "before", label: "is before", needsValue: true },
    { op: "after", label: "is after", needsValue: true },
    { op: "empty", label: "is empty", needsValue: false },
  ],
  checkbox: [
    { op: "checked", label: "is checked", needsValue: false },
    { op: "unchecked", label: "is unchecked", needsValue: false },
  ],
  relation: [
    { op: "empty", label: "is empty", needsValue: false },
    { op: "not_empty", label: "is not empty", needsValue: false },
  ],
};

function isEmpty(value: CellValue | undefined, type: PropertyType): boolean {
  if (!value) return true;
  switch (type) {
    case "text":
      return !value.text?.trim();
    case "url":
      return !value.url?.trim();
    case "number":
      return value.number === undefined || value.number === null;
    case "select":
      return !value.select;
    case "multi_select":
      return !value.multi_select || value.multi_select.length === 0;
    case "date":
      return !value.date?.start;
    case "checkbox":
      return value.checkbox === undefined;
    case "relation":
      return !value.relation || value.relation.length === 0;
  }
}

function matches(row: DbRow, filter: ViewFilter, prop: DbProperty): boolean {
  const value = row.values[prop.id];
  const day = (iso: string | undefined) => (iso ?? "").slice(0, 10);
  switch (filter.op) {
    case "empty":
      return isEmpty(value, prop.type);
    case "not_empty":
      return !isEmpty(value, prop.type);
    case "contains": {
      const haystack = (prop.type === "url" ? value?.url : value?.text) ?? "";
      return haystack.toLowerCase().includes(String(filter.value ?? "").toLowerCase());
    }
    case "not_contains":
      return !(value?.text ?? "").toLowerCase().includes(String(filter.value ?? "").toLowerCase());
    case "eq":
      return value?.number === Number(filter.value);
    case "neq":
      return value?.number !== Number(filter.value);
    case "gt":
      return value?.number !== undefined && value.number > Number(filter.value);
    case "lt":
      return value?.number !== undefined && value.number < Number(filter.value);
    case "is":
      if (prop.type === "date") return day(value?.date?.start) === String(filter.value);
      return value?.select === filter.value;
    case "is_not":
      return value?.select !== filter.value;
    case "has":
      return (value?.multi_select ?? []).includes(String(filter.value));
    case "not_has":
      return !(value?.multi_select ?? []).includes(String(filter.value));
    case "before":
      return !!value?.date?.start && day(value.date.start) < String(filter.value);
    case "after":
      return !!value?.date?.start && day(value.date.start) > String(filter.value);
    case "checked":
      return value?.checkbox === true;
    case "unchecked":
      return value?.checkbox !== true;
    default:
      return true;
  }
}

function sortKey(row: DbRow, prop: DbProperty | undefined): string | number {
  if (!prop) return row.title.toLowerCase(); // "title" pseudo-property
  const value = row.values[prop.id];
  switch (prop.type) {
    case "number":
      return value?.number ?? Number.NEGATIVE_INFINITY;
    case "date":
      return value?.date?.start ?? "";
    case "checkbox":
      return value?.checkbox ? 1 : 0;
    case "select": {
      // Sort selects by their configured choice order, not alphabetically.
      const idx = (prop.options.choices ?? []).findIndex((c) => c.id === value?.select);
      return idx === -1 ? Number.MAX_SAFE_INTEGER : idx;
    }
    case "multi_select":
      return (value?.multi_select ?? []).length;
    case "url":
      return value?.url?.toLowerCase() ?? "";
    case "relation":
      return (value?.relation ?? []).length;
    default:
      return value?.text?.toLowerCase() ?? "";
  }
}

export function applyView(
  rows: DbRow[],
  properties: DbProperty[],
  filters: ViewFilter[] | undefined,
  sorts: ViewSort[] | undefined
): DbRow[] {
  const byId = new Map(properties.map((p) => [p.id, p]));
  let out = rows;
  if (filters?.length) {
    out = out.filter((row) =>
      filters.every((f) => {
        if (f.prop === "title") {
          const t = row.title.toLowerCase();
          const needle = String(f.value ?? "").toLowerCase();
          if (f.op === "contains") return t.includes(needle);
          if (f.op === "not_contains") return !t.includes(needle);
          if (f.op === "empty") return t.trim() === "";
          if (f.op === "not_empty") return t.trim() !== "";
          return true;
        }
        const prop = byId.get(f.prop);
        return prop ? matches(row, f, prop) : true;
      })
    );
  }
  if (sorts?.length) {
    out = [...out].sort((a, b) => {
      for (const s of sorts) {
        const prop = s.prop === "title" ? undefined : byId.get(s.prop);
        const ka = sortKey(a, prop);
        const kb = sortKey(b, prop);
        if (ka < kb) return s.dir === "asc" ? -1 : 1;
        if (ka > kb) return s.dir === "asc" ? 1 : -1;
      }
      return a.position - b.position;
    });
  }
  return out;
}
