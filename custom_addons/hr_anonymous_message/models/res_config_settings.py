# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_anonymous_email = fields.Char(
        string='HR Email for Anonymous Messages',
        config_parameter='hr_anonymous_message.hr_email',
        help='Email address where anonymous messages will be sent'
    )
    
    enable_monthly_report = fields.Boolean(
        string='Send Monthly Excel Reports',
        config_parameter='hr_anonymous_message.enable_monthly_report',
        default=False,
        help='Automatically send Excel report of all anonymous messages to HR email monthly'
    )
    
    monthly_report_day = fields.Integer(
        string='Report Day of Month',
        config_parameter='hr_anonymous_message.monthly_report_day',
        default=1,
        help='Day of the month to send the report (1-28)'
    )
    
    @api.constrains('monthly_report_day')
    def _check_monthly_report_day(self):
        for record in self:
            if record.monthly_report_day and (record.monthly_report_day < 1 or record.monthly_report_day > 28):
                from odoo.exceptions import ValidationError
                raise ValidationError('Report day must be between 1 and 28')
                # raise models.ValidationError('Report day must be between 1 and 28')