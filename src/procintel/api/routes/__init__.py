"""Endpoint groups. A new group is a module with a `router`, listed in ROUTERS with the role it needs (None: open,
or the module guards its routes itself); roles are checked in the backend for every call (procintel.api.security)."""
from procintel.api.routes import (ask, assess, assistant, auth, conversations, dashboard, evaluation, feedback, figures, health, insights, intake, jobs, media,
                                  monitoring, pipeline, prompts, settings, shadows, webhooks)

ROUTERS = [
    (auth.router, None),         # sign-in is open; account management checks the admin role per route
    (health.router, None),
    (webhooks.router, None),     # source systems pushing changes: checked by their signature, not a session
    (dashboard.router, "planner"),
    (assess.router, "planner"),
    (ask.router, "planner"),
    (figures.router, "planner"),  # the image of a cited figure
    (media.router, "planner"),    # project photos and videos: any planner sees them; the uploader or an admin removes one
    (assistant.router, "planner"),  # the planning chat
    (conversations.router, "planner"),  # each user's saved conversations (plan chat and Ask), their own only
    (feedback.router, "planner"),  # its review listing needs a reviewer (per route)
    (insights.router, "planner"),  # each planner's own watch-list and alerts
    (monitoring.router, "planner"),  # ongoing work; its status-rule routes need admin (per route)
    (settings.router, "admin"),
    (prompts.router, "admin"),
    (jobs.router, None),         # admin per route; reload also from the local refresh script
    (pipeline.router, "admin"),
    (intake.router, "planner"),   # uploads: planners their own, admins all; approving needs admin (per route)
    (shadows.router, "admin"),
    (evaluation.router, "reviewer"),  # labelling and reading; starting a run needs admin (per route)
]
