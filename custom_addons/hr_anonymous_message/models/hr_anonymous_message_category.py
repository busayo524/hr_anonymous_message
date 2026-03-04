# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class HrAnonymousMessageCategory(models.Model):
    """
    Message categories managed by HR/Admin.
    Fully anonymous — this model stores ONLY the category label,
    never any reference to who sent a message.
    """
    _name = 'hr.anonymous.message.category'
    _description = 'Anonymous Message Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Char(string='Description', translate=True)
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color Index', default=0)

    # Count field — shows how many messages use this category
    # (HR/Admin facing only; never exposes sender identity)
    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
    )

    @api.depends('name')
    def _compute_message_count(self):
        counts = self.env['hr.anonymous.message'].sudo().read_group(
            domain=[('category_id', 'in', self.ids)],
            fields=['category_id'],
            groupby=['category_id'],
        )
        count_map = {c['category_id'][0]: c['category_id_count'] for c in counts}
        for record in self:
            record.message_count = count_map.get(record.id, 0)

    def name_get(self):
        return [(rec.id, rec.name) for rec in self]


class HrAnonymousMessagePriority(models.Model):
    """
    Priority levels — kept as a separate model so the searchpanel
    sidebar can display them with live counts.
    Fully anonymous — no sender data stored here.
    """
    _name = 'hr.anonymous.message.priority'
    _description = 'Anonymous Message Priority Level'
    _order = 'sequence'

    name = fields.Char(string='Priority Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    code = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority Code', required=True)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index', default=0)

    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
    )

    @api.depends('code')
    def _compute_message_count(self):
        counts = self.env['hr.anonymous.message'].sudo().read_group(
            domain=[('priority', 'in', self.mapped('code'))],
            fields=['priority'],
            groupby=['priority'],
        )
        count_map = {c['priority']: c['priority_count'] for c in counts}
        for record in self:
            record.message_count = count_map.get(record.code, 0)