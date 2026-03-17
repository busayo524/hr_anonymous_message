# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)


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
        help='Automatically send report of all anonymous messages to HR email monthly'
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
            if record.monthly_report_day and (
                record.monthly_report_day < 1 or record.monthly_report_day > 28
            ):
                raise ValidationError('Report day must be between 1 and 28')

    def action_send_test_report(self):
        self.ensure_one()

        hr_email = self.hr_anonymous_email or ''
        if not hr_email.strip():
            raise UserError(
                'HR Email Address is not configured. '
                'Please set it above before sending a test report.'
            )

        today = date.today()
        month_start = date(today.year, today.month, 1)
        month_end = (
            date(today.year + 1, 1, 1) if today.month == 12
            else date(today.year, today.month + 1, 1)
        )
        month_name = month_start.strftime('%B %Y')

        messages = self.env['hr.anonymous.message'].sudo().search([
            ('create_date', '>=', fields.Datetime.to_string(
                datetime.combine(month_start, datetime.min.time())
            )),
            ('create_date', '<', fields.Datetime.to_string(
                datetime.combine(month_end, datetime.min.time())
            )),
            ('state', '!=', 'draft'),
        ])

        email_body = self.env['hr.anonymous.message']._build_statistics_email(
            messages, month_name, today, is_test=True
        )

        try:
            mail = self.env['mail.mail'].sudo().create({
                'subject': f'[TEST] 📊 HR Anonymous Messages Report — {month_name}',
                'email_to': hr_email.strip(),
                'email_from': self.env.company.email or hr_email.strip(),
                'body_html': email_body,
                'auto_delete': True,
            })
            mail.sudo().send()
        except Exception as e:
            raise UserError(f'Failed to send test report: {str(e)}')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '📊 Test Report Sent!',
                'message': (
                    f'Statistics report for {month_name} ({len(messages)} messages) '
                    f'sent to {hr_email}.'
                ),
                'type': 'success',
                'sticky': False,
            }
        }