# -*- coding: utf-8 -*-
{
    'name': 'HR Anonymous Messaging System',
    'version': '2.0.0',
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
        * Monthly Excel reports
        * Complete anonymity guaranteed
    """,
    'author': 'Promethean Consulting Limited',
    'website': 'https://prometheanconsult.com/',
    'depends': ['base', 'hr', 'mail'],
    'data': [
        # 'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'data/ir_cron.xml',
        'views/hr_anonymous_message_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}