"""
Generate high-level architecture diagram for MDM SaaS.
Produces: scripts/arch_diagram.png  (high-res, 3200x2000)
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe

# ── Canvas ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(20, 13))
ax.set_xlim(0, 20)
ax.set_ylim(0, 13)
ax.axis('off')
fig.patch.set_facecolor('#0F172A')
ax.set_facecolor('#0F172A')

# ── Color palette ─────────────────────────────────────────────────────────────
C = {
    'bg':        '#0F172A',
    'panel':     '#1E293B',
    'blue':      '#1D4ED8',
    'blue_lt':   '#3B82F6',
    'green':     '#059669',
    'orange':    '#EA580C',
    'purple':    '#7C3AED',
    'teal':      '#0F766E',
    'yellow':    '#D97706',
    'white':     '#F8FAFC',
    'gray':      '#94A3B8',
    'gray_lt':   '#CBD5E1',
    'border':    '#334155',
    'arrow':     '#475569',
    'apns_bg':   '#064E3B',
    'apple_bg':  '#1E1B4B',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, color, alpha=0.95, radius=0.35, lw=1.5, edgecolor=None):
    ec = edgecolor or color
    b = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0.0,rounding_size={radius}",
                       facecolor=color, edgecolor=ec,
                       linewidth=lw, alpha=alpha, zorder=3)
    ax.add_patch(b)
    return b

def header_box(ax, x, y, w, h, hdr_color, body_color, title, icon='',
               title_size=11, body_items=None, body_size=8.5):
    """Box with colored header bar + body items."""
    hdr_h = 0.55
    # header
    box(ax, x, y + h - hdr_h, w, hdr_h, hdr_color, radius=0.3,
        edgecolor=hdr_color)
    # body
    box(ax, x, y, w, h - hdr_h, body_color, radius=0.3,
        edgecolor=hdr_color, lw=1.5)
    # title text
    ax.text(x + w/2, y + h - hdr_h/2, f'{icon}  {title}',
            ha='center', va='center', fontsize=title_size,
            color='white', fontweight='bold', zorder=5)
    # body items
    if body_items:
        step = (h - hdr_h - 0.15) / max(len(body_items), 1)
        for i, item in enumerate(body_items):
            ty = y + h - hdr_h - 0.22 - i * step
            ax.text(x + 0.18, ty, f'• {item}',
                    ha='left', va='center', fontsize=body_size,
                    color=C['gray_lt'], zorder=5)

def arrow(ax, x1, y1, x2, y2, color='#475569', lw=1.8,
          label='', label_color='#94A3B8', bidirect=False):
    style = '->' if not bidirect else '<->'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style,
                                color=color, lw=lw,
                                connectionstyle='arc3,rad=0.0'),
                zorder=4)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx, my + 0.15, label, ha='center', va='bottom',
                fontsize=7.5, color=label_color, zorder=6,
                fontstyle='italic')

def curved_arrow(ax, x1, y1, x2, y2, color='#475569', lw=1.8, rad=0.25, label=''):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->',
                                color=color, lw=lw,
                                connectionstyle=f'arc3,rad={rad}'),
                zorder=4)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx + 0.3, my, label, ha='left', va='center',
                fontsize=7.5, color=color, zorder=6, fontstyle='italic')

def zone_box(ax, x, y, w, h, label, color, alpha=0.08):
    r = FancyBboxPatch((x, y), w, h,
                       boxstyle="round,pad=0.0,rounding_size=0.5",
                       facecolor=color, edgecolor=color,
                       linewidth=1.5, alpha=alpha, zorder=1,
                       linestyle='--')
    ax.add_patch(r)
    ax.text(x + 0.18, y + h - 0.22, label,
            ha='left', va='top', fontsize=8, color=color,
            fontweight='bold', alpha=0.85, zorder=2)

# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND ZONES
# ══════════════════════════════════════════════════════════════════════════════
zone_box(ax, 0.3,  7.8, 19.4, 4.9,  'ADMIN / BROWSER LAYER',    '#3B82F6')
zone_box(ax, 0.3,  3.1, 10.5, 4.4,  'BACKEND SERVICES',         '#059669')
zone_box(ax, 11.1, 3.1,  8.5, 4.4,  'DATA & MESSAGING LAYER',   '#D97706')
zone_box(ax, 0.3,  0.3, 19.4, 2.55, 'DEVICE LAYER (macOS)',     '#7C3AED')

# ══════════════════════════════════════════════════════════════════════════════
# ROW 1 — Admin / Browser Layer
# ══════════════════════════════════════════════════════════════════════════════

# Next.js Dashboard
header_box(ax, 0.6, 9.2, 3.8, 3.1, C['blue'], C['panel'],
           'Next.js Dashboard', '🖥️', title_size=11,
           body_items=['Admin web UI', 'Device management',
                       'Policy controls', 'Compliance dashboard', 'Audit logs'])

# IT Admin
box(ax, 1.2, 8.1, 2.6, 0.85, C['blue'], radius=0.3, edgecolor='#60A5FA', lw=1.5)
ax.text(2.5, 8.525, '👤  IT Admin', ha='center', va='center',
        fontsize=10, color='white', fontweight='bold', zorder=5)

# Self-Service Portal
header_box(ax, 5.0, 9.2, 3.8, 3.1, C['teal'], C['panel'],
           'Self-Service Portal', '🌐', title_size=11,
           body_items=['Software catalog', 'App install requests',
                       'JIT admin access req.', 'Token-authenticated', 'HTML — no login'])

# End User
box(ax, 5.6, 8.1, 2.6, 0.85, C['teal'], radius=0.3, edgecolor='#2DD4BF', lw=1.5)
ax.text(6.9, 8.525, '👤  End User (Mac)', ha='center', va='center',
        fontsize=10, color='white', fontweight='bold', zorder=5)

# Apple APNs
header_box(ax, 9.4, 9.2, 3.8, 3.1, C['apns_bg'], C['panel'],
           'Apple APNs', '🍎', title_size=11,
           body_items=['api.push.apple.com', 'HTTP/2 push provider',
                       'Wake-up push to device', 'TLS 1.2+ encrypted',
                       'Push topic from MDM cert'])

# AWS Cloud
header_box(ax, 13.8, 9.2, 5.6, 3.1, C['yellow'], C['panel'],
           'AWS (Production) / LocalStack (Dev)', '☁️', title_size=10,
           body_items=['SQS — command queue', 'RDS PostgreSQL (prod)',
                       'Secrets Manager — APNs keys',
                       'ECS Fargate — app tasks',
                       'EFS — package uploads'])

# ══════════════════════════════════════════════════════════════════════════════
# ROW 2 — Backend Services
# ══════════════════════════════════════════════════════════════════════════════

# FastAPI Core
header_box(ax, 0.6, 3.4, 4.8, 3.8, C['blue_lt'], C['panel'],
           'FastAPI Backend', '⚡', title_size=12,
           body_items=[
               '/api/v1/auth       — JWT login',
               '/api/v1/devices    — CRUD + actions',
               '/api/v1/profiles   — PSSO, USB, GK',
               '/api/v1/packages   — upload & dist.',
               '/api/v1/portal     — self-service',
               '/api/v1/agent      — agent jobs',
               '/api/v1/compliance — policy engine',
               '/api/v1/audit      — audit trail',
           ], body_size=8)

# MDM Protocol
header_box(ax, 5.8, 3.4, 4.6, 3.8, C['purple'], C['panel'],
           'MDM Protocol Handler', '📡', title_size=11,
           body_items=[
               'PUT /mdm/apple/checkin',
               '  → Authenticate',
               '  → TokenUpdate (APNs token)',
               '  → CheckOut',
               'PUT /mdm/apple/connect',
               '  → Deliver queued commands',
               '  → Receive command results',
               '  → mTLS device cert auth',
           ], body_size=8)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 2 — Data & Messaging Layer
# ══════════════════════════════════════════════════════════════════════════════

# PostgreSQL
header_box(ax, 11.4, 5.0, 3.6, 2.2, '#1E40AF', C['panel'],
           'PostgreSQL', '🗄️', title_size=11,
           body_items=['tenants, users, devices',
                       'mdm_commands (queue)',
                       'profiles, script_jobs',
                       'compliance_results, audit'])

# SQS
header_box(ax, 15.4, 5.0, 3.8, 2.2, C['yellow'], C['panel'],
           'SQS Queue', '📨', title_size=11,
           body_items=['mdm-commands queue',
                       'Decouples API from push',
                       'LocalStack for dev',
                       'AWS SQS for prod'])

# Auto-revoke + Notifications
header_box(ax, 11.4, 3.4, 3.6, 1.35, C['orange'], C['panel'],
           'Background Workers', '⚙️', title_size=10,
           body_items=['Auto-revoke (every 60s)',
                       'Webhook notifications'])

# Uploads
header_box(ax, 15.4, 3.4, 3.8, 1.35, C['teal'], C['panel'],
           'File Storage', '📦', title_size=10,
           body_items=['Package uploads (.pkg .dmg)',
                       '/app/uploads  →  EFS (prod)'])

# ══════════════════════════════════════════════════════════════════════════════
# ROW 3 — Device Layer
# ══════════════════════════════════════════════════════════════════════════════

# macOS Device
header_box(ax, 0.6, 0.5, 4.8, 2.1, C['apple_bg'], C['panel'],
           'macOS Device', '💻', title_size=12,
           body_items=['MDM protocol (checkin + connect)',
                       'Installs .mobileconfig profiles',
                       'Executes: Lock / Erase / Restart / Query'],
           body_size=8.5)

# Bash Agent
header_box(ax, 5.8, 0.5, 4.6, 2.1, C['orange'], C['panel'],
           'Bash Management Agent', '🔧', title_size=11,
           body_items=['LaunchDaemon — always running',
                       'Polls /agent/jobs every 30s',
                       'Installs apps, runs scripts, dseditgroup'],
           body_size=8.5)

# Profiles on device
header_box(ax, 10.8, 0.5, 4.0, 2.1, C['purple'], C['panel'],
           'Installed Profiles', '🛡️', title_size=11,
           body_items=['MDM Enrollment profile',
                       'PSSO (Entra ID SSO)',
                       'USB Block (macOS 12–15+)',
                       'Gatekeeper policy'],
           body_size=8.5)

# Compliance
header_box(ax, 15.2, 0.5, 4.3, 2.1, C['green'], C['panel'],
           'Local Compliance State', '✅', title_size=11,
           body_items=['FileVault, Firewall, Gatekeeper',
                       'PSSO registered status',
                       'OS update compliance',
                       'Reported via MDM connect'],
           body_size=8.5)

# ══════════════════════════════════════════════════════════════════════════════
# ARROWS
# ══════════════════════════════════════════════════════════════════════════════

# IT Admin → Dashboard
arrow(ax, 2.5, 8.1, 2.5, 9.2, C['blue_lt'], lw=2, label='HTTPS')

# End User → Portal
arrow(ax, 6.9, 8.1, 6.9, 9.2, C['teal'], lw=2, label='HTTPS')

# Dashboard → FastAPI
arrow(ax, 2.5, 9.2, 2.5, 7.2, C['blue_lt'], lw=2, label='REST API')

# Portal → FastAPI
arrow(ax, 6.9, 9.2, 5.8, 7.2, C['teal'], lw=2)

# FastAPI → MDM Protocol (internal)
arrow(ax, 5.4, 5.3, 5.8, 5.3, C['gray'], lw=1.5, bidirect=True)

# FastAPI → PostgreSQL
arrow(ax, 5.4, 4.8, 11.4, 5.8, C['blue_lt'], lw=1.8, label='SQLAlchemy async')

# FastAPI → SQS
arrow(ax, 5.4, 4.4, 15.4, 5.5, C['yellow'], lw=1.8, label='boto3')

# SQS → APNs (consumer sends push)
curved_arrow(ax, 15.4, 6.2, 11.3, 10.7, C['yellow'], lw=1.8, rad=-0.2, label='send push')

# FastAPI → APNs (direct push for non-queued)
arrow(ax, 3.5, 7.2, 10.5, 10.5, C['blue_lt'], lw=1.5)

# APNs → macOS Device (push notification)
curved_arrow(ax, 10.5, 9.2, 3.0, 2.6, C['apns_bg'], lw=2.2, rad=0.3, label='wake-up push')

# macOS Device → MDM Protocol (checkin / connect)
arrow(ax, 3.0, 2.6, 7.5, 3.4, C['purple'], lw=2, label='PUT /checkin  /connect')

# MDM Protocol → macOS Device (commands)
curved_arrow(ax, 7.5, 3.4, 5.0, 2.6, '#7C3AED', lw=1.5, rad=0.2, label='command plist')

# Bash Agent → FastAPI (poll jobs / submit results)
curved_arrow(ax, 8.1, 2.6, 3.0, 3.4, C['orange'], lw=1.8, rad=-0.15, label='poll jobs / results')

# FastAPI → Bash Agent (job response)
curved_arrow(ax, 2.8, 3.4, 7.9, 2.6, C['orange'], lw=1.3, rad=0.15)

# MDM Protocol → PostgreSQL
arrow(ax, 8.1, 5.0, 11.4, 5.8, C['purple'], lw=1.5)

# Auto-revoke → PostgreSQL
arrow(ax, 13.2, 4.1, 13.2, 5.0, C['orange'], lw=1.5)

# ══════════════════════════════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════════════════════════════
ax.text(10.0, 12.7, 'MDM SaaS — High-Level Architecture',
        ha='center', va='center', fontsize=18, color='white',
        fontweight='bold', zorder=10)
ax.text(10.0, 12.35, 'Multi-Tenant Apple MDM Platform with Entra ID PSSO · Software Distribution · Compliance · JIT Admin Access',
        ha='center', va='center', fontsize=9.5, color=C['gray'], zorder=10)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    (C['blue_lt'],  'Dashboard API (HTTPS/JWT)'),
    (C['purple'],   'MDM Protocol (mTLS)'),
    (C['orange'],   'Agent (HTTP + agent token)'),
    (C['yellow'],   'SQS Messaging (boto3)'),
    (C['apns_bg'],  'APNs Push (HTTP/2 TLS)'),
    (C['teal'],     'Self-Service Portal'),
]
lx = 0.6
for color, label in legend_items:
    box(ax, lx, 0.06, 0.28, 0.2, color, radius=0.05)
    ax.text(lx + 0.35, 0.16, label, ha='left', va='center',
            fontsize=7.5, color=C['gray_lt'], zorder=6)
    lx += 3.2

plt.tight_layout(pad=0.3)
out = '/Users/manikandank/Downloads/mdm-saas/scripts/arch_diagram.png'
plt.savefig(out, dpi=160, bbox_inches='tight',
            facecolor='#0F172A', edgecolor='none')
plt.close()
print(f'Saved: {out}')
