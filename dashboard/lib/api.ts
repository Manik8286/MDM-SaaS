const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://192.168.64.1";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("mdm_token");
}

export function setToken(token: string) {
  localStorage.setItem("mdm_token", token);
}

export function clearToken() {
  localStorage.removeItem("mdm_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export async function login(email: string, password: string) {
  return request<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// Devices
export async function getDevices() {
  return request<Device[]>("/devices");
}

export async function getDevice(id: string) {
  return request<Device>(`/devices/${id}`);
}

export async function lockDevice(id: string, pin?: string, message?: string) {
  return request<{ command_uuid: string }>(`/devices/${id}/lock`, {
    method: "POST",
    body: JSON.stringify({ pin, message }),
  });
}

export async function eraseDevice(id: string, pin: string = "") {
  return request<{ command_uuid: string }>(`/devices/${id}/erase`, {
    method: "POST",
    body: JSON.stringify({ pin }),
  });
}

export async function restartDevice(id: string) {
  return request<{ command_uuid: string }>(`/devices/${id}/restart`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function queryDevice(id: string) {
  return request<{ command_uuid: string }>(`/devices/${id}/query`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// Audit
export async function getAuditLogs(params?: { resource_type?: string; action?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.resource_type) qs.set("resource_type", params.resource_type);
  if (params?.action) qs.set("action", params.action);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString() ? `?${qs}` : "";
  return request<AuditLog[]>(`/audit${q}`);
}

// Tenant
export async function getTenant() {
  return request<TenantInfo>("/tenant");
}

export async function updateTenant(data: Partial<TenantUpdate>) {
  return request<TenantInfo>("/tenant", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// Profiles
export async function getProfiles() {
  return request<Profile[]>("/profiles");
}

export async function createProfile(data: CreateProfileInput) {
  return request<Profile>("/profiles", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function pushProfile(id: string) {
  return request<{ queued: number; command_uuids: string[] }>(`/profiles/${id}/push`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function pushPsso(options: PssoOptions) {
  return request<{ queued: number; command_uuids: string[] }>("/profiles/psso", {
    method: "POST",
    body: JSON.stringify(options),
  });
}

// Enrollment
export async function createEnrollmentToken(platform: string = "macos", reusable: boolean = false, expires_in_hours: number = 72) {
  return request<EnrollmentToken>("/enrollment/tokens", {
    method: "POST",
    body: JSON.stringify({ platform, reusable, expires_in_hours }),
  });
}

// Device users
export async function getDeviceUsers(id: string) {
  return request<DeviceUser[]>(`/devices/${id}/users`);
}
export async function refreshDeviceUsers(id: string) {
  return request<{ command_uuid: string }>(`/devices/${id}/users/refresh`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// Patch management
export async function getDeviceApps(id: string) {
  return request<InstalledApp[]>(`/devices/${id}/patch/apps`);
}
export async function getDeviceUpdates(id: string) {
  return request<DeviceUpdate[]>(`/devices/${id}/patch/updates`);
}
export async function getDeviceCompliance(id: string) {
  return request<ComplianceStatus>(`/devices/${id}/patch/compliance`);
}
export async function scanDevice(id: string, force = false) {
  return request<{ queued: number; command_uuids: string[] }>(`/devices/${id}/patch/scan`, {
    method: "POST",
    body: JSON.stringify({ force }),
  });
}
export async function installUpdates(id: string, product_keys: string[], install_action = "InstallLater") {
  return request<{ command_uuid: string }>(`/devices/${id}/patch/install`, {
    method: "POST",
    body: JSON.stringify({ product_keys, install_action }),
  });
}

// Types
export interface Device {
  id: string;
  udid: string;
  platform: string;
  serial_number: string | null;
  model: string | null;
  os_version: string | null;
  hostname: string | null;
  status: string;
  psso_status: string;
  compliance_status: string;
  enrolled_at: string | null;
  last_checkin: string | null;
}

export interface DeviceUser {
  id: string;
  short_name: string;
  full_name: string | null;
  is_admin: boolean;
  is_logged_in: boolean;
  has_secure_token: boolean;
  last_seen_at: string;
}

export interface InstalledApp {
  name: string;
  bundle_id: string | null;
  version: string | null;
  short_version: string | null;
  source: string | null;
  last_seen_at: string;
}

export interface DeviceUpdate {
  product_key: string;
  human_readable_name: string | null;
  version: string | null;
  build: string | null;
  is_critical: boolean;
  restart_required: boolean;
  last_seen_at: string;
}

export interface ComplianceStatus {
  compliance_status: string;
  compliance_checked_at: string | null;
  is_encrypted: boolean | null;
  is_supervised: boolean | null;
  critical_update_count: number;
  total_update_count: number;
  total_app_count: number;
}

export interface Profile {
  id: string;
  name: string;
  type: string;
  platform: string;
  status: string;
  created_at: string;
}

export interface CreateProfileInput {
  name: string;
  type: string;
  platform: string;
  payload: Record<string, unknown>;
}

export interface PssoOptions {
  auth_method: string;
  enable_create_user_at_login: boolean;
  registration_token?: string;
  admin_groups?: string[];
}

export interface AuditLog {
  id: string;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  changes: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface TenantInfo {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  apns_push_topic: string | null;
  entra_tenant_id: string | null;
  entra_client_id: string | null;
}

export interface TenantUpdate {
  name?: string;
  apns_push_topic?: string;
  entra_tenant_id?: string;
  entra_client_id?: string;
}

export interface EnrollmentToken {
  token: string;
  platform: string;
  reusable: boolean;
  expires_at: string | null;
  enrollment_url: string;
}
