# -*- coding: utf-8 -*-
{
    'name': 'HR Anonymous Messaging',
    'version': '1.0.0',
    'category': 'Human Resources',
    'summary': 'Allow employees to send anonymous messages to HR',
    'description': """
        HR Anonymous Messaging System
        ==============================
        
        Features:
        ---------
        * Employees can send anonymous messages to HR
        * Messages are categorized (complaints, suggestions, harassment, etc.)
        * Sender identity is logged for audit but not visible to HR
        * Automatic email notifications to HR
        * Configurable HR email address
        * Audit trail for compliance
    """,
    'author': 'Promethean Consulting Limited',
    'website': 'https://prometheanconsult.com/',
    'depends': ['base', 'hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'views/hr_anonymous_message_views.xml',
        'views/res_config_settings_views.xml',
        #'views/templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}