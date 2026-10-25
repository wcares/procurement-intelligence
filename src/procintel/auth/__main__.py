"""Accounts from the command line (the password is asked for, never passed as an argument):

    python -m procintel.auth add-user NAME [--role planner|admin]
    python -m procintel.auth set-password NAME
    python -m procintel.auth list
"""
from __future__ import annotations

import argparse
import getpass

from procintel.auth import ROLES, service, store


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m procintel.auth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-user")
    add.add_argument("name")
    add.add_argument("--role", choices=ROLES, default="planner")
    sub.add_parser("set-password").add_argument("name")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "list":
        for u in store.users():
            print(f"{u['username']:20s} {u['role']:8s} {'active' if u['active'] else 'disabled'}")
        return
    pw = getpass.getpass("password: ")
    if pw != getpass.getpass("again: "):
        raise SystemExit("the passwords differ")
    if a.cmd == "add-user":
        service.create_user(a.name, pw, a.role)
    else:
        service.update_user(a.name, password=pw)
    print("done")


if __name__ == "__main__":
    main()
