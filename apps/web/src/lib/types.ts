/** API response shapes — keep in sync with apps/api/lore_api/schemas.py. */

export interface User {
  id: string;
  email: string;
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
  email: string;
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

export interface Page {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  title: string;
  icon: string | null;
  position: number;
  updated_at: string;
  deleted_at: string | null;
}

export interface Favorite {
  page_id: string;
  position: number;
}
