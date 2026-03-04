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
            if record.monthly_report_day and (
                record.monthly_report_day < 1 or record.monthly_report_day > 28
            ):
                raise ValidationError('Report day must be between 1 and 28')

    def action_send_test_report(self):
        """
        Manually send a test report for the CURRENT month right now.
        This is completely separate from the cron job:
        - The cron runs automatically on the configured day and sends PREVIOUS month
        - This button sends CURRENT month immediately, on demand, for testing

        The monthly cron behaviour is NOT affected by this button at all.
        """
        self.ensure_one()

        # Validate HR email first
        hr_email = self.hr_anonymous_email or ''
        if not hr_email.strip():
            raise UserError(
                'HR Email Address is not configured. '
                'Please set it above before sending a test report.'
            )

        today = date.today()

        # Current month range (not previous month — this is the test difference)
        month_start = date(today.year, today.month, 1)
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1)
        else:
            month_end = date(today.year, today.month + 1, 1)

        month_name = month_start.strftime('%B %Y')

        # Fetch current month messages
        messages = self.env['hr.anonymous.message'].sudo().search([
            ('create_date', '>=', fields.Datetime.to_string(
                datetime.combine(month_start, datetime.min.time())
            )),
            ('create_date', '<', fields.Datetime.to_string(
                datetime.combine(month_end, datetime.min.time())
            )),
            ('state', '!=', 'draft'),
        ])

        _logger.info(
            f"Test report: {len(messages)} messages found for {month_name}"
        )

        # Use the same Excel generator as the cron
        AnonymousMsg = self.env['hr.anonymous.message']
        try:
            excel_bytes = AnonymousMsg._generate_excel_export(messages)
        except Exception as e:
            raise UserError(f'Failed to generate Excel report: {str(e)}')

        import base64
        filename = f"TEST_Anonymous_Messages_{month_start.strftime('%B_%Y')}.xlsx"

        # Stats
        total       = len(messages)
        resolved    = len(messages.filtered(lambda m: m.state == 'resolved'))
        in_progress = len(messages.filtered(lambda m: m.state == 'in_progress'))
        pending     = len(messages.filtered(lambda m: m.state in ['sent', 'acknowledged']))
        closed      = len(messages.filtered(lambda m: m.state == 'closed'))

        email_body = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;
            background:#f4f4f4;padding:20px;">

  <div style="background:linear-gradient(135deg,#e65100 0%,#ff8f00 100%);
              padding:32px 30px;border-radius:8px 8px 0 0;text-align:center;">
    <div style="font-size:38px;margin-bottom:8px;">🧪</div>
    <h1 style="color:#fff;margin:0;font-size:22px;font-weight:bold;">
      TEST — Anonymous Messages Report
    </h1>
    <p style="color:#ffe0b2;margin:8px 0 0;font-size:13px;">
      {month_name} (Current Month — Manual Test)
    </p>
  </div>

  <div style="background:#fff;padding:30px;
              border-left:1px solid #e0e0e0;border-right:1px solid #e0e0e0;">

    <div style="background:#fff3e0;border:1px solid #ffb74d;border-radius:4px;
                padding:12px 16px;margin-bottom:20px;">
      <p style="margin:0;font-size:13px;color:#e65100;">
        🧪 <strong>This is a TEST email</strong> sent manually from Settings.
        It contains messages from the <strong>current month ({month_name})</strong>.<br/>
        The scheduled monthly cron will continue to run normally on day
        <strong>{self.monthly_report_day}</strong> of each month and will send
        the <strong>previous month's</strong> messages automatically.
      </p>
    </div>

    <p style="font-size:15px;color:#333;margin-top:0;">Dear HR Team,</p>
    <p style="font-size:14px;color:#555;line-height:1.7;">
      Please find attached the <strong>test Excel report</strong> for
      <strong>{month_name}</strong>.
    </p>

    <div style="background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;
                padding:20px;margin:20px 0;">
      <h3 style="margin:0 0 16px;color:#2E5090;font-size:15px;
                 border-bottom:2px solid #2E5090;padding-bottom:8px;">
        📋 Report Summary — {month_name}
      </h3>
      <table style="width:100%;font-size:13px;border-collapse:collapse;">
        <tr>
          <td style="padding:8px 0;color:#888;width:200px;">Total Messages</td>
          <td style="padding:8px 0;font-weight:bold;color:#222;">{total}</td>
        </tr>
        <tr style="border-top:1px solid #f0f0f0;">
          <td style="padding:8px 0;color:#888;">✅ Resolved</td>
          <td style="padding:8px 0;font-weight:bold;color:#2e7d32;">{resolved}</td>
        </tr>
        <tr style="border-top:1px solid #f0f0f0;">
          <td style="padding:8px 0;color:#888;">🔄 In Progress</td>
          <td style="padding:8px 0;font-weight:bold;color:#e65100;">{in_progress}</td>
        </tr>
        <tr style="border-top:1px solid #f0f0f0;">
          <td style="padding:8px 0;color:#888;">⏳ Pending Review</td>
          <td style="padding:8px 0;font-weight:bold;color:#c62828;">{pending}</td>
        </tr>
        <tr style="border-top:1px solid #f0f0f0;">
          <td style="padding:8px 0;color:#888;">🔒 Closed by Employee</td>
          <td style="padding:8px 0;font-weight:bold;color:#555;">{closed}</td>
        </tr>
      </table>
    </div>

    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:4px;
                padding:12px 16px;margin:20px 0;">
      <p style="margin:0;font-size:13px;color:#2e7d32;">
        📎 <strong>Attached:</strong> <em>{filename}</em><br/>
        Contains: <strong>Anonymous Messages</strong> sheet (full list) +
        <strong>Summary</strong> sheet (breakdown).
      </p>
    </div>

    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;
                padding:12px 16px;margin:20px 0;">
      <p style="margin:0;font-size:12px;color:#856404;">
        🛡️ <strong>Privacy Notice:</strong> Sender identities are NOT included.
        All messages remain fully anonymous.
      </p>
    </div>

    <p style="font-size:13px;color:#555;margin-bottom:0;">
      Kind regards,<br/>
      <strong>HR Anonymous Messaging System</strong><br/>
      <span style="color:#aaa;font-size:11px;">Test email sent manually from Settings.</span>
    </p>
  </div>

  <div style="background:#eee;padding:14px;text-align:center;
              border-radius:0 0 8px 8px;border:1px solid #e0e0e0;border-top:none;">
    <p style="margin:0;font-size:11px;color:#999;">
      TEST report generated on {today.strftime('%d %B %Y')} — Confidential HR Document.
    </p>
  </div>
</div>"""

        try:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': filename,
                'datas': base64.b64encode(excel_bytes).decode('utf-8'),
                'mimetype': (
                    'application/vnd.openxmlformats-officedocument'
                    '.spreadsheetml.sheet'
                ),
                'res_model': 'res.config.settings',
                'res_id': 0,
                'type': 'binary',
            })

            mail = self.env['mail.mail'].sudo().create({
                'subject': f'[TEST] Anonymous Messages Report — {month_name}',
                'email_to': hr_email.strip(),
                'email_from': self.env.company.email or hr_email.strip(),
                'body_html': email_body,
                'auto_delete': True,
                'attachment_ids': [(4, attachment.id)],
            })
            mail.sudo().send()
            attachment.sudo().unlink()

            _logger.info(
                f"Test report sent to {hr_email} — "
                f"{total} messages for {month_name}"
            )

        except Exception as e:
            _logger.error(f"Test report failed: {e}")
            raise UserError(f'Failed to send test report: {str(e)}')

        # Show success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test Report Sent!',
                'message': (
                    f'Test report for {month_name} ({total} messages) '
                    f'sent to {hr_email}. Check your inbox.'
                ),
                'type': 'success',
                'sticky': False,
            }
        }