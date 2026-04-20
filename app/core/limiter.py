"""
Shared slowapi rate-limiter instance.

Key limits:
  - /auth/login, /auth/2fa/*  →  10 requests / minute / IP  (brute-force guard)
  - /mdm/apple/*              →  120 requests / minute / IP  (device churn)
  - Everything else           →  200 requests / minute / IP  (general API)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
