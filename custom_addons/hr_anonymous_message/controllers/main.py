# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json


class AnonymousMessageController(http.Controller):

    @http.route('/api/anonymous/message', type='jsonrpc', auth='user', methods=['POST'], csrf=False)
    def send_anonymous_message(self, **kw):
        """API endpoint to send anonymous message"""
        try:
            data = request.jsonrequest
            
            # Create the message
            message = request.env['hr.anonymous.message'].create({
                'name': data.get('subject'),
                'description': data.get('message'),
                'category': data.get('category', 'general'),
            })
            
            # Send to HR
            message.send_to_hr()
            
            return {
                'success': True,
                'message': 'Your anonymous message has been sent to HR management successfully',
                'message_id': message.id
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/api/anonymous/categories', type='jsonrpc', auth='user', methods=['GET'], csrf=False)
    def get_message_categories(self):
        """Get available categories for anonymous messages"""
        categories = request.env['hr.anonymous.message']._fields['category'].selection
        
        return {
            'categories': [
                {'value': cat[0], 'label': cat[1]} 
                for cat in categories
            ]
        }

    @http.route('/api/anonymous/status', type='jsonrpc', auth='user', methods=['GET'], csrf=False)
    def get_anonymous_system_status(self):
        """Check if anonymous messaging system is available"""
        hr_email = request.env['ir.config_parameter'].sudo().get_param(
            'hr_anonymous_message.hr_email',
            default='hr@company.com'
        )
        
        return {
            'available': True,
            'hr_email_configured': hr_email != 'hr@company.com',
            'message': 'Anonymous messaging system is operational'
        }