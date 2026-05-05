#!/usr/bin/env python3
"""
Management CLI — run from the project root:

    python -m cli.manage <command> [args]

Commands:
    init-db                              Initialise / migrate database (runs Alembic)
    create-client <slug> <name>          Create a new client
    create-domain <slug> <domain>        Add a domain to a client
    create-user <email> <role>           Create a user (prompted for password)
      [--client <slug>]                  Assign to a client (default viewer role)
      [--client-role admin|viewer]       Per-client role when using --client
    list-clients                         List all clients
    set-role <email> <role>              Change a user's global role (super_admin|user)
    assign-client <email> <slug>         Grant a user access to a client
      [--role admin|viewer]              Per-client role (default: viewer)
    set-client-role <email> <slug> <r>   Change per-client role for an existing assignment
    revoke-client <email> <slug>         Remove a user's access to a client
    reset-password <email>               Set a new password for a user
      [--temporary]                      Mark as temporary (user must change on next login)
    scan <slug> [--dir <path>]           Process files in a client's incoming folder
    enrich-geo <slug> [--force]          Backfill geo data on records missing location info
    export-client <slug>                 Export all client data to a ZIP file
      [--output <path>]                  Output path (default: ./{slug}-export-{date}.zip)
    purge-client <slug>                  Permanently delete all data for a client
      [--yes]                            Skip interactive confirmation (for scripting)
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import SessionLocal, init_db
from core.models import Client, Domain, User, UserClient, UserRole, ClientRole
from core.config import settings
from core.security import hash_password


def cmd_init_db(_args):
    init_db()
    print("Database initialised.")


def cmd_create_client(args):
    db = SessionLocal()
    try:
        if db.query(Client).filter_by(slug=args.slug).first():
            print(f"Client '{args.slug}' already exists.")
            return
        client = Client(slug=args.slug, name=args.name)
        db.add(client)
        db.commit()
        settings.client_incoming_dir(args.slug).mkdir(parents=True, exist_ok=True)
        print(f"Client '{args.slug}' created. Incoming: {settings.client_incoming_dir(args.slug)}")
    finally:
        db.close()


def cmd_create_domain(args):
    db = SessionLocal()
    try:
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        db.add(Domain(client_id=client.id, domain=args.domain))
        db.commit()
        print(f"Domain '{args.domain}' added to '{args.slug}'.")
    finally:
        db.close()


def cmd_create_user(args):
    try:
        role = UserRole(args.role)
    except ValueError:
        print(f"Invalid role. Choose: {[r.value for r in UserRole]}")
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(email=args.email).first()
        if existing:
            print(f"User '{args.email}' already exists. Use assign-client to add client access.")
            return

        password = getpass.getpass("Password: ")
        user = User(email=args.email, role=role.value, password_hash=hash_password(password))
        db.add(user)
        db.flush()

        if args.client:
            client = db.query(Client).filter_by(slug=args.client).first()
            if not client:
                print(f"Client '{args.client}' not found — user created without client assignment.")
            else:
                client_role = args.client_role if args.client_role else "viewer"
                db.add(UserClient(user_id=user.id, client_id=client.id, role=client_role))

        db.commit()
        print(f"User '{args.email}' ({role.value}) created.")
    finally:
        db.close()


def cmd_set_role(args):
    try:
        role = UserRole(args.role)
    except ValueError:
        print(f"Invalid role. Choose: {[r.value for r in UserRole]}")
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email).first()
        if not user:
            print(f"User '{args.email}' not found.")
            return
        old_role = user.role
        user.role = role.value
        db.commit()
        print(f"User '{args.email}' role changed from '{old_role}' to '{role.value}'.")
    finally:
        db.close()


def cmd_assign_client(args):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email).first()
        if not user:
            print(f"User '{args.email}' not found.")
            return
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        existing = db.query(UserClient).filter_by(user_id=user.id, client_id=client.id).first()
        if existing:
            print(f"User '{args.email}' already has access to '{args.slug}'. Use set-client-role to change role.")
            return
        role = args.role if args.role else "viewer"
        db.add(UserClient(user_id=user.id, client_id=client.id, role=role))
        db.commit()
        print(f"Assigned client '{args.slug}' to user '{args.email}' with role '{role}'.")
    finally:
        db.close()


def cmd_set_client_role(args):
    try:
        role = ClientRole(args.role)
    except ValueError:
        print(f"Invalid client role. Choose: {[r.value for r in ClientRole]}")
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email).first()
        if not user:
            print(f"User '{args.email}' not found.")
            return
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        uc = db.query(UserClient).filter_by(user_id=user.id, client_id=client.id).first()
        if not uc:
            print(f"User '{args.email}' does not have access to '{args.slug}'. Use assign-client first.")
            return
        old_role = uc.role
        uc.role = role.value
        db.commit()
        print(f"Client role for '{args.email}' on '{args.slug}' changed from '{old_role}' to '{role.value}'.")
    finally:
        db.close()


def cmd_revoke_client(args):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email).first()
        if not user:
            print(f"User '{args.email}' not found.")
            return
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        uc = db.query(UserClient).filter_by(user_id=user.id, client_id=client.id).first()
        if not uc:
            print(f"User '{args.email}' does not have access to '{args.slug}'.")
            return
        db.delete(uc)
        db.commit()
        print(f"Revoked client '{args.slug}' from user '{args.email}'.")
    finally:
        db.close()


def cmd_reset_password(args):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email).first()
        if not user:
            print(f"User '{args.email}' not found.")
            return
        password = getpass.getpass("New password: ")
        user.password_hash = hash_password(password)
        user.must_change_password = args.temporary
        db.commit()
        flag = " (temporary — user must change on next login)" if args.temporary else ""
        print(f"Password reset for '{args.email}'{flag}.")
    finally:
        db.close()


def cmd_list_clients(_args):
    db = SessionLocal()
    try:
        clients = db.query(Client).all()
        if not clients:
            print("No clients found.")
            return
        for c in clients:
            status = "active" if c.is_active else "inactive"
            print(f"  {c.slug:<24} {c.name:<40} [{status}]")
    finally:
        db.close()


def cmd_scan(args):
    from ingestion.pipeline import process_file
    from ingestion.archiver import archive_file

    scan_dir = Path(args.dir) if args.dir else settings.client_incoming_dir(args.slug)
    if not scan_dir.exists():
        print(f"Directory not found: {scan_dir}")
        return

    db = SessionLocal()
    processed = 0
    try:
        for f in scan_dir.iterdir():
            if f.is_file():
                ok = process_file(f, args.slug, db)
                if ok:
                    archive_file(f, args.slug, db)
                    processed += 1
    finally:
        db.close()

    print(f"Scanned {scan_dir}: {processed} file(s) processed.")


def cmd_enrich_geo(args):
    from ingestion.geo_enrichment import enrich_geo
    from core.models import Client as C

    db = SessionLocal()
    try:
        client = db.query(C).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        result = enrich_geo(db, client.id, force=args.force)
        print(
            f"Scanned {result['records_scanned']} record(s) — "
            f"{result['records_updated']} updated, "
            f"{result['flags_added']} geo_anomaly flag(s) added."
        )
    finally:
        db.close()


def cmd_export_client(args):
    from datetime import datetime, timezone
    from core.client_offboard import build_export_zip

    db = SessionLocal()
    try:
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return

        print(f"Exporting data for '{args.slug}'…")
        zip_bytes = build_export_zip(client, db)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output = Path(args.output) if args.output else Path(f"{args.slug}-export-{date_str}.zip")
        output.write_bytes(zip_bytes)
        print(f"Export written to: {output.resolve()}  ({len(zip_bytes):,} bytes)")
    finally:
        db.close()


def cmd_purge_client(args):
    from core.client_offboard import purge_client as _purge

    db = SessionLocal()
    try:
        client = db.query(Client).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return

        if not args.yes:
            print(f"\nThis will permanently delete ALL data for client '{args.slug}':")
            print(f"  • All reports, records, flags, and auth results")
            print(f"  • Domains, IMAP config, processed file records")
            print(f"  • All user assignments to this client")
            print(f"  • Users with no other client access will be deactivated")
            print(f"  • Report files on disk will be removed\n")
            confirm = input(f"Type the client slug to confirm: ").strip()
            if confirm != args.slug:
                print("Slug did not match — aborted.")
                return

        print(f"Purging '{args.slug}'…")
        summary = _purge(client, db)

        d = summary["deleted"]
        print(f"\nPurge complete:")
        print(f"  Reports deleted   : {d['reports']}")
        print(f"  Records deleted   : {d['records']}")
        print(f"  Auth results      : {d['auth_results']}")
        print(f"  Flags deleted     : {d['flags']}")
        print(f"  Domains deleted   : {d['domains']}")
        print(f"  IMAP configs      : {d['imap_configs']}")
        print(f"  Processed files   : {d['processed_files']}")
        print(f"  User assignments  : {d['user_assignments']}")
        if summary["deactivated_users"]:
            print(f"  Deactivated users : {', '.join(summary['deactivated_users'])}")
        if summary["filesystem_removed"]:
            print(f"  Directories removed:")
            for p in summary["filesystem_removed"]:
                print(f"    {p}")
    finally:
        db.close()


def cmd_enrich_whois(args):
    from ingestion.whois_enrichment import enrich_whois
    from core.models import Client as C

    db = SessionLocal()
    try:
        client = db.query(C).filter_by(slug=args.slug).first()
        if not client:
            print(f"Client '{args.slug}' not found.")
            return
        print(f"Looking up WHOIS data for {args.slug} (this may take a moment)…")
        result = enrich_whois(db, client.id, force=args.force)
        print(
            f"Scanned {result['records_scanned']} record(s) — "
            f"{result['records_updated']} updated, "
            f"{result['ips_queried']} unique IP(s) queried."
        )
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="DMARC system management CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db")

    p = sub.add_parser("create-client")
    p.add_argument("slug")
    p.add_argument("name")

    p = sub.add_parser("create-domain")
    p.add_argument("slug")
    p.add_argument("domain")

    p = sub.add_parser("create-user")
    p.add_argument("email")
    p.add_argument("role", choices=[r.value for r in UserRole])
    p.add_argument("--client", default=None)
    p.add_argument("--client-role", choices=[r.value for r in ClientRole], default=None, dest="client_role")

    sub.add_parser("list-clients")

    p = sub.add_parser("set-role", help="Change a user's global role")
    p.add_argument("email")
    p.add_argument("role", choices=[r.value for r in UserRole])

    p = sub.add_parser("assign-client", help="Grant a user access to a client")
    p.add_argument("email")
    p.add_argument("slug")
    p.add_argument("--role", choices=[r.value for r in ClientRole], default="viewer")

    p = sub.add_parser("set-client-role", help="Change per-client role for an existing assignment")
    p.add_argument("email")
    p.add_argument("slug")
    p.add_argument("role", choices=[r.value for r in ClientRole])

    p = sub.add_parser("revoke-client", help="Remove a user's access to a client")
    p.add_argument("email")
    p.add_argument("slug")

    p = sub.add_parser("reset-password", help="Reset a user's password")
    p.add_argument("email")
    p.add_argument("--temporary", action="store_true", help="Force password change on next login")

    p = sub.add_parser("scan")
    p.add_argument("slug")
    p.add_argument("--dir", default=None)

    p = sub.add_parser("enrich-geo")
    p.add_argument("slug")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("enrich-whois")
    p.add_argument("slug")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("export-client", help="Export all client data to a ZIP file")
    p.add_argument("slug")
    p.add_argument("--output", default=None, help="Output file path")

    p = sub.add_parser("purge-client", help="Permanently delete all data for a client")
    p.add_argument("slug")
    p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()
    commands = {
        "init-db": cmd_init_db,
        "create-client": cmd_create_client,
        "create-domain": cmd_create_domain,
        "create-user": cmd_create_user,
        "list-clients": cmd_list_clients,
        "set-role": cmd_set_role,
        "assign-client": cmd_assign_client,
        "set-client-role": cmd_set_client_role,
        "revoke-client": cmd_revoke_client,
        "reset-password": cmd_reset_password,
        "scan": cmd_scan,
        "enrich-geo": cmd_enrich_geo,
        "enrich-whois": cmd_enrich_whois,
        "export-client": cmd_export_client,
        "purge-client": cmd_purge_client,
    }

    if args.command not in commands:
        parser.print_help()
        return

    commands[args.command](args)


if __name__ == "__main__":
    main()