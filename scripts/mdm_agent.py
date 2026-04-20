#!/usr/bin/env python3
"""
MDM Management Agent — runs as a root LaunchDaemon on enrolled Macs.

Polls the MDM server for pending script jobs and executes them as root.
Config is read from /Library/MDMAgent/config.json:
  {"server_url": "https://...", "agent_token": "uuid"}

Logs to /var/log/mdm-agent.log.
"""
import json
import logging
import os
import pwd
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONFIG_PATH = "/Library/MDMAgent/config.json"
LOG_PATH = "/var/log/mdm-agent.log"
POLL_INTERVAL = 30  # seconds
USER_REPORT_INTERVAL = 300  # report local users every 5 minutes
MAX_OUTPUT = 65536  # 64 KB cap on stdout/stderr

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mdm-agent")


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    server_url = cfg["server_url"].rstrip("/")
    agent_token = cfg["agent_token"]
    return server_url, agent_token


def make_ssl_context():
    ctx = ssl.create_default_context()
    return ctx


def api_request(server_url, agent_token, method, path, body=None):
    url = f"{server_url}/api/v1/agent{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {agent_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    ctx = make_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read())


def poll_jobs(server_url, agent_token):
    return api_request(server_url, agent_token, "GET", "/jobs")


def post_result(server_url, agent_token, job_id, exit_code, stdout, stderr):
    api_request(server_url, agent_token, "POST", f"/jobs/{job_id}/result", {
        "exit_code": exit_code,
        "stdout": stdout[:MAX_OUTPUT] if stdout else "",
        "stderr": stderr[:MAX_OUTPUT] if stderr else "",
    })


def get_console_user():
    """Return the short name of the user logged in at the GUI console (pure Python, no subprocess)."""
    try:
        import stat as _stat
        st = os.stat("/dev/console")
        pw = pwd.getpwuid(st.st_uid)
        name = pw.pw_name
        return name if name and name != "root" else None
    except Exception:
        return None


def get_local_users():
    """
    Return real local user accounts (UID >= 500) using only Python stdlib.
    No dscl/sysadminctl — avoids xcode-select errors in headless LaunchDaemon context.
    """
    import grp as _grp

    console_user = get_console_user()

    # Admin group members from /etc/group (no subprocess)
    try:
        admin_members = set(_grp.getgrnam("admin").gr_mem)
    except Exception:
        admin_members = set()

    users = []
    try:
        pwd.getpwall()  # warm cache
    except Exception:
        pass

    seen = set()
    try:
        for pw in pwd.getpwall():
            if pw.pw_uid < 500:
                continue
            if pw.pw_name.startswith("_"):
                continue
            if pw.pw_name in seen:
                continue
            seen.add(pw.pw_name)

            full_name = pw.pw_gecos.split(",")[0].strip() or pw.pw_name

            users.append({
                "short_name": pw.pw_name,
                "full_name": full_name,
                "is_admin": pw.pw_name in admin_members,
                "is_logged_in": pw.pw_name == console_user,
                "has_secure_token": False,  # not detectable without dscl in daemon context
            })
    except Exception as e:
        log.warning("Failed to list local users: %s", e)

    return users


def report_users(server_url, agent_token):
    """Collect local users and send to server."""
    try:
        users = get_local_users()
        if users:
            api_request(server_url, agent_token, "POST", "/users", users)
            log.info("Reported %d local users to server", len(users))
    except Exception as e:
        log.warning("Failed to report users: %s", e)


def execute_job(job, server_url, agent_token):
    job_id = job["id"]
    command = job["command"]
    label = job.get("label", "")
    log.info("Executing job %s label=%s: %s", job_id, label, command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
        log.info("Job %s exit_code=%d", job_id, exit_code)
        if stderr:
            log.warning("Job %s stderr: %s", job_id, stderr[:500])
    except subprocess.TimeoutExpired:
        exit_code = -1
        stdout = ""
        stderr = "Command timed out after 300 seconds"
        log.error("Job %s timed out", job_id)
    except Exception as e:
        exit_code = -1
        stdout = ""
        stderr = str(e)
        log.error("Job %s execution error: %s", job_id, e)

    try:
        post_result(server_url, agent_token, job_id, exit_code, stdout, stderr)
    except Exception as e:
        log.error("Failed to post result for job %s: %s", job_id, e)


def main():
    # Wait for config to exist (may not be present on very first boot)
    while not os.path.exists(CONFIG_PATH):
        log.warning("Config not found at %s — retrying in 60s", CONFIG_PATH)
        time.sleep(60)

    try:
        server_url, agent_token = load_config()
    except Exception as e:
        log.error("Failed to load config: %s", e)
        sys.exit(1)

    log.info("MDM agent started. server=%s poll_interval=%ds", server_url, POLL_INTERVAL)

    last_user_report = 0

    while True:
        try:
            jobs = poll_jobs(server_url, agent_token)
            if jobs:
                log.info("Received %d job(s)", len(jobs))
                for job in jobs:
                    execute_job(job, server_url, agent_token)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.error("Unauthorized — check agent_token in %s", CONFIG_PATH)
            else:
                log.warning("HTTP error polling jobs: %s %s", e.code, e.reason)
        except Exception as e:
            log.warning("Poll error: %s", e)

        # Report local users every USER_REPORT_INTERVAL seconds
        now = time.time()
        if now - last_user_report >= USER_REPORT_INTERVAL:
            report_users(server_url, agent_token)
            last_user_report = now

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
