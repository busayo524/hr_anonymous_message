# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_anonymous_email = fields.Char(
        string='HR Email for Anonymous Messages',
        config_parameter='hr_anonymous_message.hr_email',
        help='Email address where anonymous messages will be sent'
    )
    
    anonymous_message_auto_send = fields.Boolean(
        string='Auto-send Messages',
        config_parameter='hr_anonymous_message.auto_send',
        default=True,
        help='Automatically send email when anonymous message is created'
    )