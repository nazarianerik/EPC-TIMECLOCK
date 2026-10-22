"""Set (or change) the admin password.

Run:  .venv\\Scripts\\python set_password.py      (Windows)
"""

from getpass import getpass

from werkzeug.security import generate_password_hash

from config import load_config, save_config


def main():
    cfg = load_config()
    print("Set the admin password (typing is hidden).")
    while True:
        pw = getpass("New password: ")
        if len(pw) < 6:
            print("Please use at least 6 characters.\n")
            continue
        if pw != getpass("Type it again: "):
            print("Those didn't match. Try again.\n")
            continue
        break
    cfg["admin_password_hash"] = generate_password_hash(pw)
    save_config(cfg)
    print("Admin password saved. If the server is running, the new password works right away.")


if __name__ == "__main__":
    main()
