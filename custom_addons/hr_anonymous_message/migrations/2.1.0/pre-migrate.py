# -*- coding: utf-8 -*-
"""
Migration: 2.0.0 → 2.1.0
Moves old `category` Selection field values to new `category_id` Many2one.

Odoo runs this automatically during upgrade because it lives in:
  migrations/2.1.0/pre-migrate.py

'pre' means it runs BEFORE the new models are loaded, so we work
directly with SQL to avoid ORM conflicts during the transition.
"""
import logging

_logger = logging.getLogger(__name__)

# Maps old selection key → the name value in hr.anonymous.message.category
CATEGORY_MAP = {
    'complaint':      'Complaint',
    'suggestion':     'Suggestion',
    'concern':        'Concern',
    'harassment':     'Harassment Report',
    'discrimination': 'Discrimination Report',
    'safety':         'Safety Issue',
    'ethics':         'Ethics Violation',
    'general':        'General Message',
}


def migrate(cr, version):
    """
    1. Ensure the category table exists (it may not yet if this is a fresh
       install path — in that case there is nothing to migrate).
    2. For each old category key, find or create the matching category record,
       then UPDATE all messages that have that old value.
    3. Rename the old column to category_legacy so existing data is preserved
       and auditable, but no longer used by the ORM.
    """
    if not version:
        _logger.info("Migration: fresh install detected, skipping category migration.")
        return

    _logger.info("=== HR Anonymous Message: migrating category field → category_id ===")

    # ── 1. Check old column exists ─────────────────────────────────────
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_anonymous_message'
          AND column_name = 'category'
    """)
    if not cr.fetchone():
        _logger.info("Old 'category' column not found — nothing to migrate.")
        return

    # ── 2. Ensure category table exists ───────────────────────────────
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_anonymous_message_category'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("Category table doesn't exist yet — will be created by ORM after migration.")
        # We'll handle this in post-migrate instead
        return

    # ── 3. For each old key, get or create the category record ─────────
    for old_key, category_name in CATEGORY_MAP.items():
        # Find existing category record by name
        cr.execute("""
            SELECT id FROM hr_anonymous_message_category
            WHERE name = %s
            LIMIT 1
        """, (category_name,))
        row = cr.fetchone()

        if row:
            category_id = row[0]
        else:
            # Create it if it doesn't exist yet
            cr.execute("""
                INSERT INTO hr_anonymous_message_category (name, sequence, active)
                VALUES (%s, %s, TRUE)
                RETURNING id
            """, (category_name, 10))
            category_id = cr.fetchone()[0]
            _logger.info(f"Created category: {category_name} (id={category_id})")

        # Update all messages with this old category value
        cr.execute("""
            UPDATE hr_anonymous_message
            SET category_id = %s
            WHERE category = %s
              AND (category_id IS NULL OR category_id = 0)
        """, (category_id, old_key))

        updated = cr.rowcount
        if updated:
            _logger.info(f"  Migrated {updated} messages: '{old_key}' → '{category_name}' (id={category_id})")

    # ── 4. Rename old column to category_legacy ────────────────────────
    # Only rename if category_legacy doesn't already exist
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_anonymous_message'
          AND column_name = 'category_legacy'
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE hr_anonymous_message
            RENAME COLUMN category TO category_legacy
        """)
        _logger.info("Renamed column: category → category_legacy")
    else:
        _logger.info("category_legacy column already exists, skipping rename.")

    _logger.info("=== Category migration complete ===")