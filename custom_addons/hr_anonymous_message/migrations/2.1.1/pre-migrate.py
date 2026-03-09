# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Add date_period column and populate existing records."""

    _logger.info("=== HR Anonymous Message: adding date_period column ===")

    cr.execute("""
        ALTER TABLE hr_anonymous_message
        ADD COLUMN IF NOT EXISTS date_period VARCHAR;
    """)

    cr.execute("""
        UPDATE hr_anonymous_message
        SET date_period = CASE
            WHEN create_date::date = CURRENT_DATE
                THEN 'today'
            WHEN create_date::date >= date_trunc('week', CURRENT_DATE)::date
                THEN 'this_week'
            WHEN create_date::date >= date_trunc('month', CURRENT_DATE)::date
                THEN 'this_month'
            WHEN create_date::date >= (date_trunc('month', CURRENT_DATE) - INTERVAL '1 month')::date
                THEN 'last_month'
            ELSE 'older'
        END
        WHERE date_period IS NULL;
    """)

    _logger.info("=== date_period column added and populated ===")