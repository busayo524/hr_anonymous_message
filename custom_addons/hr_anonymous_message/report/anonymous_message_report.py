# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta
import base64
import io
import logging

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

_logger = logging.getLogger(__name__)

class HrAnonymousMessage(models.Model):
    _inherit = 'hr.anonymous.message'
    
    @api.model
    def _generate_and_send_monthly_report(self):
        """Generate Excel report and send via email"""
        if not xlsxwriter:
            _logger.error('xlsxwriter library not installed. Cannot generate Excel report.')
            return
        
        # Get last month's data
        today = datetime.now()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        
        # Fetch messages from last month
        messages = self.search([
            ('create_date', '>=', first_day_last_month),
            ('create_date', '<=', last_day_last_month),
            ('state', '!=', 'draft')
        ], order='create_date desc')
        
        if not messages:
            _logger.info('No messages to report for last month.')
            return
        
        # Generate Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Anonymous Messages Report')
        
        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4A5568',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })
        
        cell_format = workbook.add_format({
            'border': 1,
            'valign': 'vcenter',
            'text_wrap': True
        })
        
        date_format = workbook.add_format({
            'border': 1,
            'valign': 'vcenter',
            'num_format': 'yyyy-mm-dd hh:mm'
        })
        
        # Status color formats
        status_formats = {
            'sent': workbook.add_format({'bg_color': '#E3F2FD', 'border': 1}),
            'acknowledged': workbook.add_format({'bg_color': '#FFF9C4', 'border': 1}),
            'in_progress': workbook.add_format({'bg_color': '#FFE0B2', 'border': 1}),
            'resolved': workbook.add_format({'bg_color': '#C8E6C9', 'border': 1}),
            'declined': workbook.add_format({'bg_color': '#FFCDD2', 'border': 1}),
            'closed': workbook.add_format({'bg_color': '#E0E0E0', 'border': 1}),
        }
        
        # Title
        worksheet.merge_range('A1:H1', 
            f'Anonymous Messages Report - {first_day_last_month.strftime("%B %Y")}',
            workbook.add_format({
                'bold': True,
                'font_size': 16,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#667eea',
                'font_color': 'white'
            })
        )
        
        # Set column widths
        worksheet.set_column('A:A', 20)  # Date
        worksheet.set_column('B:B', 15)  # Category
        worksheet.set_column('C:C', 30)  # Subject
        worksheet.set_column('D:D', 12)  # Priority
        worksheet.set_column('E:E', 15)  # Status
        worksheet.set_column('F:F', 40)  # Resolution Notes
        worksheet.set_column('G:G', 15)  # Employee Closed
        worksheet.set_column('H:H', 20)  # Closed Date
        
        # Headers
        headers = [
            'Date & Time Sent',
            'Category',
            'Subject',
            'Priority',
            'Status',
            'Resolution Notes',
            'Employee Closed',
            'Closed Date'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(2, col, header, header_format)
        
        # Data rows
        row = 3
        for msg in messages:
            # Category labels
            category_dict = dict(msg._fields['category'].selection)
            priority_dict = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Urgent'}
            state_dict = dict(msg._fields['state'].selection)
            
            worksheet.write_datetime(row, 0, msg.create_date, date_format)
            worksheet.write(row, 1, category_dict.get(msg.category, msg.category), cell_format)
            worksheet.write(row, 2, msg.name, cell_format)
            worksheet.write(row, 3, priority_dict.get(msg.priority, 'Normal'), cell_format)
            worksheet.write(row, 4, state_dict.get(msg.state, msg.state), 
                          status_formats.get(msg.state, cell_format))
            worksheet.write(row, 5, msg.resolution_notes or '', cell_format)
            worksheet.write(row, 6, 'Yes' if msg.is_closed_by_employee else 'No', cell_format)
            worksheet.write(row, 7, msg.closed_date.strftime('%Y-%m-%d %H:%M') if msg.closed_date else '', cell_format)
            
            row += 1
        
        # Summary section
        row += 2
        worksheet.merge_range(row, 0, row, 1, 'SUMMARY STATISTICS', header_format)
        row += 1
        
        # Count by status
        status_counts = {}
        for msg in messages:
            status_counts[msg.state] = status_counts.get(msg.state, 0) + 1
        
        worksheet.write(row, 0, 'Total Messages:', workbook.add_format({'bold': True}))
        worksheet.write(row, 1, len(messages))
        row += 1
        
        for state, count in status_counts.items():
            state_label = dict(messages._fields['state'].selection).get(state, state)
            worksheet.write(row, 0, f'{state_label}:', cell_format)
            worksheet.write(row, 1, count, status_formats.get(state, cell_format))
            row += 1
        
        # Close workbook
        workbook.close()
        output.seek(0)
        
        # Encode to base64
        excel_data = base64.b64encode(output.read())
        output.close()
        
        # Send email with attachment
        hr_email = self.env['ir.config_parameter'].sudo().get_param(
            'hr_anonymous_message.hr_email', 
            default=''
        )
        
        if not hr_email:
            _logger.warning('HR email not configured. Cannot send monthly report.')
            return
        
        # Create attachment
        filename = f'Anonymous_Messages_Report_{first_day_last_month.strftime("%B_%Y")}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': excel_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        # Send email
        mail_values = {
            'subject': f'📊 Monthly Anonymous Messages Report - {first_day_last_month.strftime("%B %Y")}',
            'body_html': self._get_monthly_report_email_body(messages, first_day_last_month),
            'email_to': hr_email,
            'email_from': self.env.user.company_id.email or 'noreply@company.com',
            'attachment_ids': [(6, 0, [attachment.id])],
            'auto_delete': False,
        }
        
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()
        
        _logger.info(f'Monthly report sent successfully to {hr_email}')
    
    def _get_monthly_report_email_body(self, messages, report_month):
        """Generate HTML email body for monthly report"""
        status_counts = {}
        category_counts = {}
        
        for msg in messages:
            status_counts[msg.state] = status_counts.get(msg.state, 0) + 1
            category_counts[msg.category] = category_counts.get(msg.category, 0) + 1
        
        state_dict = dict(messages._fields['state'].selection)
        category_dict = dict(messages._fields['category'].selection)
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #667eea; text-align: center;">📊 Monthly Anonymous Messages Report</h2>
                <h3 style="text-align: center; color: #666;">{report_month.strftime('%B %Y')}</h3>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">Summary</h3>
                    <p><strong>Total Messages:</strong> {len(messages)}</p>
                    
                    <h4>By Status:</h4>
                    <ul>
                        {''.join([f"<li>{state_dict.get(state, state)}: {count}</li>" for state, count in status_counts.items()])}
                    </ul>
                    
                    <h4>By Category:</h4>
                    <ul>
                        {''.join([f"<li>{category_dict.get(cat, cat)}: {count}</li>" for cat, count in category_counts.items()])}
                    </ul>
                </div>
                
                <div style="background-color: #e8f4fd; padding: 15px; border-radius: 6px; border-left: 4px solid #0d6efd;">
                    <p style="margin: 0;"><strong>📎 Attachment:</strong> Detailed Excel report with all message information is attached.</p>
                </div>
                
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #888; font-size: 12px;">
                    <p>This is an automated report from the Odoo Anonymous HR Messaging System.</p>
                    <p>Sender identities are NOT included to maintain anonymity.</p>
                </div>
            </div>
        </body>
        </html>
        """