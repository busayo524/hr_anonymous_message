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

    name = fields.Char(
        string='Subject', 
        required=True,
    )
    
    description = fields.Html(
        string='Message', 
        required=True
    )
    
    category = fields.Selection([
        ('complaint', 'Complaint'),
        ('suggestion', 'Suggestion'),
        ('concern', 'Concern'),
        ('harassment', 'Harassment Report'),
        ('discrimination', 'Discrimination Report'),
        ('safety', 'Safety Issue'),
        ('ethics', 'Ethics Violation'),
        ('general', 'General Message'),
    ], string='Category', required=True, default='general')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('declined', 'Declined'),
        ('closed', 'Closed by Employee'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Audit trail is stored encrypted in separate table
    sender_audit_hash = fields.Char(
        string='Audit Hash', 
        readonly=True,
        help='Encrypted audit trail - not viewable in UI'
    )

    sender_user_id = fields.Many2one(
        'res.users',
        string='Sender',
        readonly=True,
        copy=False,
    )
    
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1')
    
    hr_notes = fields.Text(
        string='HR Internal Notes',
        groups='hr.group_hr_user',
        tracking=True
    )
    
    resolution_notes = fields.Text(
        string='Resolution Notes',
        help='Details about how this message was resolved or why it was declined',
        groups='hr.group_hr_user',
        tracking=True
    )
    
    mail_sent = fields.Boolean(
        string='Email Sent',
        default=False,
        readonly=True
    )
    
    mail_id = fields.Many2one(
        'mail.mail',
        string='Email Record',
        readonly=True
    )
    
    is_closed_by_employee = fields.Boolean(
        string='Closed by Employee',
        default=False,
        readonly=True
    )
    
    closed_date = fields.Datetime(
        string='Closed Date',
        readonly=True
    )
    
    # Computed field to check if current user is the sender
    # Uses encrypted comparison
    is_my_message = fields.Boolean(
        string='My Message',
        compute='_compute_is_my_message',
        search='_search_is_my_message'
    )
    
    @api.depends('sender_audit_hash')
    def _compute_is_my_message(self):
        """Check if current user is sender using hash comparison"""
        for record in self:
            current_user_hash = self._generate_user_hash(self.env.user.id)
            record.is_my_message = record.sender_audit_hash == current_user_hash
    
    def _search_is_my_message(self, operator, value):
        """Search for user's own messages using hash"""
        current_user_hash = self._generate_user_hash(self.env.user.id)
        if operator == '=' and value:
            return [('sender_audit_hash', '=', current_user_hash)]
        return [('sender_audit_hash', '!=', current_user_hash)]
    
    def read(self, fields=None, load='_classic_read'):
        """Override read to always strip sender_user_id from results"""
        if fields and 'sender_user_id' in fields:
            fields = [f for f in fields if f != 'sender_user_id']
        return super().read(fields=fields, load=load)
    
    @api.model
    def _generate_user_hash(self, user_id):
        """Generate hash for user ID (for audit purposes only)"""
        # Create hash using user ID + system secret
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret', 
            default='default_secret_change_in_production'
        )
        hash_string = f"{user_id}_{secret}"
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    def message_post(self, **kwargs):
        """Always post chatter messages as OdooBot, never as real user"""
        bot_partner = self.env.ref('base.partner_root')
        kwargs['author_id'] = bot_partner.id
        kwargs.pop('email_from', None)
        return super(HrAnonymousMessage, self.sudo()).message_post(**kwargs)

    def _message_compute_author(self, author_id=None, email_from=None, raise_on_email=True):
        """Force all messages to appear from anonymous system identity"""
        bot_partner = self.env.ref('base.partner_root')
        company_email = self.env.company.email or 'noreply@localhost'
        return bot_partner.id, f"Anonymous HR System <{company_email}>"
    
    def _message_log(self, **kwargs):
        """Override to ensure all internal logs are anonymous"""
        bot_partner = self.env.ref('base.partner_root')
        kwargs['author_id'] = bot_partner.id
        return super(HrAnonymousMessage, self.sudo())._message_log(**kwargs)
    
    # I REPLACED _message_log_mail_sent WITH THIS to log email log:
    def _message_notify_by_email(self, message, recipients_data, **kwargs):
        """Odoo 19 - block email log from appearing in chatter"""
        return super(HrAnonymousMessage, self.sudo())._message_notify_by_email(
            message, recipients_data, **kwargs
        )

    def send_to_hr(self):
        """Send anonymous message to HR via email and notification"""
        self.ensure_one()
        
        # Get HR email from settings
        ICP = self.env['ir.config_parameter'].sudo()
        hr_email = ICP.get_param('hr_anonymous_message.hr_email', default='').strip()

        # Debug logging
        _logger.info(f"=== ANONYMOUS MESSAGE DEBUG ===")
        _logger.info(f"Retrieved HR email from settings: '{hr_email}'")
        
        if not hr_email:
            raise UserError(_('HR email is not configured. Please ask your administrator to configure it in Settings → HR Anonymous Messages.'))
        
        # Log for audit - NO user identification in logs
        _logger.info(f"Anonymous message '{self.name}' sent - Hash: {self.sender_audit_hash[:8]}...")
        
        # Create audit log in separate table (not visible in UI)
        self._create_audit_log()

        # Get the email template
        template = self.env.ref('hr_anonymous_message.email_template_anonymous_message', raise_if_not_found=False)
        
        if not template:
            _logger.error("Email template 'hr_anonymous_message.email_template_anonymous_message' not found!")
            raise UserError(_('Email template not found. Please contact your administrator.'))
        
        _logger.info(f"Template found: {template.name}")
        _logger.info(f"Sending email to: {hr_email}")
        
        try:
            # Generate email body from template without logging to chatter
            # Use sudo context to render template
            template_sudo = template.sudo()
            
            body = template_sudo._render_field(
                'body_html', 
                self.ids,
                compute_lang=True
            )[self.id]
            
            subject = template_sudo._render_field(
                'subject',
                self.ids,
                compute_lang=True
            )[self.id]

            # Create mail directly — no chatter logging
            mail_values = {
                'subject': subject,
                'email_to': hr_email,
                'email_from': self.env.company.email or 'noreply@localhost',
                'body_html': body,
                'auto_delete': True,
                # No res_id or model — this prevents chatter logging entirely
            }
            
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.sudo().send()
            
            _logger.info(f"Email sent anonymously to: {hr_email}")
            mail_sent = True

        except Exception as e:
            _logger.error(f"Failed to send email: {str(e)}")
            _logger.exception("Full traceback:")
            mail_sent = False
            raise UserError(_(
                'Failed to send email: %s\n\nPlease check:\n'
                '1. Outgoing Mail Server is configured\n'
                '2. HR email is valid\n'
                '3. Check logs for details'
            ) % str(e))
        
        # Update state
        self.write({
            'state': 'sent',
            'mail_sent': True,
        })
        
        # Notify all HR users via Odoo notification
        self._notify_hr_users()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success!'),
                'message': _('Your anonymous message has been sent to HR management %s') % hr_email,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
    
    def _create_audit_log(self):
        """Create encrypted audit log (for legal compliance only)"""
        # Store in separate table that's not accessible via UI
        self.env['hr.anonymous.message.audit'].sudo().create({
            'message_id': self.id,
            'user_hash': self.sender_audit_hash,
            'timestamp': fields.Datetime.now(),
            'action': 'message_sent'
        })
        
    def _notify_hr_users(self):
        """Send Odoo notification to all HR users - fully anonymous"""
        hr_group = self.env.ref('hr.group_hr_user', raise_if_not_found=False)
        if not hr_group:
            return

        hr_users = hr_group.user_ids
        if not hr_users:
            return

        partner_ids = hr_users.mapped('partner_id').ids

        # One post to all HR partners — message_post override handles anonymity
        self.sudo().message_post(
            body=_('A new anonymous message has been received: <strong>%s</strong>') % self.name,
            subject=_('New Anonymous Message'),
            partner_ids=partner_ids,
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
        )

        if hr_users:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('New Anonymous Message: %s') % self.name,
                note=_('Category: %s') % dict(self._fields['category'].selection).get(self.category),
                user_id=hr_users[0].id,
            )

    
    def _notify_employee_status_change(self, old_state):
        """Notify employee when HR changes status"""
        if old_state != self.state:
            # Find the employee using hash comparison
            # Send notification without revealing identity
            status_label = dict(self._fields['state'].selection).get(self.state)
            
            # Post message that only the sender can see
            self.message_post(
                body=_('Your message "%s" status changed to: %s') % (self.name, status_label),
                subject=_('Message Status Updated'),
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )

    # HR Action Methods
    def action_acknowledge(self):
        """HR acknowledges receipt"""
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'acknowledged'})
        self._notify_employee_status_change(old_state)
        return True

    def action_in_progress(self):
        """Mark as in progress"""
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'in_progress'})
        self._notify_employee_status_change(old_state)
        return True

    def action_resolve(self):
        """Mark as resolved"""
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'resolved'})
        self._notify_employee_status_change(old_state)
        return True

    def action_decline(self):
        """Decline the message"""
        self.ensure_one()
        old_state = self.state
        self.write({'state': 'declined'})
        self._notify_employee_status_change(old_state)
        return True
    
    # Employee Action
    def action_close_ticket(self):
        """Employee closes their own ticket"""
        self.ensure_one()
        
        # Check using hash comparison
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

    @api.model
    def create(self, vals_list):
        """Override create to generate audit hash"""
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        real_user_id = self.env.user.id
        
        for vals in vals_list:
            vals['sender_audit_hash'] = self._generate_user_hash(real_user_id)
            vals['sender_user_id'] = real_user_id
            
        records = super(HrAnonymousMessage, self.sudo()).create(vals_list)

         # Force correct sender_user_id via SQL since sudo() may override it
        for record in records:
            self.env.cr.execute(
                "UPDATE hr_anonymous_message SET sender_user_id = %s WHERE id = %s",
                (real_user_id, record.id)
            )

        # Force ORM to re-read from DB, not cache
        self.env.cr.flush()
        records.invalidate_recordset(['sender_user_id'])

        return records
    
    def write(self, vals):
        """Track status changes for notifications"""
        for record in self:
            old_state = record.state
            res = super(HrAnonymousMessage, record).write(vals)
            if 'state' in vals and old_state != vals['state']:
                record._notify_employee_status_change(old_state)
            return res
        return super(HrAnonymousMessage, self).write(vals)
    
    @api.constrains('state')
    def _check_state_change_permission(self):
        """Only HR can change status (except employee closing)"""
        for record in self:
            if not self.env.user.has_group('hr.group_hr_user') and \
               not self.env.user.has_group('base.group_system'):
                if record.state not in ['draft', 'sent', 'closed']:
                    raise ValidationError(_('Only HR users can change message status.'))
                


    def _generate_excel_export(self, messages):
        """Generate Excel export identical to Odoo's Export All functionality"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            raise UserError(_('openpyxl library is required. Install it with: pip install openpyxl'))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Anonymous Messages"

        header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
        header_fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
        header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        data_font = Font(name='Arial', size=10)
        data_align = Alignment(vertical='center', wrap_text=True)
        alt_fill = PatternFill(start_color='F0F4F8', end_color='F0F4F8', fill_type='solid')
        thin_side = Side(style='thin', color='CCCCCC')
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        headers = [
            'ID', 'Subject', 'Category', 'Priority', 'Status',
            'Date Submitted', 'Date Closed', 'Closed by Employee',
            'Email Sent', 'HR Notes', 'Resolution Notes'
        ]
        col_widths = [8, 35, 20, 12, 18, 20, 20, 18, 12, 40, 40]

        for col_num, (header, width) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = cell_border
            ws.column_dimensions[ws.cell(row=1, column=col_num).column_letter].width = width
        ws.row_dimensions[1].height = 30

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

        for row_num, msg in enumerate(messages, 2):
            row_data = [
                msg.id,
                msg.name or '',
                category_labels.get(msg.category, msg.category or ''),
                priority_labels.get(msg.priority, msg.priority or ''),
                state_labels.get(msg.state, msg.state or ''),
                msg.create_date.strftime('%Y-%m-%d %H:%M') if msg.create_date else '',
                msg.closed_date.strftime('%Y-%m-%d %H:%M') if msg.closed_date else '',
                'Yes' if msg.is_closed_by_employee else 'No',
                'Yes' if msg.mail_sent else 'No',
                msg.hr_notes or '',
                msg.resolution_notes or '',
            ]
            use_alt = (row_num % 2 == 0)
            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.font = data_font
                cell.alignment = data_align
                cell.border = cell_border
                if use_alt:
                    cell.fill = alt_fill
            ws.row_dimensions[row_num].height = 20

        # Summary Sheet
        ws_summary = wb.create_sheet(title="Summary")
        ws_summary['A1'] = 'Anonymous Messages - Monthly Summary'
        ws_summary['A1'].font = Font(name='Arial', bold=True, size=14, color='2E5090')
        ws_summary.merge_cells('A1:C1')
        ws_summary['A1'].alignment = Alignment(horizontal='center')
        ws_summary.row_dimensions[1].height = 30
        ws_summary['A2'] = f'Report Period: {date.today().strftime("%B %Y")}'
        ws_summary['A2'].font = Font(name='Arial', italic=True, size=10, color='666666')
        ws_summary.merge_cells('A2:C2')
        ws_summary['A2'].alignment = Alignment(horizontal='center')

        for col, header in enumerate(['Category', 'Count', 'Percentage'], 1):
            cell = ws_summary.cell(row=4, column=col, value=header)
            cell.font = Font(name='Arial', bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
            cell.border = cell_border

        ws_summary.column_dimensions['A'].width = 25
        ws_summary.column_dimensions['B'].width = 12
        ws_summary.column_dimensions['C'].width = 15

        category_counts = {}
        for msg in messages:
            label = category_labels.get(msg.category, msg.category or 'Unknown')
            category_counts[label] = category_counts.get(label, 0) + 1

        total = len(messages)
        for row_idx, (cat, count) in enumerate(category_counts.items(), 5):
            ws_summary.cell(row=row_idx, column=1, value=cat).border = cell_border
            ws_summary.cell(row=row_idx, column=2, value=count).border = cell_border
            pct_cell = ws_summary.cell(row=row_idx, column=3,
                                        value=f'=B{row_idx}/B{5+len(category_counts)}*100')
            pct_cell.border = cell_border
            pct_cell.number_format = '0.0"%"'

        total_row = 5 + len(category_counts)
        ws_summary.cell(row=total_row, column=1, value='TOTAL').font = Font(name='Arial', bold=True)
        ws_summary.cell(row=total_row, column=1).border = cell_border
        ws_summary.cell(row=total_row, column=2,
                        value=f'=SUM(B5:B{total_row-1})').font = Font(name='Arial', bold=True)
        ws_summary.cell(row=total_row, column=2).border = cell_border
        ws_summary.cell(row=total_row, column=3, value='100%').border = cell_border

        # Status breakdown
        status_start = total_row + 3
        ws_summary.cell(row=status_start, column=1,
                        value='Status Breakdown').font = Font(name='Arial', bold=True, size=11)
        ws_summary.merge_cells(f'A{status_start}:C{status_start}')

        for col, header in enumerate(['Status', 'Count', 'Percentage'], 1):
            cell = ws_summary.cell(row=status_start + 1, column=col, value=header)
            cell.font = Font(name='Arial', bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color='2E5090', end_color='2E5090', fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
            cell.border = cell_border

        status_counts = {}
        for msg in messages:
            label = state_labels.get(msg.state, msg.state or 'Unknown')
            status_counts[label] = status_counts.get(label, 0) + 1

        for row_idx, (status, count) in enumerate(status_counts.items(), status_start + 2):
            ws_summary.cell(row=row_idx, column=1, value=status).border = cell_border
            ws_summary.cell(row=row_idx, column=2, value=count).border = cell_border
            ws_summary.cell(row=row_idx, column=3,
                            value=f'{round(count/total*100, 1)}%' if total > 0 else '0%').border = cell_border

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    @api.model
    def _cron_send_monthly_report(self):
        """Cron job: Generate and email monthly Excel report to HR"""
        _logger.info("=== Starting Monthly Anonymous Messages Report ===")

        ICP = self.env['ir.config_parameter'].sudo()

        enable_report = ICP.get_param('hr_anonymous_message.enable_monthly_report', default='False')
        if enable_report not in ('True', '1', 'true'):
            _logger.info("Monthly reports disabled in settings. Skipping.")
            return

        report_day = int(ICP.get_param('hr_anonymous_message.monthly_report_day', default='1'))
        today = date.today()
        if today.day != report_day:
            _logger.info(f"Today is day {today.day}, report day is {report_day}. Skipping.")
            return

        hr_email = ICP.get_param('hr_anonymous_message.hr_email', default='').strip()
        if not hr_email:
            _logger.error("Monthly report: HR email not configured. Aborting.")
            return

        # Get messages from previous month
        if today.month == 1:
            report_month, report_year = 12, today.year - 1
        else:
            report_month, report_year = today.month - 1, today.year

        month_start = date(report_year, report_month, 1)
        month_end = date(
            report_year + (1 if report_month == 12 else 0),
            1 if report_month == 12 else report_month + 1,
            1
        )

        messages = self.sudo().search([
            ('create_date', '>=', fields.Datetime.to_string(
                datetime.combine(month_start, datetime.min.time()))),
            ('create_date', '<', fields.Datetime.to_string(
                datetime.combine(month_end, datetime.min.time()))),
            ('state', '!=', 'draft'),
        ])

        month_name = month_start.strftime('%B %Y')
        _logger.info(f"Monthly report: Found {len(messages)} messages for {month_name}")

        excel_data = self._generate_excel_export(messages)
        filename = f"Anonymous_Messages_Report_{month_start.strftime('%Y_%m')}.xlsx"

        resolved_count = len(messages.filtered(lambda m: m.state == 'resolved'))
        in_progress_count = len(messages.filtered(lambda m: m.state == 'in_progress'))
        pending_count = len(messages.filtered(lambda m: m.state in ['sent', 'acknowledged']))

        email_body = f"""
<div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #2E5090 0%, #4A90D9 100%); padding: 30px; border-radius: 8px 8px 0 0; text-align: center;">
        <h1 style="color: #ffffff; margin: 0; font-size: 22px;">Monthly Anonymous Messages Report</h1>
        <p style="color: #d0e4f7; margin: 8px 0 0 0; font-size: 14px;">{month_name}</p>
    </div>
    <div style="background: #f9f9f9; padding: 30px; border: 1px solid #e0e0e0;">
        <p style="font-size: 15px; color: #333;">Dear HR Team,</p>
        <p style="font-size: 14px; color: #555; line-height: 1.6;">
            Please find attached the <strong>monthly report of all anonymous messages</strong> submitted
            by employees during <strong>{month_name}</strong>. This report has been automatically
            generated by the HR Anonymous Messaging System.
        </p>
        <div style="background: #ffffff; border-left: 4px solid #2E5090; padding: 15px 20px; margin: 20px 0; border-radius: 0 4px 4px 0;">
            <h3 style="margin: 0 0 12px 0; color: #2E5090; font-size: 14px;">Report Summary</h3>
            <table style="width: 100%; font-size: 13px;">
                <tr><td style="padding: 5px 0; color: #666;">Report Period:</td>
                    <td style="font-weight: bold; color: #333;">{month_name}</td></tr>
                <tr><td style="padding: 5px 0; color: #666;">Total Messages:</td>
                    <td style="font-weight: bold; color: #333;">{len(messages)}</td></tr>
                <tr><td style="padding: 5px 0; color: #666;">Resolved:</td>
                    <td style="font-weight: bold; color: #008000;">{resolved_count}</td></tr>
                <tr><td style="padding: 5px 0; color: #666;">In Progress:</td>
                    <td style="font-weight: bold; color: #FF8C00;">{in_progress_count}</td></tr>
                <tr><td style="padding: 5px 0; color: #666;">Pending Review:</td>
                    <td style="font-weight: bold; color: #DC143C;">{pending_count}</td></tr>
            </table>
        </div>
        <p style="font-size: 14px; color: #555; line-height: 1.6;">
            The attached Excel file contains two sheets:<br>
            <strong>Sheet 1 - Anonymous Messages:</strong> Full list with subject, category, priority, status and resolution notes.<br>
            <strong>Sheet 2 - Summary:</strong> Breakdown by category and status with percentages.
        </p>
        <div style="background: #fff3cd; border: 1px solid #ffc107; padding: 12px 16px; border-radius: 4px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #856404;">
                <strong>Privacy Notice:</strong> Sender identities are NOT included in this report.
                All messages remain fully anonymous in compliance with company policy.
            </p>
        </div>
        <p style="font-size: 14px; color: #555; margin-bottom: 0;">
            Kind regards,<br>
            <strong>HR Anonymous Messaging System</strong><br>
            <span style="color: #888; font-size: 12px;">This is an automated message. Please do not reply.</span>
        </p>
    </div>
    <div style="background: #f0f0f0; padding: 12px; text-align: center; border-radius: 0 0 8px 8px;">
        <p style="margin: 0; font-size: 11px; color: #999;">
            Generated automatically on {today.strftime('%d %B %Y')} - Confidential HR Document
        </p>
    </div>
</div>
        """

        mail_values = {
            'subject': f'Monthly Anonymous Messages Report - {month_name}',
            'email_to': hr_email,
            'email_from': hr_email,
            'body_html': email_body,
            'attachment_ids': [(0, 0, {
                'name': filename,
                'datas': base64.b64encode(excel_data).decode('utf-8'),
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })],
        }

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.sudo().send()
        _logger.info(f"Monthly report sent to {hr_email} with {len(messages)} messages attached.")


class HrAnonymousMessageAudit(models.Model):
    """Separate audit log table - NOT accessible via UI"""
    _name = 'hr.anonymous.message.audit'
    _description = 'Anonymous Message Audit Log (Encrypted)'
    _rec_name = 'message_id'
    
    message_id = fields.Many2one(
        'hr.anonymous.message',
        string='Message',
        required=True,
        ondelete='cascade'
    )
    
    user_hash = fields.Char(
        string='User Hash',
        required=True,
        help='Encrypted user identifier - cannot be reversed without system secret'
    )
    
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True
    )
    
    action = fields.Char(
        string='Action',
        required=True
    )
    
    # NO UI access - only database access for legal compliance