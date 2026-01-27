# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrAnonymousMessage(models.Model):
    _name = 'hr.anonymous.message'
    _description = 'Anonymous HR Message'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Subject', 
        required=True, 
        tracking=True
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
    ], string='Category', required=True, default='general', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Audit fields (only visible to admin/compliance)
    sender_user_id = fields.Many2one(
        'res.users', 
        string='Sender (Audit Only)', 
        readonly=True,
        groups='hr.group_hr_manager,base.group_system'
    )
    
    sender_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sender Employee (Audit Only)', 
        readonly=True,
        groups='hr.group_hr_manager,base.group_system'
    )
    
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1')
    
    hr_notes = fields.Text(
        string='HR Notes',
        groups='hr.group_hr_user'
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

    def send_to_hr(self):
        """Send anonymous message to HR via email"""
        self.ensure_one()
        
        # Get HR email from settings
        hr_email = self.env['ir.config_parameter'].sudo().get_param(
            'hr_anonymous_message.hr_email', 
            default='hr@company.com'
        )
        
        if not hr_email or hr_email == 'hr@company.com':
            raise UserError(_('HR email is not configured. Please configure it in Settings > General Settings'))
        
        # Log the sender for audit purposes
        _logger.info(f"Anonymous message '{self.name}' sent by user {self.env.user.name} (ID: {self.env.user.id})")
        
        # Get email template
        template = self.env.ref('hr_anonymous_message.email_template_anonymous_message', raise_if_not_found=False)
        
        if template:
            # Send email using template
            template.send_mail(self.id, force_send=True, email_values={
                'email_to': hr_email,
            })
        else:
            # Fallback: Create email manually
            mail_values = {
                'email_to': hr_email,
                'subject': f'Anonymous Employee Message: {self.name}',
                'body_html': self._prepare_email_body(),
                'email_from': self.env.user.company_id.email or 'noreply@company.com',
                'auto_delete': False,
            }
            
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            self.mail_id = mail.id
        
        # Update state
        self.write({
            'state': 'sent',
            'mail_sent': True,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Your anonymous message has been sent to HR management successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _prepare_email_body(self):
        """Prepare HTML email body"""
        category_label = dict(self._fields['category'].selection).get(self.category, self.category)
        
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd;">
                    <h2 style="color: #2c3e50;">Anonymous Employee Message</h2>
                    
                    <table style="width: 100%; margin: 20px 0;">
                        <tr>
                            <td style="padding: 10px; background-color: #f8f9fa;">
                                <strong>Category:</strong>
                            </td>
                            <td style="padding: 10px;">
                                {category_label}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; background-color: #f8f9fa;">
                                <strong>Subject:</strong>
                            </td>
                            <td style="padding: 10px;">
                                {self.name}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; background-color: #f8f9fa;">
                                <strong>Date:</strong>
                            </td>
                            <td style="padding: 10px;">
                                {fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                            </td>
                        </tr>
                    </table>
                    
                    <hr style="border: 1px solid #ddd; margin: 20px 0;">
                    
                    <div style="margin: 20px 0;">
                        <strong>Message:</strong>
                        <div style="margin-top: 10px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #3498db;">
                            {self.description or ''}
                        </div>
                    </div>
                    
                    <hr style="border: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="color: #7f8c8d; font-size: 12px; font-style: italic;">
                        This message was sent anonymously through the employee portal.<br>
                        The sender's identity is logged for audit purposes but is not revealed in this communication.
                    </p>
                </div>
            </body>
        </html>
        """

    @api.model
    def create(self, vals_list):
        """Override create to log sender information"""
        # Handle both single dict and list of dicts
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        
        for vals in vals_list:
            # Store sender information for audit
            vals['sender_user_id'] = self.env.user.id
            
            # Try to get employee record
            employee = self.env['hr.employee'].sudo().search([
                ('user_id', '=', self.env.user.id)
            ], limit=1)
            
            if employee:
                vals['sender_employee_id'] = employee.id
        
        return super(HrAnonymousMessage, self).create(vals_list)

    def action_acknowledge(self):
        """HR acknowledges receipt of message"""
        self.write({'state': 'acknowledged'})

    def action_in_progress(self):
        """Mark message as being investigated"""
        self.write({'state': 'in_progress'})

    def action_resolve(self):
        """Mark message as resolved"""
        self.write({'state': 'resolved'})

    def action_close(self):
        """Close the message"""
        self.write({'state': 'closed'})