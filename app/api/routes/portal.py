"""
Self-Service Portal API — used by the client portal page (/portal?token=...).

Device users authenticate with the device's agent_token (no JWT required).
Allows standard users to:
  - See their device info
  - Request admin access
  - Browse software catalog and request installs

GET  /portal/me                     — device + user info
GET  /portal/catalog                — software catalog
POST /portal/software-requests      — submit software request
GET  /portal/software-requests      — list requests for this device
POST /portal/admin-requests         — request admin access (wraps admin_access workflow)
GET  /portal/admin-requests         — list admin access requests for this device
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, DeviceUser, ScriptJob, SoftwareRequest, SoftwarePackage, AdminAccessRequest, Tenant, User
from app.core.deps import get_current_tenant, get_current_user, get_portal_session, PortalSession
from app.core.config import get_settings
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/portal")

# ---------------------------------------------------------------------------
# Software catalog — common enterprise apps with silent install pkg URLs
# ---------------------------------------------------------------------------
SOFTWARE_CATALOG = [
    {
        "id": "google-chrome",
        "name": "Google Chrome",
        "category": "Browser",
        "icon": "🌐",
        "description": "Fast, secure web browser by Google",
        "pkg_url": "https://dl.google.com/chrome/mac/universal/stable/gcem/googlechrome.dmg",
        "install_cmd": 'cd /tmp && curl -A "Mozilla/5.0" -L "https://dl.google.com/chrome/mac/stable/GGRO/googlechrome.dmg" -o chrome.dmg && hdiutil attach chrome.dmg -nobrowse -quiet && cp -R "/Volumes/Google Chrome/Google Chrome.app" /Applications/ && hdiutil detach "/Volumes/Google Chrome" -quiet && rm chrome.dmg',
    },
    {
        "id": "firefox",
        "name": "Mozilla Firefox",
        "category": "Browser",
        "icon": "🦊",
        "description": "Open source web browser by Mozilla",
        "pkg_url": "https://download.mozilla.org/?product=firefox-latest-ssl&os=osx&lang=en-US",
        "install_cmd": 'cd /tmp && curl -L "https://download.mozilla.org/?product=firefox-latest-ssl&os=osx&lang=en-US" -o firefox.dmg && hdiutil attach firefox.dmg -nobrowse -quiet && cp -R /Volumes/Firefox/Firefox.app /Applications/ && hdiutil detach /Volumes/Firefox -quiet && rm firefox.dmg',
    },
    {
        "id": "zoom",
        "name": "Zoom",
        "category": "Communication",
        "icon": "📹",
        "description": "Video conferencing and meetings",
        "pkg_url": "https://zoom.us/client/latest/Zoom.pkg",
        "install_cmd": 'cd /tmp && curl -L "https://zoom.us/client/latest/Zoom.pkg" -o zoom.pkg && installer -pkg zoom.pkg -target / && rm zoom.pkg',
    },
    {
        "id": "slack",
        "name": "Slack",
        "category": "Communication",
        "icon": "💬",
        "description": "Team messaging and collaboration",
        "pkg_url": "https://slack.com/downloads/mac",
        "install_cmd": 'cd /tmp && curl -L "https://downloads.slack-edge.com/desktop-releases/mac/x64/latest/Slack.dmg" -o slack.dmg && hdiutil attach slack.dmg -nobrowse -quiet && cp -R /Volumes/Slack/Slack.app /Applications/ && hdiutil detach /Volumes/Slack -quiet && rm slack.dmg',
    },
    {
        "id": "ms-teams",
        "name": "Microsoft Teams",
        "category": "Communication",
        "icon": "🟣",
        "description": "Microsoft Teams for collaboration",
        "pkg_url": "https://go.microsoft.com/fwlink/?linkid=2249065",
        "install_cmd": 'cd /tmp && curl -L "https://go.microsoft.com/fwlink/?linkid=2249065" -o teams.pkg && installer -pkg teams.pkg -target / && rm teams.pkg',
    },
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "category": "Development",
        "icon": "💻",
        "description": "Lightweight code editor by Microsoft",
        "pkg_url": "https://code.visualstudio.com/sha/download?build=stable&os=darwin-universal",
        "install_cmd": 'cd /tmp && curl -L "https://code.visualstudio.com/sha/download?build=stable&os=darwin-universal" -o vscode.zip && unzip -q vscode.zip -d /Applications/ && rm vscode.zip',
    },
    {
        "id": "1password",
        "name": "1Password",
        "category": "Security",
        "icon": "🔑",
        "description": "Password manager",
        "pkg_url": "https://downloads.1password.com/mac/1Password.pkg",
        "install_cmd": 'cd /tmp && curl -L "https://downloads.1password.com/mac/1Password.pkg" -o 1password.pkg && installer -pkg 1password.pkg -target / && rm 1password.pkg',
    },
    {
        "id": "office365",
        "name": "Microsoft Office 365",
        "category": "Productivity",
        "icon": "📊",
        "description": "Word, Excel, PowerPoint, Outlook",
        "pkg_url": "https://go.microsoft.com/fwlink/p/?linkid=2009112",
        "install_cmd": 'cd /tmp && curl -L "https://go.microsoft.com/fwlink/p/?linkid=2009112" -o office.pkg && installer -pkg office.pkg -target / && rm office.pkg',
    },
    {
        "id": "notion",
        "name": "Notion",
        "category": "Productivity",
        "icon": "📝",
        "description": "Notes, docs, and project management",
        "pkg_url": "https://www.notion.so/desktop/mac-universal/download",
        "install_cmd": 'cd /tmp && curl -L "https://www.notion.so/desktop/mac-universal/download" -o notion.dmg && hdiutil attach notion.dmg -nobrowse -quiet && cp -R "/Volumes/Notion/Notion.app" /Applications/ && hdiutil detach /Volumes/Notion -quiet && rm notion.dmg',
    },
]

# ---------------------------------------------------------------------------
# Auth — resolve device from portal session (Entra-authenticated user)
# ---------------------------------------------------------------------------

async def get_portal_device(
    session: PortalSession = Depends(get_portal_session),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    Find the enrolled device for the logged-in user.
    Matches by DeviceUser short_name or UPN prefix against enrolled devices
    in the user's tenant. Returns the most recently checked-in device.
    """
    settings = get_settings()
    # short_name is the local macOS username — typically the UPN prefix
    upn_prefix = session.upn.split("@")[0].lower()

    # Find device users matching this UPN
    du_result = await db.execute(
        select(DeviceUser).where(DeviceUser.short_name == upn_prefix)
    )
    device_users = du_result.scalars().all()

    if device_users:
        device_ids = [du.device_id for du in device_users]
        dev_result = await db.execute(
            select(Device).where(
                Device.id.in_(device_ids),
                Device.tenant_id == session.tenant_id,
                Device.status == "enrolled",
            ).order_by(Device.last_checkin.desc())
        )
        device = dev_result.scalars().first()
        if device:
            return device

    # Fallback: return first enrolled device in the tenant
    # (useful when device users haven't been refreshed yet)
    fallback = await db.execute(
        select(Device).where(
            Device.tenant_id == session.tenant_id,
            Device.status == "enrolled",
        ).order_by(Device.last_checkin.desc())
    )
    device = fallback.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="No enrolled device found for your account")
    return device


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SoftwareRequestCreate(BaseModel):
    software_id: str | None = None   # from catalog
    software_name: str | None = None  # custom
    software_pkg_url: str | None = None
    reason: str | None = None


class AdminRequestCreate(BaseModel):
    reason: str | None = None
    duration_hours: int = 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def portal_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Serve the self-service portal. Redirects to Entra login if not authenticated."""
    from app.core.security import decode_token
    from app.core.deps import PORTAL_COOKIE

    base_url = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto", "")
    host = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    if proto and host:
        base_url = f"{proto}://{host}"

    # Check for portal session cookie — redirect to login if missing/invalid
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        return RedirectResponse(f"{base_url}/api/v1/auth/portal/login?next={base_url}/api/v1/portal")
    try:
        payload = decode_token(token)
        if payload.get("role") != "portal":
            raise ValueError("not portal")
        session_email = payload.get("sub", "")
        session_name = payload.get("name", session_email)
    except Exception:
        response = RedirectResponse(f"{base_url}/api/v1/auth/portal/login?next={base_url}/api/v1/portal")
        response.delete_cookie(PORTAL_COOKIE, path="/")
        return response

    # Check for error param
    error_param = request.query_params.get("error", "")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>IT Self-Service Portal</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5f7;min-height:100vh}}
    .header{{background:#fff;border-bottom:1px solid #e5e5ea;padding:16px 24px;display:flex;align-items:center;justify-content:space-between}}
    .header h1{{font-size:16px;font-weight:600;color:#1d1d1f}}
    .header p{{font-size:12px;color:#8e8e93;margin-top:2px}}
    .tabs{{background:#fff;border-bottom:1px solid #e5e5ea;padding:0 24px;display:flex;gap:4px}}
    .tab{{padding:12px 16px;font-size:14px;font-weight:500;border-bottom:2px solid transparent;cursor:pointer;color:#8e8e93;background:none;border-top:none;border-left:none;border-right:none}}
    .tab.active{{border-bottom-color:#1d1d1f;color:#1d1d1f}}
    .content{{max-width:680px;margin:0 auto;padding:24px}}
    .card{{background:#fff;border:1px solid #e5e5ea;border-radius:12px;padding:20px;margin-bottom:16px}}
    .card h2{{font-size:14px;font-weight:600;color:#1d1d1f;margin-bottom:4px}}
    .card p{{font-size:13px;color:#8e8e93;margin-bottom:16px}}
    .catalog-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}}
    .catalog-item{{border:1px solid #e5e5ea;border-radius:10px;padding:12px;cursor:pointer;display:flex;align-items:center;gap:10px;background:#fff;text-align:left;transition:border-color .15s}}
    .catalog-item:hover{{border-color:#aaa;background:#fafafa}}
    .catalog-item.selected{{border-color:#1d1d1f;background:#f5f5f7}}
    .catalog-item .emoji{{font-size:24px}}
    .catalog-item .name{{font-size:13px;font-weight:500;color:#1d1d1f}}
    .catalog-item .desc{{font-size:11px;color:#8e8e93}}
    .category-label{{font-size:11px;font-weight:600;color:#8e8e93;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 6px}}
    input,textarea,select{{width:100%;border:1px solid #d1d1d6;border-radius:8px;padding:8px 12px;font-size:14px;font-family:inherit;outline:none}}
    input:focus,textarea:focus{{border-color:#1d1d1f}}
    textarea{{resize:none}}
    label{{display:block;font-size:12px;font-weight:500;color:#3c3c43;margin-bottom:4px;margin-top:12px}}
    .btn{{width:100%;background:#1d1d1f;color:#fff;border:none;border-radius:10px;padding:11px;font-size:14px;font-weight:500;cursor:pointer;margin-top:16px}}
    .btn:hover{{background:#333}}
    .btn:disabled{{opacity:.5;cursor:default}}
    .duration-row{{display:flex;gap:8px;margin-top:4px}}
    .dur-btn{{flex:1;border:1px solid #d1d1d6;border-radius:8px;padding:8px;font-size:13px;font-weight:500;cursor:pointer;background:#fff;color:#1d1d1f}}
    .dur-btn.selected{{background:#1d1d1f;color:#fff;border-color:#1d1d1f}}
    .badge{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:500;border:1px solid}}
    .badge-pending{{background:#fff9ec;color:#92550a;border-color:#f0c070}}
    .badge-approved{{background:#f0fdf4;color:#166534;border-color:#86efac}}
    .badge-rejected,.badge-denied{{background:#fef2f2;color:#991b1b;border-color:#fca5a5}}
    .badge-installing{{background:#eff6ff;color:#1e40af;border-color:#93c5fd}}
    .badge-completed{{background:#f0fdf4;color:#166534;border-color:#86efac}}
    .badge-failed{{background:#fef2f2;color:#991b1b;border-color:#fca5a5}}
    .request-row{{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid #f2f2f7}}
    .request-row:last-child{{border-bottom:none}}
    .toast{{position:fixed;top:16px;right:16px;background:#1d1d1f;color:#fff;padding:10px 16px;border-radius:10px;font-size:13px;z-index:99;display:none}}
    .error-card{{background:#fff;border:1px solid #fca5a5;border-radius:12px;padding:32px;text-align:center;margin:40px auto;max-width:400px}}
    .user-select{{font-size:13px;border:1px solid #d1d1d6;border-radius:8px;padding:6px 10px;background:#fff}}
    .hidden{{display:none}}
    .custom-input{{margin-top:12px;padding-top:12px;border-top:1px solid #f2f2f7}}
  </style>
</head>
<body>
<div id="toast" class="toast"></div>
<div id="app">
  <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;color:#8e8e93;font-size:14px">Loading…</div>
</div>

<script>
const API = "{base_url}";

let deviceInfo = null;
let catalog = [];
let selectedSoftware = null;
let selectedDuration = 4;
let activeTab = "software";

async function api(path, options={{}}) {{
  const r = await fetch(API + "/api/v1/portal" + path, {{
    ...options,
    credentials: "include",
    headers: {{"Content-Type": "application/json", ...(options.headers||{{}})}}
  }});
  if (r.status === 401) {{ window.location.href = API + "/api/v1/auth/portal/login"; return; }}
  if (!r.ok) {{ const e = await r.json().catch(()=>({{}})); throw new Error(e.detail || "HTTP " + r.status); }}
  return r.json();
}}

function toast(msg) {{
  const t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  setTimeout(()=>t.style.display="none", 4000);
}}

function badge(status) {{
  return `<span class="badge badge-${{status}}">${{status}}</span>`;
}}

function renderHeader() {{
  const user = deviceInfo?.users?.find(u=>u.short_name === getSelectedUser()) || deviceInfo?.users?.[0];
  const userOptions = (deviceInfo?.users||[]).map(u =>
    `<option value="${{u.short_name}}">${{u.full_name||u.short_name}}${{u.is_admin?" (admin)":""}}</option>`
  ).join("");
  return `
    <div class="header">
      <div>
        <h1>IT Self-Service Portal</h1>
        <p>${{deviceInfo?.hostname||"Your Mac"}} · ${{deviceInfo?.model||""}}</p>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        ${{userOptions ? `<select class="user-select" id="userSelect" onchange="render()">${{userOptions}}</select>` : ""}}
        <div style="text-align:right">
          <div style="font-size:12px;font-weight:600;color:#1d1d1f">{session_name}</div>
          <div style="font-size:11px;color:#8e8e93">{session_email}</div>
        </div>
        <a href="{base_url}/api/v1/auth/portal/logout"
           style="font-size:12px;color:#8e8e93;text-decoration:none;border:1px solid #e5e5ea;border-radius:6px;padding:4px 10px;white-space:nowrap"
           title="Sign out">Sign out</a>
      </div>
    </div>
    <div class="tabs">
      <button class="tab ${{activeTab==="software"?"active":""}}" onclick="setTab('software')">Request Software</button>
      <button class="tab ${{activeTab==="admin"?"active":""}}" onclick="setTab('admin')">Admin Access</button>
      <button class="tab ${{activeTab==="status"?"active":""}}" onclick="setTab('status')">My Requests</button>
    </div>`;
}}

function getSelectedUser() {{
  return document.getElementById("userSelect")?.value || deviceInfo?.users?.find(u=>!u.is_admin)?.short_name || deviceInfo?.users?.[0]?.short_name || "";
}}

function setTab(t) {{ activeTab = t; render(); }}

function renderCatalog() {{
  const categories = [...new Set(catalog.map(c=>c.category))];
  return categories.map(cat => `
    <div class="category-label">${{cat}}</div>
    <div class="catalog-grid">
      ${{catalog.filter(c=>c.category===cat).map(item=>`
        <button class="catalog-item ${{selectedSoftware?.id===item.id?"selected":""}}" onclick="selectSoftware('${{item.id}}')">
          <span class="emoji">${{item.icon}}</span>
          <div><div class="name">${{item.name}}</div><div class="desc">${{item.description}}</div></div>
        </button>`).join("")}}
    </div>`).join("");
}}

function selectSoftware(id) {{
  selectedSoftware = selectedSoftware?.id===id ? null : catalog.find(c=>c.id===id);
  document.getElementById("customSoftware").value = "";
  renderSelectedSoftware();
  // re-highlight
  document.querySelectorAll(".catalog-item").forEach(el => el.classList.remove("selected"));
  if (selectedSoftware) document.querySelectorAll(".catalog-item").forEach(el => {{
    if (el.querySelector(".name")?.textContent === selectedSoftware.name) el.classList.add("selected");
  }});
}}

function renderSelectedSoftware() {{
  const panel = document.getElementById("softwarePanel");
  const name = selectedSoftware?.name || document.getElementById("customSoftware")?.value;
  if (panel) panel.style.display = name ? "block" : "none";
  const title = document.getElementById("softwarePanelTitle");
  if (title) title.textContent = "Request: " + (name||"");
}}

async function submitSoftware() {{
  const user = getSelectedUser();
  const name = selectedSoftware?.name || document.getElementById("customSoftware")?.value;
  const reason = document.getElementById("softwareReason")?.value;
  if (!user) return toast("Select your username first");
  if (!name) return toast("Select or enter a software name");
  document.getElementById("submitSoftwareBtn").disabled = true;
  try {{
    await api("/software-requests", {{method:"POST", body: JSON.stringify({{
      requester_name: user,
      software_id: selectedSoftware?.id||undefined,
      software_name: selectedSoftware?undefined:name,
      reason: reason||undefined
    }})}});
    toast("Request submitted! An admin will review shortly.");
    selectedSoftware = null;
    document.getElementById("softwareReason").value = "";
    document.getElementById("customSoftware").value = "";
    await loadRequests(); render();
  }} catch(e) {{ toast(e.message); }}
  finally {{ const b = document.getElementById("submitSoftwareBtn"); if(b) b.disabled=false; }}
}}

async function submitAdmin() {{
  const user = getSelectedUser();
  const reason = document.getElementById("adminReason")?.value;
  if (!user) return toast("Select your username first");
  if (!reason) return toast("Please enter a reason");
  document.getElementById("submitAdminBtn").disabled = true;
  try {{
    await api("/admin-requests", {{method:"POST", body: JSON.stringify({{
      requester_name: user, reason, duration_hours: selectedDuration
    }})}});
    toast("Admin access request submitted! An admin will review shortly.");
    document.getElementById("adminReason").value = "";
    await loadRequests(); render();
  }} catch(e) {{ toast(e.message); }}
  finally {{ const b = document.getElementById("submitAdminBtn"); if(b) b.disabled=false; }}
}}

function setDuration(h) {{ selectedDuration = h; document.querySelectorAll(".dur-btn").forEach(b=>b.classList.toggle("selected", +b.dataset.h===h)); }}

let softwareRequests = [], adminRequests = [];
async function loadRequests() {{
  [softwareRequests, adminRequests] = await Promise.all([
    api("/software-requests").catch(()=>[]),
    api("/admin-requests").catch(()=>[]),
  ]);
  // Auto-refresh every 15s while installs are in progress
  const hasInstalling = softwareRequests.some(r=>r.status==="installing");
  if (hasInstalling) setTimeout(async()=>{{ await loadRequests(); if(activeTab==="status") render(); }}, 15000);
}}

function renderRequests() {{
  const sr = softwareRequests.map(r=>`
    <div class="request-row">
      <div><div style="font-size:14px;font-weight:500">${{r.software_name}}</div>
        ${{r.reason?`<div style="font-size:12px;color:#8e8e93">${{r.reason}}</div>`:""}}
        ${{r.status==="installing"?`<div style="font-size:12px;color:#1e40af">⏳ Installing on your Mac…</div>`:""}}
        ${{r.status==="completed"?`<div style="font-size:12px;color:#16a34a">✅ Installed successfully</div>`:""}}
        ${{r.status==="failed"?`<div style="font-size:12px;color:#dc2626">❌ Installation failed — contact IT</div>`:""}}
        <div style="font-size:11px;color:#c7c7cc">${{new Date(r.created_at).toLocaleString()}}</div>
      </div>${{badge(r.status)}}
    </div>`).join("") || "<p style='color:#8e8e93;font-size:13px'>No software requests yet.</p>";

  const ar = adminRequests.map(r=>`
    <div class="request-row">
      <div><div style="font-size:14px;font-weight:500">${{r.reason||"Admin access"}}</div>
        <div style="font-size:12px;color:#8e8e93">${{r.duration_hours}}h · ${{new Date(r.requested_at).toLocaleString()}}</div>
        ${{r.status==="approved"&&r.revoke_at?`<div style="font-size:12px;color:#16a34a;font-weight:500">Active until ${{new Date(r.revoke_at).toLocaleString()}}</div>`:""}}
      </div>${{badge(r.status)}}
    </div>`).join("") || "<p style='color:#8e8e93;font-size:13px'>No admin access requests yet.</p>";

  return `
    <div class="card"><h2>Software Requests</h2><div style="margin-top:8px">${{sr}}</div></div>
    <div class="card"><h2>Admin Access Requests</h2><div style="margin-top:8px">${{ar}}</div></div>`;
}}

function render() {{
  const app = document.getElementById("app");
  const durations = [1,2,4,8,24];
  app.innerHTML = renderHeader() + `<div class="content">` + (
    activeTab==="software" ? `
      <div class="card">
        <h2>Software Catalog</h2>
        <p>Select software to request installation on your Mac.</p>
        ${{renderCatalog()}}
        <div class="custom-input">
          <label>Not in the list? Enter software name:</label>
          <input id="customSoftware" placeholder="e.g. Adobe Photoshop" oninput="renderSelectedSoftware()"/>
        </div>
      </div>
      <div class="card" id="softwarePanel" style="display:${{selectedSoftware?"block":"none"}}">
        <h2 id="softwarePanelTitle">Request software</h2>
        <label>Reason (optional)</label>
        <textarea id="softwareReason" rows="2" placeholder="Why do you need this?"></textarea>
        <button class="btn" id="submitSoftwareBtn" onclick="submitSoftware()">Submit Request</button>
      </div>` :
    activeTab==="admin" ? `
      <div class="card">
        <h2>Request Admin Access</h2>
        <p>Temporary elevated privileges to install software or make system changes. Requires IT admin approval.</p>
        <label>Reason *</label>
        <textarea id="adminReason" rows="3" placeholder="e.g. Need to install Zoom for a client meeting"></textarea>
        <label>Duration</label>
        <div class="duration-row">
          ${{durations.map(h=>`<button class="dur-btn ${{selectedDuration===h?"selected":""}}" data-h="${{h}}" onclick="setDuration(${{h}})">${{h}}h</button>`).join("")}}
        </div>
        <button class="btn" id="submitAdminBtn" onclick="submitAdmin()">Request Admin Access</button>
      </div>` :
    renderRequests()
  ) + `</div>`;
}}

async function init() {{
  try {{
    [deviceInfo, catalog] = await Promise.all([api("/me"), api("/catalog")]);
    await loadRequests();
    render();
  }} catch(e) {{
    document.getElementById("app").innerHTML = `<div class="error-card"><div style="font-size:40px;margin-bottom:12px">⚠️</div><p style="font-weight:600;color:#dc2626">Unable to connect</p><p style="font-size:13px;color:#8e8e93;margin-top:6px">${{e.message}}</p></div>`;
  }}
}}

init();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/catalog")
async def get_catalog(
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    # Return uploaded packages first, then fall back to built-in catalog
    result = await db.execute(
        select(SoftwarePackage)
        .where(SoftwarePackage.tenant_id == device.tenant_id)
        .order_by(SoftwarePackage.uploaded_at.desc())
    )
    packages = result.scalars().all()

    items = []
    settings = get_settings()
    public_url = settings.mdm_server_url.rstrip("/")

    for pkg in packages:
        ext = pkg.pkg_type
        file_var = f"/tmp/install_{pkg.id[:8]}.{ext}"
        if ext == "pkg":
            install_cmd = f'curl -sL -H "Authorization: Bearer $AGENT_TOKEN" "{public_url}/api/v1/packages/{pkg.id}/download" -o {file_var} && installer -pkg {file_var} -target / && rm {file_var}'
        else:
            vol = pkg.name.replace('"', '')
            install_cmd = f'curl -sL -H "Authorization: Bearer $AGENT_TOKEN" "{public_url}/api/v1/packages/{pkg.id}/download" -o {file_var} && hdiutil attach {file_var} -nobrowse -quiet && cp -R "/Volumes/{vol}/{pkg.name}.app" /Applications/ && hdiutil detach "/Volumes/{vol}" -quiet && rm {file_var}'

        items.append({
            "id": f"pkg_{pkg.id}",
            "name": pkg.name,
            "category": "IT Managed",
            "icon": "📦",
            "description": f"{pkg.description or ''}{' · v' + pkg.version if pkg.version else ''}".strip(" ·"),
            "package_id": pkg.id,
        })

    # Append built-in catalog items (excluding any overridden by uploaded packages)
    uploaded_names = {p.name.lower() for p in packages}
    for item in SOFTWARE_CATALOG:
        if item["name"].lower() not in uploaded_names:
            items.append({k: v for k, v in item.items() if k != "install_cmd"})

    return items


@router.get("/me")
async def get_portal_me(
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    users_result = await db.execute(
        select(DeviceUser).where(DeviceUser.device_id == device.id)
    )
    users = users_result.scalars().all()
    return {
        "device_id": device.id,
        "hostname": device.hostname,
        "serial_number": device.serial_number,
        "model": device.model,
        "os_version": device.os_version,
        "users": [
            {"id": u.id, "short_name": u.short_name, "full_name": u.full_name, "is_admin": u.is_admin}
            for u in users
        ],
    }


@router.post("/software-requests", status_code=201)
async def create_software_request(
    body: SoftwareRequestCreate,
    session: PortalSession = Depends(get_portal_session),
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    # Resolve from catalog if software_id provided
    catalog_item = None
    if body.software_id:
        catalog_item = next((s for s in SOFTWARE_CATALOG if s["id"] == body.software_id), None)

    software_name = (catalog_item["name"] if catalog_item else body.software_name) or ""
    if not software_name:
        raise HTTPException(status_code=400, detail="software_name or software_id required")

    pkg_url = body.software_pkg_url or (catalog_item["pkg_url"] if catalog_item else None)

    requester_name = session.display_name or session.email
    req = SoftwareRequest(
        tenant_id=device.tenant_id,
        device_id=device.id,
        requester_name=requester_name,
        software_name=software_name,
        software_pkg_url=pkg_url,
        reason=body.reason,
        status="pending",
    )
    db.add(req)
    await db.flush()
    log.info("SoftwareRequest created: %s for device %s by %s", software_name, device.id, requester_name)

    from app.services.notifications import notify
    asyncio.create_task(notify("software_request_created", {
        "software_name": software_name,
        "requester_name": requester_name,
        "hostname": device.hostname,
        "reason": body.reason,
    }))

    return {"id": req.id, "status": "pending", "software_name": software_name}


@router.get("/software-requests")
async def list_software_requests(
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(SoftwareRequest)
        .where(SoftwareRequest.device_id == device.id)
        .order_by(SoftwareRequest.created_at.desc())
    )
    reqs = result.scalars().all()

    # Sync status from script jobs
    for r in reqs:
        if r.script_job_id and r.status == "installing":
            job_result = await db.execute(select(ScriptJob).where(ScriptJob.id == r.script_job_id))
            job = job_result.scalar_one_or_none()
            if job:
                if job.status == "completed" and job.exit_code == 0:
                    r.status = "completed"
                elif job.status == "failed" or (job.status == "completed" and job.exit_code != 0):
                    r.status = "failed"

    return [
        {
            "id": r.id,
            "software_name": r.software_name,
            "reason": r.reason,
            "status": r.status,
            "requester_name": r.requester_name,
            "created_at": r.created_at.isoformat(),
        }
        for r in reqs
    ]


@router.post("/admin-requests", status_code=201)
async def create_portal_admin_request(
    body: AdminRequestCreate,
    session: PortalSession = Depends(get_portal_session),
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    # Match device user by UPN prefix (macOS short_name) from the session
    upn_prefix = session.upn.split("@")[0].lower()
    user_result = await db.execute(
        select(DeviceUser).where(
            DeviceUser.device_id == device.id,
            DeviceUser.short_name == upn_prefix,
        )
    )
    device_user = user_result.scalar_one_or_none()
    if not device_user:
        raise HTTPException(
            status_code=404,
            detail=f"macOS user '{upn_prefix}' not found on this device. Ask your admin to run a UserList refresh."
        )

    if device_user.is_admin:
        raise HTTPException(status_code=400, detail="You already have admin access")

    if not 1 <= body.duration_hours <= 72:
        raise HTTPException(status_code=400, detail="duration_hours must be 1–72")

    req = AdminAccessRequest(
        tenant_id=device.tenant_id,
        device_id=device.id,
        device_user_id=device_user.id,
        requested_by_id=device_user.id,  # self-request
        reason=body.reason,
        duration_hours=body.duration_hours,
    )
    db.add(req)
    await db.flush()
    log.info("AdminAccessRequest (self) created for %s on device %s", session.upn, device.id)

    from app.services.notifications import notify
    asyncio.create_task(notify("admin_access_requested", {
        "username": session.display_name or session.upn,
        "hostname": device.hostname,
        "duration_hours": body.duration_hours,
        "reason": body.reason,
    }))

    return {"id": req.id, "status": "pending"}


@router.get("/admin-requests")
async def list_portal_admin_requests(
    device: Device = Depends(get_portal_device),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdminAccessRequest)
        .where(AdminAccessRequest.device_id == device.id)
        .order_by(AdminAccessRequest.requested_at.desc())
        .limit(20)
    )
    reqs = result.scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "reason": r.reason,
            "duration_hours": r.duration_hours,
            "requested_at": r.requested_at.isoformat(),
            "revoke_at": r.revoke_at.isoformat() if r.revoke_at else None,
        }
        for r in reqs
    ]


# ---------------------------------------------------------------------------
# Admin-side endpoints (JWT auth) — for the dashboard
# ---------------------------------------------------------------------------

@router.get("/admin/software-requests")
async def admin_list_software_requests(
    status: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    q = (
        select(SoftwareRequest)
        .options(selectinload(SoftwareRequest.device))
        .where(SoftwareRequest.tenant_id == tenant.id)
        .order_by(SoftwareRequest.created_at.desc())
    )
    if status:
        q = q.where(SoftwareRequest.status == status)
    result = await db.execute(q)
    reqs = result.scalars().all()
    return [
        {
            "id": r.id,
            "device_id": r.device_id,
            "device_hostname": r.device.hostname if r.device else None,
            "requester_name": r.requester_name,
            "software_name": r.software_name,
            "software_pkg_url": r.software_pkg_url,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in reqs
    ]


@router.post("/admin/software-requests/{request_id}/approve")
async def admin_approve_software_request(
    request_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SoftwareRequest).where(
            SoftwareRequest.id == request_id,
            SoftwareRequest.tenant_id == tenant.id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    req.status = "installing"
    req.reviewed_by_id = user.id

    # Resolve install command: uploaded package > built-in catalog > pkg URL
    settings = get_settings()
    public_url = settings.mdm_server_url.rstrip("/")

    # Get device agent token for authenticated download
    device_result = await db.execute(select(Device).where(Device.id == req.device_id))
    device = device_result.scalar_one_or_none()
    agent_token = device.agent_token if device else ""

    # Check uploaded packages first
    pkg_result = await db.execute(
        select(SoftwarePackage).where(
            SoftwarePackage.tenant_id == tenant.id,
            SoftwarePackage.name == req.software_name,
        ).order_by(SoftwarePackage.uploaded_at.desc()).limit(1)
    )
    uploaded_pkg = pkg_result.scalar_one_or_none()

    if uploaded_pkg:
        ext = uploaded_pkg.pkg_type
        file_var = f"/tmp/install_{uploaded_pkg.id[:8]}.{ext}"
        if ext == "pkg":
            install_cmd = f'curl -sL -H "Authorization: Bearer {agent_token}" "{public_url}/api/v1/packages/{uploaded_pkg.id}/download" -o {file_var} && installer -pkg {file_var} -target / && rm {file_var}'
        else:
            vol = uploaded_pkg.name.replace('"', '')
            install_cmd = f'curl -sL -H "Authorization: Bearer {agent_token}" "{public_url}/api/v1/packages/{uploaded_pkg.id}/download" -o {file_var} && hdiutil attach {file_var} -nobrowse -quiet && cp -R "/Volumes/{vol}/{uploaded_pkg.name}.app" /Applications/ && hdiutil detach "/Volumes/{vol}" -quiet && rm {file_var}'
    else:
        catalog_item = next((s for s in SOFTWARE_CATALOG if s["name"] == req.software_name), None)
        if catalog_item:
            install_cmd = catalog_item["install_cmd"]
        elif req.software_pkg_url:
            install_cmd = f'cd /tmp && curl -L "{req.software_pkg_url}" -o install.pkg && installer -pkg install.pkg -target / && rm install.pkg'
        else:
            raise HTTPException(status_code=400, detail="No install command or pkg URL available for this software")

    job = ScriptJob(
        tenant_id=tenant.id,
        device_id=req.device_id,
        command=install_cmd,
        label=f"install_{req.software_name.lower().replace(' ', '_')}",
        status="pending",
        created_by_id=user.id,
    )
    db.add(job)
    await db.flush()
    req.script_job_id = job.id
    log.info("SoftwareRequest %s approved, ScriptJob %s queued", req.id, job.id)
    return {"id": req.id, "status": req.status, "job_id": job.id}


@router.post("/admin/software-requests/{request_id}/reject")
async def admin_reject_software_request(
    request_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SoftwareRequest).where(
            SoftwareRequest.id == request_id,
            SoftwareRequest.tenant_id == tenant.id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = "rejected"
    req.reviewed_by_id = user.id
    return {"id": req.id, "status": "rejected"}
