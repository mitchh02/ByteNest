# Synthetic database data

Apply `schema.sql` to MySQL 8.0.16 or newer first, then run from the repository root:

```bash
python3 -m pip install -r db/requirements.txt
export MYSQL_USER=your_database_user
export MYSQL_PASSWORD=your_database_password
python3 db/seed.py --seed 42
```

The default run appends 100 users, 200 contacts, 300 connections, and 30 open
roles. Each run uses unique demo emails at `example.com`. Demo users have no
password hash. All rows are inserted in one transaction, rolled back on failure.

Customize counts and preview generation without a database or driver:

```bash
python3 db/seed.py --users 200 --connections 600 --jobs 50 --seed 42 --dry-run
```

Connection options are `--host`, `--port`, `--user`, and `--database`, or the
corresponding `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, and `MYSQL_DATABASE`
environment variables. The password is read from `MYSQL_PASSWORD`.

Connections are unique ordered pairs with strengths from 0.01 to 1.00. When
at least `users - 1` connections are requested, every generated user belongs to
one connected network. Job posters are marked as hiring and their company matches
the opening. `--seed` reproduces profiles and relationships; email namespaces
remain unique so runs can coexist.
