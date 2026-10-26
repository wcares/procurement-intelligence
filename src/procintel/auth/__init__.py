"""Sign-in and roles (docs/ui-design.md section 3c).

    passwords.py  salted scrypt hashes
    store.py      accounts, sessions and failed logins (data/auth.duckdb, schema "auth" in Postgres)
    service.py    log in / out, the user behind a session, the first admin, pseudonymous ids for the logs

PROCINTEL_AUTH chooses the identity provider: "local" (username and password, the default) or "off" (no sign-in,
everyone is an admin: tests and a one-person local install). Single sign-on is a further provider for a pilot.
"""
ROLES = ("planner", "reviewer", "admin")  # each role can do everything the roles before it can
RANK = {r: i for i, r in enumerate(ROLES)}


def has_role(role: str | None, needed: str) -> bool:
    """Whether an account with `role` may use what needs `needed` (planner < reviewer < admin)."""
    return role in RANK and RANK[role] >= RANK[needed]
