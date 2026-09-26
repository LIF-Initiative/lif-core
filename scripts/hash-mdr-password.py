#!/usr/bin/env python3
"""Print a password hash for MDR__AUTH__LOCAL_USERS (#1316).

Usage:
    python3 scripts/hash-mdr-password.py

Prompts for the password twice and prints the hash. Put it in your .env as
``MDR__AUTH__LOCAL_USERS=alice@example.org=<hash>``; separate several users with
commas. Needs only the Python standard library, so it runs outside the repo's venv.
"""

import getpass
import importlib.util
import sys
from pathlib import Path

# Load the module by path: importing the lif.mdr_restapi package would start the MDR app.
_MODULE = Path(__file__).resolve().parent.parent / "bases" / "lif" / "mdr_restapi" / "local_users.py"
_spec = importlib.util.spec_from_file_location("local_users", _MODULE)
assert _spec is not None and _spec.loader is not None
local_users = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(local_users)

password = getpass.getpass("Password: ")
if not password:
    sys.exit("Empty password; nothing printed.")
if getpass.getpass("Again: ") != password:
    sys.exit("Passwords did not match; nothing printed.")
print(local_users.hash_password(password))
