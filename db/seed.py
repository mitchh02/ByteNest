#!/usr/bin/env python3
"""Populate the existing MySQL schema with synthetic hiring-network data."""

import argparse
from decimal import Decimal
import os
import random
import uuid


FIRST_NAMES = ('Alex', 'Jordan', 'Taylor', 'Morgan', 'Sam', 'Casey', 'Jamie', 'Riley')
LAST_NAMES = ('Chen', 'Patel', 'Garcia', 'Smith', 'Kim', 'Williams', 'Ahmed', 'Rivera')
COMPANIES = ('Northstar Labs', 'Cedar Systems', 'Orbit Analytics', 'Harbor Software')
TITLES = ('Backend Engineer', 'Frontend Engineer', 'Data Engineer', 'Product Designer',
          'Engineering Manager', 'Product Manager')
LOCATIONS = ('Chicago, IL', 'Austin, TX', 'Seattle, WA', 'Boston, MA', 'Remote')
SOURCES = ('self_rated', 'coworker', 'github', 'contacts', 'inferred')


def generate_data(user_count, connection_count, job_count, seed=None):
    """Return records using zero-based user indices until database IDs are known."""
    if user_count < 1 or job_count < 0 or connection_count < 0:
        raise ValueError('Users must be positive; connections and jobs must be nonnegative.')
    maximum = user_count * (user_count - 1) // 2
    if connection_count > maximum:
        raise ValueError(f'{user_count} users allow at most {maximum} unique connections.')
    rng = random.Random(seed)
    # A fresh namespace lets repeated runs append without conflicting emails.
    namespace = uuid.uuid4().hex
    users, contacts, connections, jobs = [], [], [], []
    hiring = set(rng.sample(range(user_count), max(1, user_count // 5))) if job_count else set()
    for index in range(user_count):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        company, title = rng.choice(COMPANIES), rng.choice(TITLES)
        handle = f'demo-{namespace}-{index}'
        email = f'{handle}@example.com'
        users.append((first, last, email, None, title, company,
                      f'{first} is a synthetic {title.lower()} interested in collaboration and mentoring.',
                      rng.choice(LOCATIONS), index in hiring))
        contacts.extend(((index, 'email', email, False),
                         (index, 'website', f'https://example.com/profiles/{handle}', True)))

    # Seed a spanning tree when enough edges are requested, so path searches work.
    pairs = set()
    for right in range(1, min(user_count, connection_count + 1)):
        pairs.add((rng.randrange(right), right))
    remaining = connection_count - len(pairs)
    if remaining:
        # Dense graphs use a finite candidate list instead of repeated collisions.
        if connection_count > maximum // 2:
            candidates = [(a, b) for a in range(user_count)
                          for b in range(a + 1, user_count) if (a, b) not in pairs]
            pairs.update(rng.sample(candidates, remaining))
        else:
            while len(pairs) < connection_count:
                a, b = sorted(rng.sample(range(user_count), 2))
                pairs.add((a, b))
    for a, b in sorted(pairs):
        same_company = users[a][5] == users[b][5]
        source = 'coworker' if same_company else rng.choice(SOURCES)
        context = (f'Worked together at {users[a][5]}' if same_company
                   else 'Met through a synthetic professional networking event')
        connections.append((a, b, Decimal(rng.randint(1, 100)) / 100,
                            source, context, rng.choice((True, False))))
    for _ in range(job_count):
        poster = rng.choice(sorted(hiring))
        title = rng.choice(TITLES)
        jobs.append((poster, title, users[poster][5],
                     f'Join {users[poster][5]} as a {title}. Synthetic demo opening.', True))
    return users, contacts, connections, jobs


def insert_data(connection, data):
    """Insert all records in one transaction, preserving existing data."""
    users, contacts, connections, jobs = data
    cursor = connection.cursor()
    try:
        ids = []
        for user in users:
            cursor.execute(
                'INSERT INTO users (first_name, last_name, email, password_hash, '
                'job_title, company, bio, location, is_hiring) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)', user)
            ids.append(cursor.lastrowid)
        if contacts:
            cursor.executemany(
                'INSERT INTO user_contacts (user_id, contact_type, value, is_public) '
                'VALUES (%s, %s, %s, %s)',
                [(ids[row[0]], *row[1:]) for row in contacts])
        if connections:
            cursor.executemany(
                'INSERT INTO user_connections (user_a_id, user_b_id, strength, source, context, confirmed) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                [(*sorted((ids[row[0]], ids[row[1]])), *row[2:]) for row in connections])
        if jobs:
            cursor.executemany(
                'INSERT INTO job_openings (posted_by, title, company, description, is_open) '
                'VALUES (%s, %s, %s, %s, %s)',
                [(ids[row[0]], *row[1:]) for row in jobs])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users', type=int, default=100)
    parser.add_argument('--connections', type=int, default=300)
    parser.add_argument('--jobs', type=int, default=30)
    parser.add_argument('--seed', type=int, help='Reproduce profiles and relationships (emails remain unique).')
    parser.add_argument('--dry-run', action='store_true', help='Generate without connecting or writing.')
    parser.add_argument('--host', default=os.getenv('MYSQL_HOST', 'localhost'))
    parser.add_argument('--port', type=int, default=int(os.getenv('MYSQL_PORT', '3306')))
    parser.add_argument('--user', default=os.getenv('MYSQL_USER', 'root'))
    parser.add_argument('--database', default=os.getenv('MYSQL_DATABASE', 'six_degrees'))
    args = parser.parse_args()
    try:
        data = generate_data(args.users, args.connections, args.jobs, args.seed)
    except ValueError as error:
        parser.error(str(error))
    if not args.dry_run:
        try:
            import mysql.connector
        except ImportError:
            parser.exit(1, 'Install the driver with: python3 -m pip install -r db/requirements.txt\n')
        try:
            connection = mysql.connector.connect(
                host=args.host, port=args.port, user=args.user,
                password=os.getenv('MYSQL_PASSWORD', ''), database=args.database,
                autocommit=False)
            try:
                insert_data(connection, data)
            finally:
                connection.close()
        except mysql.connector.Error as error:
            parser.exit(1, f'Database error: {error}\n')
    action = 'Generated (dry run)' if args.dry_run else 'Inserted'
    print(f'{action}: {len(data[0])} users, {len(data[1])} contacts, '
          f'{len(data[2])} connections, {len(data[3])} job openings.')


if __name__ == '__main__':
    main()
