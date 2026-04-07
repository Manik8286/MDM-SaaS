const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://192.168.64.1";

function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  return localStorage.getItem("mdm_api_url") || DEFAULT_API_BASE;
}

export function setApiUrl(url: string) {
  localStorage.setItem("mdm_api_url", url);
}

export function getApiUrl(): string {
  return getApiBase();
}

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
  const res = await fetch(`${getApiBase()}/api/v1${path}`, {
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

// Policies
export async function pushUsbBlock() {
  return request<{ queued: number; command_uuids: string[] }>("/profiles/usb-block/push", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function pushGatekeeper(allow_identified_developers: boolean = true) {
  return request<{ queued: number; command_uuids: string[] }>("/profiles/gatekeeper/push", {
    method: "POST",
    body: JSON.stringify({ allow_identified_developers }),
  });
}
export async function pushUsbBlockDevice(deviceId: string) {
  return request<{ queued: number; command_uuids: string[] }>(`/profiles/usb-block/push/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function removeUsbBlockDevice(deviceId: string) {
  return request<{ queued: number; command_uuids: string[] }>(`/profiles/usb-block/remove/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function pushPssoDevice(deviceId: string, authMethod: string = "UserSecureEnclaveKey") {
  return request<{ queued: number; command_uuid: string }>(`/profiles/psso/push/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({ auth_method: authMethod, enable_create_user_at_login: true }),
  });
}
export async function pushIcloudBlockDevice(deviceId: string) {
  return request<{ queued: number; command_uuid: string }>(`/profiles/icloud-block/push/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function removeIcloudBlockDevice(deviceId: string) {
  return request<{ queued: number; command_uuid: string }>(`/profiles/icloud-block/remove/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function pushOneDriveKfmDevice(deviceId: string) {
  return request<{ queued: number; command_uuid: string }>(`/profiles/onedrive-kfm/push/${deviceId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// Software Requests (admin dashboard)
export async function getSoftwareRequests(status?: string) {
  const q = status ? `?status=${status}` : "";
  return request<SoftwareRequestItem[]>(`/portal/admin/software-requests${q}`);
}
export async function approveSoftwareRequest(id: string) {
  return request<SoftwareRequestItem>(`/portal/admin/software-requests/${id}/approve`, { method: "POST", body: JSON.stringify({}) });
}
export async function rejectSoftwareRequest(id: string) {
  return request<SoftwareRequestItem>(`/portal/admin/software-requests/${id}/reject`, { method: "POST", body: JSON.stringify({}) });
}

export interface SoftwareRequestItem {
  id: string;
  device_id: string;
  device_hostname: string | null;
  requester_name: string;
  software_name: string;
  software_pkg_url: string | null;
  reason: string | null;
  status: string;
  created_at: string;
}

// Agent
export async function getAgentToken(deviceId: string) {
  return request<{ device_id: string; agent_token: string; server_url: string; bootstrap_url: string }>(
    `/devices/${deviceId}/agent-token`
  );
}

// Admin Access
export async function getAdminAccessRequests(status?: string) {
  const q = status ? `?status=${status}` : "";
  return request<AdminAccessRequest[]>(`/admin-access/requests${q}`);
}
export async function createAdminAccessRequest(data: { device_id: string; device_user_id: string; reason?: string; duration_hours?: number }) {
  return request<AdminAccessRequest>("/admin-access/requests", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
export async function approveAdminAccess(id: string) {
  return request<AdminAccessRequest>(`/admin-access/requests/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function denyAdminAccess(id: string) {
  return request<AdminAccessRequest>(`/admin-access/requests/${id}/deny`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function revokeAdminAccess(id: string) {
  return request<AdminAccessRequest>(`/admin-access/requests/${id}/revoke`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// Software Packages
export async function getPackages() {
  return request<SoftwarePackageItem[]>("/packages");
}
export async function uploadPackage(formData: FormData) {
  const token = typeof window !== "undefined" ? localStorage.getItem("mdm_token") : null;
  const res = await fetch(`${getApiUrl()}/api/v1/packages`, {
    method: "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<SoftwarePackageItem>;
}
export async function deletePackage(id: string) {
  return request<void>(`/packages/${id}`, { method: "DELETE" });
}
export function packageDownloadUrl(id: string): string {
  return `${getApiUrl()}/api/v1/packages/${id}/download`;
}

export interface SoftwarePackageItem {
  id: string;
  name: string;
  version: string | null;
  description: string | null;
  filename: string;
  file_size: number | null;
  pkg_type: string;
  uploaded_at: string;
}

// Compliance
export async function getComplianceSummary() {
  return request<FleetSummary>("/compliance/summary");
}
export async function getCompliancePolicies() {
  return request<CompliancePolicy[]>("/compliance/policies");
}
export async function getDeviceCompliance2(deviceId: string) {
  return request<DeviceComplianceSummary>(`/compliance/devices/${deviceId}`);
}
export async function evaluatePolicy(policyId: string) {
  return request<{ evaluated: number; policy: string }>(`/compliance/policies/${policyId}/evaluate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
export async function createCompliancePolicy(data: CreatePolicyInput2) {
  return request<CompliancePolicy>("/compliance/policies", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
export async function updateCompliancePolicy(id: string, data: Partial<CreatePolicyInput2> & { is_active?: boolean }) {
  return request<CompliancePolicy>(`/compliance/policies/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}
export async function deleteCompliancePolicy(id: string) {
  return request<void>(`/compliance/policies/${id}`, { method: "DELETE" });
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

export interface PolicyRules {
  filevault_required: boolean;
  firewall_required: boolean;
  gatekeeper_required: boolean;
  max_checkin_age_hours: number;
  critical_updates_allowed: number;
  psso_required: boolean;
  screen_lock_required: boolean;
}

export interface CompliancePolicy {
  id: string;
  name: string;
  framework: string;
  description: string | null;
  rules: PolicyRules;
  is_active: boolean;
  created_at: string;
}

export interface ComplianceResult {
  id: string;
  device_id: string;
  policy_id: string;
  status: string;
  passing: string[];
  failing: string[];
  unknown: string[];
  checked_at: string;
}

export interface DeviceComplianceSummary {
  device_id: string;
  hostname: string | null;
  serial_number: string | null;
  overall_status: string;
  policy_results: ComplianceResult[];
}

export interface FleetSummary {
  total_devices: number;
  compliant: number;
  non_compliant: number;
  unknown: number;
  policies: CompliancePolicy[];
}

export interface AdminAccessRequest {
  id: string;
  device_id: string;
  device_user_id: string;
  requested_by_id: string;
  approved_by_id: string | null;
  status: string;
  reason: string | null;
  duration_hours: number;
  requested_at: string;
  decided_at: string | null;
  revoke_at: string | null;
  revoked_at: string | null;
  device_hostname: string | null;
  device_serial: string | null;
  username: string | null;
  is_currently_admin: boolean | null;
  elevation_command: string | null;
}

export interface CreatePolicyInput2 {
  name: string;
  framework: string;
  description?: string;
  rules: PolicyRules;
}
