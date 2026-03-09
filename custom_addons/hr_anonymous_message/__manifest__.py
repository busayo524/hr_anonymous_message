# -*- coding: utf-8 -*-
{
    'name': 'HR Anonymous Messaging System',
    'version': '2.1.1',
    'category': 'Human Resources',
    'summary': 'Fully anonymous messaging system with encrypted audit trail',
    'description': """
        HR Anonymous Messaging System
        ==============================
        
        Features:
        ---------
        * 100% Anonymous - NO ONE can see sender identity
        * Encrypted audit trail for legal compliance
        * Real-time notifications
        * Status workflow management
        * Sidebar search panel with live message counts
        * Monthly Excel reports
        * Complete anonymity guaranteed
    """,
    'author': 'Promethean Consulting Limited',
    'website': 'https://prometheanconsult.com/',
    'depends': ['base', 'hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/category_data.xml',
        'data/mail_template.xml',
        'data/ir_cron.xml',
        'views/hr_anonymous_message_category_views.xml',
        'views/hr_anonymous_message_views_employee.xml',
        'views/hr_anonymous_message_views_hr.xml',
        'views/hr_anonymous_message_views_admin.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}