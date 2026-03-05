# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, date
import hashlib
import base64
import io

_logger = logging.getLogger(__name__)

class HrAnonymousMessage(models.Model):
    _name = 'hr.anonymous.message'
    _description = 'Anonymous HR Message'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Subject', required=True)
    description = fields.Html(string='Message', required=True)

    category_id = fields.Many2one(
        'hr.anonymous.message.category',
        string='Category',
        required=True,
        ondelete='restrict',
        index=True,
    )
    
    category_legacy = fields.Selection([
        ('complaint', 'Complaint'),
        ('suggestion', 'Suggestion'),
        ('concern', 'Concern'),
        ('harassment', 'Harassment Report'),
        ('discrimination', 'Discrimination Report'),
        ('safety', 'Safety Issue'),
        ('ethics', 'Ethics Violation'),
        ('general', 'General Message'),
    ], string='Category (Legacy)', default='general')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('declined', 'Declined'),
        ('closed', 'Closed by Employee'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    sender_audit_hash = fields.Char(
        string='Audit Hash', readonly=True,
        help='Encrypted audit trail - not viewable in UI'
    )
    sender_user_id = fields.Many2one(
        'res.users', string='Sender', readonly=True, copy=False,
    )
    priority = fields.Selection([
        ('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Urgent'),
    ], string='Priority', default='1')
    
    hr_notes = fields.Text(
        string='HR Internal Notes', groups='hr.group_hr_user', tracking=True
    )
    resolution_notes = fields.Text(
        string='Resolution Notes',
        help='Details about how this message was resolved or why it was declined',
        groups='hr.group_hr_user', tracking=True
    )
    mail_sent = fields.Boolean(string='Email Sent', default=False, readonly=True)
    mail_id = fields.Many2one('mail.mail', string='Email Record', readonly=True)
    is_closed_by_employee = fields.Boolean(
        string='Closed by Employee', default=False, readonly=True
    )
    closed_date = fields.Datetime(string='Closed Date', readonly=True)
    is_my_message = fields.Boolean(
        string='My Message',
        compute='_compute_is_my_message',
        search='_search_is_my_message'
    )

    @api.depends('sender_audit_hash')
    def _compute_is_my_message(self):
        for record in self:
            current_user_hash = self._generate_user_hash(self.env.user.id)
            record.is_my_message = record.sender_audit_hash == current_user_hash

    def _search_is_my_message(self, operator, value):
        current_user_hash = self._generate_user_hash(self.env.user.id)
        if operator == '=' and value:
            return [('sender_audit_hash', '=', current_user_hash)]
        return [('sender_audit_hash', '!=', current_user_hash)]

    def read(self, fields=None, load='_classic_read'):
        """Strip sender_user_id so it is never exposed via RPC"""
        if fields and 'sender_user_id' in fields:
            fields = [f for f in fields if f != 'sender_user_id']
        return super().read(fields=fields, load=load)

    @api.model
    def _generate_user_hash(self, user_id):
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret', default='default_secret_change_in_production'
        )
        return hashlib.sha256(f"{user_id}_{secret}".encode()).hexdigest()

    def message_post(self, **kwargs):
        bot_partner = self.env.ref('base.partner_root')
        kwargs['author_id'] = bot_partner.id
        kwargs.pop('email_from', None)
        return super(HrAnonymousMessage, self.sudo()).message_post(**kwargs)

    def _message_compute_author(self, author_id=None, email_from=None, raise_on_email=True):
        bot_partner = self.env.ref('base.partner_root')
        company_email = self.env.company.email or 'noreply@localhost'
        return bot_partner.id, f"Anonymous HR System <{company_email}>"

    def _message_log(self, **kwargs):
        bot_partner = self.env.ref('base.partner_root')
        kwargs['author_id'] = bot_partner.id
        return super(HrAnonymousMessage, self.sudo())._message_log(**kwargs)

    def _message_notify_by_email(self, message, recipients_data, **kwargs):
        return super(HrAnonymousMessage, self.sudo())._message_notify_by_email(
            message, recipients_data, **kwargs
        )

    def send_to_hr(self):
        """
        Employee submits an anonymous message.

        What this does:
        - Saves the message with state = 'sent'
        - Creates an encrypted audit log entry
        - Notifies HR users inside Odoo (chatter + activity)
        - Does NOT send any email — emails are handled exclusively
          by the monthly cron job (_cron_send_monthly_report)
        """
        self.ensure_one()

        # Validate HR email is configured (needed for monthly cron later)
        ICP = self.env['ir.config_parameter'].sudo()
        hr_email = ICP.get_param('hr_anonymous_message.hr_email', default='').strip()
        if not hr_email:
            raise UserError(_(
                'HR email is not configured. Please ask your administrator to '
                'configure it in Settings → HR Anonymous Messages.'
            ))

        _logger.info(
            f"Anonymous message '{self.name}' submitted — "
            f"Hash: {self.sender_audit_hash[:8]}... (no email sent, monthly cron will handle)"
        )

        # Audit log
        self._create_audit_log()

        # Update state — NO email sent here
        self.write({'state': 'sent', 'mail_sent': False})

        # Notify HR users inside Odoo only
        self._notify_hr_users()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Message Submitted!'),
                'message': _(
                    'Your anonymous message has been submitted to HR. '
                    'You will be notified when its status changes.'
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _create_audit_log(self):
        self.env['hr.anonymous.message.audit'].sudo().create({
            'message_id': self.id,
            'user_hash': self.sender_audit_hash,
            'timestamp': fields.Datetime.now(),
            'action': 'message_sent',
        })

    def _notify_hr_users(self):
        """Notify HR users inside Odoo — no email, fully anonymous"""
        hr_group = self.env.ref('hr.group_hr_user', raise_if_not_found=False)
        if not hr_group:
            return
        hr_users = hr_group.user_ids
        if not hr_users:
            return

        partner_ids = hr_users.mapped('partner_id').ids

        self.sudo().message_post(
            body=_('A new anonymous message has been received: <strong>%s</strong>') % self.name,
            subject=_('New Anonymous Message'),
            partner_ids=partner_ids,
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
        )
        self.sudo().activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('New Anonymous Message: %s') % self.name,
            note=_('Category: %s') % (self.category_id.name if self.category_id else ''),
            user_id=hr_users[0].id,
        )

    def _notify_employee_status_change(self, old_state):
        if old_state != self.state:
            status_label = dict(self._fields['state'].selection).get(self.state)
            self.message_post(
                body=_('Your message "%s" status changed to: %s') % (self.name, status_label),
                subject=_('Message Status Updated'),
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )

    # ── HR workflow actions ───
    def action_acknowledge(self):
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'acknowledged'})
        self._notify_employee_status_change(old_state)
        return True

    def action_in_progress(self):
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'in_progress'})
        self._notify_employee_status_change(old_state)
        return True

    def action_resolve(self):
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'resolved'})
        self._notify_employee_status_change(old_state)
        return True

    def action_decline(self):
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'declined'})
        self._notify_employee_status_change(old_state)
        return True

    def action_close_ticket(self):
        self.ensure_one()
        if not self.is_my_message:
            raise UserError(_('You can only close your own messages.'))
        if self.state == 'draft':
            raise UserError(_('You cannot close a message that has not been sent yet.'))
        self.write({
            'state': 'closed',
            'is_closed_by_employee': True,
            'closed_date': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ticket Closed'),
                'message': _('Your message has been marked as closed.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # ── ORM overrides ───
    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        real_user_id = self.env.user.id
        for vals in vals_list:
            vals['sender_audit_hash'] = self._generate_user_hash(real_user_id)
            vals['sender_user_id'] = real_user_id
        records = super(HrAnonymousMessage, self.sudo()).create(vals_list)
        for record in records:
            self.env.cr.execute(
                "UPDATE hr_anonymous_message SET sender_user_id = %s WHERE id = %s",
                (real_user_id, record.id)
            )
        self.env.cr.flush()
        records.invalidate_recordset(['sender_user_id'])
        return records

    def write(self, vals):
        for record in self:
            old_state = record.state
            res = super(HrAnonymousMessage, record).write(vals)
            if 'state' in vals and old_state != vals['state']:
                record._notify_employee_status_change(old_state)
            return res
        return super(HrAnonymousMessage, self).write(vals)

    @api.constrains('state')
    def _check_state_change_permission(self):
        for record in self:
            if not self.env.user.has_group('hr.group_hr_user') and \
               not self.env.user.has_group('base.group_system'):
                if record.state not in ['draft', 'sent', 'closed']:
                    raise ValidationError(_('Only HR users can change message status.'))

    # ── Excel generation ───
    def _generate_excel_export(self, messages):
        """
        Build a styled two-sheet Excel workbook for the monthly report.
        Sheet 1: full message list (no sender identity).
        Sheet 2: category + status summary.
        """
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            raise UserError(_('openpyxl is required. Run: pip install openpyxl'))

        category_labels = {
            'complaint': 'Complaint', 'suggestion': 'Suggestion',
            'concern': 'Concern', 'harassment': 'Harassment Report',
            'discrimination': 'Discrimination Report', 'safety': 'Safety Issue',
            'ethics': 'Ethics Violation', 'general': 'General Message',
        }
        priority_labels = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Urgent'}
        state_labels = {
            'draft': 'Draft', 'sent': 'Sent', 'acknowledged': 'Acknowledged',
            'in_progress': 'In Progress', 'resolved': 'Resolved',
            'declined': 'Declined', 'closed': 'Closed by Employee',
        }

        thin = Side(style='thin', color='CCCCCC')
        bdr = Border(left=thin, right=thin, top=thin, bottom=thin)
        h_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
        h_fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
        h_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        d_font = Font(name='Arial', size=10)
        d_align = Alignment(vertical='center', wrap_text=True)
        alt_fill = PatternFill(start_color='F0F4F8', end_color='F0F4F8', fill_type='solid')

        wb = openpyxl.Workbook()

        # ── Sheet 1: Messages ──────────────────────────────────────────
        ws = wb.active
        ws.title = "Anonymous Messages"

        headers = [
            'ID', 'Subject', 'Category', 'Priority', 'Status',
            'Date Submitted', 'Date Closed', 'Closed by Employee',
            'HR Notes', 'Resolution Notes',
        ]
        col_widths = [8, 35, 20, 12, 18, 20, 20, 18, 40, 40]

        for col, (hdr, w) in enumerate(zip(headers, col_widths), 1):
            c = ws.cell(row=1, column=col, value=hdr)
            c.font = h_font
            c.fill = h_fill
            c.alignment = h_align
            c.border = bdr
            ws.column_dimensions[c.column_letter].width = w
        ws.row_dimensions[1].height = 30

        for row, msg in enumerate(messages, 2):
            row_data = [
                msg.id,
                msg.name or '',
                msg.category_id.name if msg.category_id else '',
                priority_labels.get(msg.priority, msg.priority or ''),
                state_labels.get(msg.state, msg.state or ''),
                msg.create_date.strftime('%Y-%m-%d %H:%M') if msg.create_date else '',
                msg.closed_date.strftime('%Y-%m-%d %H:%M') if msg.closed_date else '',
                'Yes' if msg.is_closed_by_employee else 'No',
                msg.hr_notes or '',
                msg.resolution_notes or '',
            ]
            use_alt = (row % 2 == 0)
            for col, val in enumerate(row_data, 1):
                c = ws.cell(row=row, column=col, value=val)
                c.font = d_font
                c.alignment = d_align
                c.border = bdr
                if use_alt:
                    c.fill = alt_fill
            ws.row_dimensions[row].height = 20

        # ── Sheet 2: Summary ───────────────────────────────────────────
        ws2 = wb.create_sheet(title="Summary")
        ws2.column_dimensions['A'].width = 25
        ws2.column_dimensions['B'].width = 12
        ws2.column_dimensions['C'].width = 15

        ws2.merge_cells('A1:C1')
        ws2['A1'] = 'Anonymous Messages — Monthly Summary'
        ws2['A1'].font = Font(name='Arial', bold=True, size=14, color='2E5090')
        ws2['A1'].alignment = Alignment(horizontal='center')
        ws2.row_dimensions[1].height = 30

        ws2.merge_cells('A2:C2')
        ws2['A2'] = f'Report Period: {date.today().strftime("%B %Y")}'
        ws2['A2'].font = Font(name='Arial', italic=True, size=10, color='666666')
        ws2['A2'].alignment = Alignment(horizontal='center')

        # Category breakdown
        for col, hdr in enumerate(['Category', 'Count', 'Percentage'], 1):
            c = ws2.cell(row=4, column=col, value=hdr)
            c.font = Font(name='Arial', bold=True, color='FFFFFF')
            c.fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
            c.alignment = Alignment(horizontal='center')
            c.border = bdr

        cat_counts = {}
        for msg in messages:
            lbl = category_labels.get(msg.category, msg.category or 'Unknown')
            cat_counts[lbl] = cat_counts.get(lbl, 0) + 1

        total = len(messages)
        for i, (cat, cnt) in enumerate(cat_counts.items(), 5):
            ws2.cell(row=i, column=1, value=cat).border = bdr
            ws2.cell(row=i, column=2, value=cnt).border = bdr
            pct = ws2.cell(row=i, column=3,
                           value=f'=B{i}/B{5+len(cat_counts)}*100')
            pct.border = bdr
            pct.number_format = '0.0"%"'

        total_row = 5 + len(cat_counts)
        ws2.cell(row=total_row, column=1, value='TOTAL').font = Font(name='Arial', bold=True)
        ws2.cell(row=total_row, column=1).border = bdr
        ws2.cell(row=total_row, column=2,
                 value=f'=SUM(B5:B{total_row-1})').font = Font(name='Arial', bold=True)
        ws2.cell(row=total_row, column=2).border = bdr
        ws2.cell(row=total_row, column=3, value='100%').border = bdr

        # Status breakdown
        ss = total_row + 3
        ws2.merge_cells(f'A{ss}:C{ss}')
        ws2.cell(row=ss, column=1,
                 value='Status Breakdown').font = Font(name='Arial', bold=True, size=11)

        for col, hdr in enumerate(['Status', 'Count', 'Percentage'], 1):
            c = ws2.cell(row=ss + 1, column=col, value=hdr)
            c.font = Font(name='Arial', bold=True, color='FFFFFF')
            c.fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
            c.alignment = Alignment(horizontal='center')
            c.border = bdr

        status_counts = {}
        for msg in messages:
            lbl = state_labels.get(msg.state, msg.state or 'Unknown')
            status_counts[lbl] = status_counts.get(lbl, 0) + 1

        for i, (st, cnt) in enumerate(status_counts.items(), ss + 2):
            ws2.cell(row=i, column=1, value=st).border = bdr
            ws2.cell(row=i, column=2, value=cnt).border = bdr
            ws2.cell(row=i, column=3,
                     value=f'{round(cnt/total*100,1)}%' if total else '0%').border = bdr

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    # ── Monthly cron ───────────────────────────────────────────────────
    @api.model
    def _cron_send_monthly_report(self):
        """
        Scheduled daily. Sends the monthly Excel report to HR on the
        configured day. This is the ONLY email ever sent to HR from
        this module. It contains:
          - A professional HTML email body with message stats
          - An Excel attachment with all messages from the previous month
        """
        _logger.info("=== Monthly Anonymous Messages Report: checking ===")

        ICP = self.env['ir.config_parameter'].sudo()

        # Check enabled
        enable_report = ICP.get_param(
            'hr_anonymous_message.enable_monthly_report', default='False'
        )
        if enable_report not in ('True', '1', 'true'):
            _logger.info("Monthly reports disabled in settings. Skipping.")
            return

        # Check day
        report_day = int(ICP.get_param(
            'hr_anonymous_message.monthly_report_day', default='1'
        ))
        today = date.today()
        if today.day != report_day:
            _logger.info(
                f"Today is day {today.day}, report day is {report_day}. Skipping."
            )
            return

        # Check HR email
        hr_email = ICP.get_param('hr_anonymous_message.hr_email', default='').strip()
        if not hr_email:
            _logger.error("Monthly report: HR email not configured. Aborting.")
            return

        # ── Date range: previous calendar month ───────────────────────
        if today.month == 1:
            report_month, report_year = 12, today.year - 1
        else:
            report_month, report_year = today.month - 1, today.year

        month_start = date(report_year, report_month, 1)
        month_end = date(
            report_year + 1 if report_month == 12 else report_year,
            1 if report_month == 12 else report_month + 1,
            1,
        )

        messages = self.sudo().search([
            ('create_date', '>=', fields.Datetime.to_string(
                datetime.combine(month_start, datetime.min.time())
            )),
            ('create_date', '<', fields.Datetime.to_string(
                datetime.combine(month_end, datetime.min.time())
            )),
            ('state', '!=', 'draft'),
        ])

        month_name = month_start.strftime('%B %Y')
        _logger.info(f"Found {len(messages)} messages for {month_name}")

        # ── Generate Excel ─────────────────────────────────────────────
        try:
            excel_bytes = self._generate_excel_export(messages)
        except Exception as e:
            _logger.error(f"Excel generation failed: {e}")
            _logger.exception("Traceback:")
            return

        filename = f"Anonymous_Messages_{month_start.strftime('%B_%Y')}.xlsx"

        # ── Stats ──────────────────────────────────────────────────────
        total          = len(messages)
        resolved       = len(messages.filtered(lambda m: m.state == 'resolved'))
        in_progress    = len(messages.filtered(lambda m: m.state == 'in_progress'))
        pending        = len(messages.filtered(lambda m: m.state in ['sent', 'acknowledged']))
        closed         = len(messages.filtered(lambda m: m.state == 'closed'))

        email_body = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;
            background:#f4f4f4;padding:20px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#2E5090 0%,#4A90D9 100%);
              padding:32px 30px;border-radius:8px 8px 0 0;text-align:center;">
    <div style="font-size:38px;margin-bottom:8px;">📊</div>
    <h1 style="color:#fff;margin:0;font-size:22px;font-weight:bold;">
      Monthly Anonymous Messages Report
    </h1>
    <p style="color:#d0e4f7;margin:8px 0 0;font-size:13px;">{month_name}</p>
  </div>

  <!-- Body -->
  <div style="background:#fff;padding:30px;
              border-left:1px solid #e0e0e0;border-right:1px solid #e0e0e0;">

    <p style="font-size:15px;color:#333;margin-top:0;">Dear HR Team,</p>
    <p style="font-size:14px;color:#555;line-height:1.7;">
      Please find attached the <strong>monthly Excel report</strong> for
      <strong>{month_name}</strong>, automatically generated by the
      HR Anonymous Messaging System.
    </p>

    <!-- Stats card -->
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

    <!-- Attachment notice -->
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:4px;
                padding:12px 16px;margin:20px 0;">
      <p style="margin:0;font-size:13px;color:#2e7d32;">
        📎 <strong>Attached:</strong> <em>{filename}</em><br/>
        Contains two sheets:
        <strong>Anonymous Messages</strong> (full list) and
        <strong>Summary</strong> (category &amp; status breakdown).
      </p>
    </div>

    <!-- Privacy notice -->
    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;
                padding:12px 16px;margin:20px 0;">
      <p style="margin:0;font-size:12px;color:#856404;">
        🛡️ <strong>Privacy Notice:</strong> Sender identities are NOT included.
        All messages remain fully anonymous in compliance with company policy.
      </p>
    </div>

    <p style="font-size:13px;color:#555;margin-bottom:0;line-height:1.6;">
      Kind regards,<br/>
      <strong>HR Anonymous Messaging System</strong><br/>
      <span style="color:#aaa;font-size:11px;">
        Automated message — please do not reply.
      </span>
    </p>
  </div>

  <!-- Footer -->
  <div style="background:#eee;padding:14px;text-align:center;
              border-radius:0 0 8px 8px;border:1px solid #e0e0e0;border-top:none;">
    <p style="margin:0;font-size:11px;color:#999;">
      Generated on {today.strftime('%d %B %Y')} — Confidential HR Document.
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
                'res_model': 'hr.anonymous.message',
                'res_id': 0,
                'type': 'binary',
            })
            _logger.info(f"Attachment created: id={attachment.id}, name={filename}")

            mail = self.env['mail.mail'].sudo().create({
                'subject': f'Monthly Anonymous Messages Report — {month_name}',
                'email_to': hr_email,
                'email_from': self.env.company.email or hr_email,
                'body_html': email_body,
                'auto_delete': True,
                'attachment_ids': [(4, attachment.id)],
            })
            _logger.info(f"Mail record created: id={mail.id}")

            mail.sudo().send()
            _logger.info(
                f"Monthly report sent to {hr_email} — "
                f"{total} messages, attachment: {filename}"
            )

            # Unlink attachment after sending to keep DB clean
            attachment.sudo().unlink()

        except Exception as e:
            _logger.error(f"Failed to send monthly report email: {e}")
            _logger.exception("Traceback:")


class HrAnonymousMessageAudit(models.Model):
    """Separate audit log table — NOT accessible via UI"""
    _name = 'hr.anonymous.message.audit'
    _description = 'Anonymous Message Audit Log (Encrypted)'
    _rec_name = 'message_id'

    message_id = fields.Many2one(
        'hr.anonymous.message', string='Message',
        required=True, ondelete='cascade'
    )
    user_hash = fields.Char(
        string='User Hash', required=True,
        help='Encrypted — cannot be reversed without system secret'
    )
    timestamp = fields.Datetime(string='Timestamp', required=True)
    action = fields.Char(string='Action', required=True)