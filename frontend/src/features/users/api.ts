import { api } from "../../lib/api";

export interface User {
  id: number;
  username: string;
  full_name: string | null;
  is_superuser: boolean;
  is_active: boolean;
  roles: string[];
  role_ids: number[];
  branch_ids: number[];
}

export interface Role {
  id: number;
  code: string;
  name: string;
  permissions: string[];
}

export interface Branch {
  id: number;
  name: string;
}

export async function listUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>("/api/v1/users");
  return data;
}

export async function createUser(payload: {
  username: string;
  password: string;
  full_name?: string;
  is_superuser?: boolean;
  role_ids: number[];
  branch_ids: number[];
}): Promise<User> {
  const { data } = await api.post<User>("/api/v1/users", payload);
  return data;
}

export async function updateUser(
  id: number,
  payload: {
    full_name?: string | null;
    is_superuser?: boolean;
    is_active?: boolean;
    role_ids?: number[];
    branch_ids?: number[];
  },
): Promise<User> {
  const { data } = await api.put<User>(`/api/v1/users/${id}`, payload);
  return data;
}

export async function resetPassword(id: number, password: string): Promise<User> {
  const { data } = await api.post<User>(`/api/v1/users/${id}/password`, { password });
  return data;
}

export async function listRoles(): Promise<Role[]> {
  const { data } = await api.get<Role[]>("/api/v1/roles");
  return data;
}

export async function listBranches(): Promise<Branch[]> {
  const { data } = await api.get<Branch[]>("/api/v1/branches");
  return data;
}
