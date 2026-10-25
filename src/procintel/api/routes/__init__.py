"""Endpoint groups. A new group is a module with a `router`, listed in ROUTERS with the role it needs (None: open,
or the module guards its routes itself); roles are checked in the backend for every call (procintel.api.security)."""
from procintel.api.routes import ask, assess, auth, feedback, health, jobs, pipeline, prompts, settings, shadows

ROUTERS = [
    (auth.router, None),         # sign-in is open; account management checks the admin role per route
    (health.router, None),
    (assess.router, "planner"),
    (ask.router, "planner"),
    (feedback.router, "planner"),  # its review listing needs admin (per route)
    (settings.router, "admin"),
    (prompts.router, "admin"),
    (jobs.router, None),         # admin per route; reload also from the local refresh script
    (pipeline.router, "admin"),
    (shadows.router, "admin"),
]
