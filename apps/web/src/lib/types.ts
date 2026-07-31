/** API response shapes — keep in sync with apps/api/lore_api/schemas.py. */

export interface User {
  id: string;
  username: string;
  name: string;
  avatar_hue: number;
}

export type Role = "owner" | "editor" | "viewer";

export interface Workspace {
  id: string;
  name: string;
  icon: string | null;
  role: Role;
}

export interface Member {
  user_id: string;
  role: Role;
  name: string;
  username: string;
  avatar_hue: number;
}

export interface Invite {
  id: string;
  workspace_id: string;
  role: Role;
}

export interface InvitePreview {
  workspace_name: string;
  workspace_icon: string | null;
  role: Role;
}

export type PageKind = "doc" | "database" | "row";

export interface Page {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  title: string;
  icon: string | null;
  kind: PageKind;
  position: number;
  updated_at: string;
  deleted_at: string | null;
}

// --- databases ---

export type PropertyType =
  | "text"
  | "number"
  | "select"
  | "multi_select"
  | "date"
  | "checkbox"
  | "url"
  | "relation";

export interface SelectChoice {
  id: string;
  name: string;
  color: string;
}

export interface DbProperty {
  id: string;
  name: string;
  type: PropertyType;
  position: number;
  options: { choices?: SelectChoice[]; target?: string };
}

export type ViewType = "table" | "board" | "list" | "calendar";

export interface ViewFilter {
  prop: string;
  op: string;
  value?: unknown;
}

export interface ViewSort {
  prop: string;
  dir: "asc" | "desc";
}

export interface ViewConfig {
  group_by?: string;
  date_prop?: string;
  filters?: ViewFilter[];
  sorts?: ViewSort[];
  hidden?: string[];
}

export interface DbView {
  id: string;
  name: string;
  type: ViewType;
  position: number;
  config: ViewConfig;
}

export interface Database {
  page: Page;
  properties: DbProperty[];
  views: DbView[];
}

export interface CellValue {
  text?: string;
  number?: number;
  select?: string;
  multi_select?: string[];
  date?: { start: string; end?: string };
  checkbox?: boolean;
  url?: string;
  relation?: string[];
}

export interface DbRow {
  id: string;
  title: string;
  icon: string | null;
  position: number;
  updated_at: string;
  values: Record<string, CellValue>;
}

export interface Favorite {
  page_id: string;
  position: number;
}
