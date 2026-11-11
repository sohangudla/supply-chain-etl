"""One-time local PostgreSQL setup (no admin rights, no Windows service).

  * initdb a cluster in ../_local/pgdata (outside the repo)
  * start it on localhost:5432
  * create role etl_user + databases olist_dw and olist_test
  * write random passwords to git-ignored .env files (never printed)

Usage:  python scripts/setup_local_postgres.py [--start-only]
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT.parent / "_local"
PGDATA = LOCAL / "pgdata"
SUPER_ENV = LOCAL / "postgres_superuser.env"
APP_ENV = ROOT / ".env"
PORT = os.getenv("PGPORT", "5432")


def pg_bin(name: str) -> str:
    exe = shutil.which(name) or str(Path(sys.executable).parent / "Library" / "bin" / f"{name}.exe")
    if not Path(exe).exists():
        sys.exit(f"Cannot find {name}; activate the conda env first")
    return exe


def read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def is_running() -> bool:
    r = subprocess.run([pg_bin("pg_ctl"), "status", "-D", str(PGDATA)], capture_output=True)
    return r.returncode == 0


def start() -> None:
    if is_running():
        print("PostgreSQL already running")
        return
    subprocess.run([pg_bin("pg_ctl"), "start", "-D", str(PGDATA), "-w",
                    "-l", str(LOCAL / "postgres.log"), "-o", f"-p {PORT}"], check=True)


def psql(sql: str, password: str, db: str = "postgres") -> None:
    env = {**os.environ, "PGPASSWORD": password}
    subprocess.run([pg_bin("psql"), "-h", "localhost", "-p", PORT, "-U", "postgres",
                    "-d", db, "-v", "ON_ERROR_STOP=1", "-q", "-c", sql],
                   check=True, env=env)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-only", action="store_true")
    args = ap.parse_args()
    LOCAL.mkdir(exist_ok=True)

    if args.start_only:
        start()
        return

    if not PGDATA.exists():
        super_pw = secrets.token_urlsafe(24)
        SUPER_ENV.write_text(f"POSTGRES_SUPERUSER_PASSWORD={super_pw}\n")
        pwfile = LOCAL / ".pwfile.tmp"
        pwfile.write_text(super_pw)
        try:
            subprocess.run([pg_bin("initdb"), "-D", str(PGDATA), "-U", "postgres",
                            "--auth=scram-sha-256", f"--pwfile={pwfile}", "-E", "UTF8",
                            "--locale=C"], check=True, capture_output=True)
        finally:
            pwfile.unlink(missing_ok=True)
        print(f"Initialised cluster at {PGDATA}")
    super_pw = read_env(SUPER_ENV)["POSTGRES_SUPERUSER_PASSWORD"]
    start()
    time.sleep(1)

    if APP_ENV.exists():
        app_pw = read_env(APP_ENV)["PGPASSWORD"]
    else:
        app_pw = secrets.token_urlsafe(24)
        APP_ENV.write_text(
            "# Local only - git-ignored. Never commit.\n"
            f"PGHOST=localhost\nPGPORT={PORT}\nPGDATABASE=olist_dw\n"
            f"PGUSER=etl_user\nPGPASSWORD={app_pw}\nPGTEST_DATABASE=olist_test\n")
    psql("DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='etl_user') "
         f"THEN CREATE ROLE etl_user LOGIN PASSWORD '{app_pw}'; END IF; END$$;", super_pw)
    for db in ("olist_dw", "olist_test"):
        env = {**os.environ, "PGPASSWORD": super_pw}
        exists = subprocess.run(
            [pg_bin("psql"), "-h", "localhost", "-p", PORT, "-U", "postgres", "-tAc",
             f"SELECT 1 FROM pg_database WHERE datname='{db}'"],
            capture_output=True, text=True, env=env).stdout.strip()
        if exists != "1":
            psql(f"CREATE DATABASE {db} OWNER etl_user", super_pw)
            print(f"Created database {db}")
    print("Local PostgreSQL ready; credentials stored in .env (git-ignored)")


if __name__ == "__main__":
    main()
