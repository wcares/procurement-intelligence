"""Endpoint groups. A new group is a module with a `router` here, added to ROUTERS."""
from procintel.api.routes import ask, assess, feedback, health, jobs, settings, shadows

ROUTERS = [assess.router, ask.router, feedback.router, settings.router, jobs.router, shadows.router, health.router]
