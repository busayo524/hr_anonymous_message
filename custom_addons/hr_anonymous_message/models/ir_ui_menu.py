# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        """
        Override to hide 'All Messages (HR)' from System Admins.
        _visible_menu_ids returns a frozenset in Odoo 19, so we must
        convert to a mutable set, remove the item, return a new frozenset.
        """
        visible = super()._visible_menu_ids(debug=debug)

        try:
            if self.env.user.has_group('base.group_system'):
                hr_menu = self.env.ref(
                    'hr_anonymous_message.menu_anonymous_message_hr',
                    raise_if_not_found=False
                )
                if hr_menu and hr_menu.id in visible:
                    # frozenset is immutable — convert, remove, refreeze
                    visible = frozenset(visible - {hr_menu.id})
        except Exception as e:
            _logger.warning(
                "hr_anonymous_message: Could not filter HR menu: %s", e
            )

        return visible