# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'
    
    anonymous_message_count = fields.Integer(
        string='My Anonymous Messages',
        compute='_compute_anonymous_message_count'
    )
    
    def _compute_anonymous_message_count(self):
        for user in self:
            user.anonymous_message_count = self.env['hr.anonymous.message'].search_count([
                ('sender_user_id', '=', user.id)
            ])