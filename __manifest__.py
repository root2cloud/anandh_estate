{
    'name': 'Real Estate Management',
    'version': '1.2',
    'license': 'LGPL-3',
    'category': 'Website',
    'summary': 'Advanced real estate management platform: properties, agents, customers and a branded website',
    'description': '''
Real Estate Management
=======================
A complete real estate management platform with:
  * Property listings with an interactive map, categories and rich detail pages.
  * Customer registration workflow with admin approval and automatic portal access.
  * Agent registration workflow with admin approval, portal access and agent dashboards.
  * Dedicated backend app with Properties, Property Categories, Customer Registrations,
    Agent Registrations, Customers and Agents menus.
  * A professional branded website header (logo + name + navigation) used across the site.
''',
    'author': 'Real Estate Management',
    'depends': ['base', 'base_geolocalize', 'web', 'website_sale', 'mail', 'base_setup'],
    'data': [
        # Security
        'security/ir.model.access.csv',
        'security/property_security.xml',

        # data
        'data/mail_property_rejection.xml',
        'data/sequences.xml',
        'data/agent_registration_demo.xml',
        'data/mail_activity.xml',
        'data/ai_content_cron.xml',
        # 'data/dashboard_data.xml',

        # Backend Views / Menus
        'views/property_views.xml',
        'views/property_category_views.xml',
        'views/dashboard_menu.xml',
        'views/menu.xml',
        'views/website_menu.xml',
        'views/property_registration_views.xml',
        'views/customer_registration_views.xml',
        'views/customer_views.xml',
        'views/agent_views.xml',
        'views/agent_registration_views.xml',
        # 'views/portal_agent_views.xml',

        # Qweb Templates - Website
        'views/qweb_templates/site_header.xml',
        'views/qweb_templates/property_map_template.xml',
        'views/qweb_templates/property_detail_page.xml',
        'views/qweb_templates/properties_menu_page.xml',
        'views/qweb_templates/website_registration_template.xml',
        # 'views/qweb_templates/agent_directory_template.xml',
        # 'views/qweb_templates/agent_detail_template.xml',
        'views/qweb_templates/customer_registration_form_template.xml',
        'views/qweb_templates/agent_registration_form_template.xml',
        'views/qweb_templates/agent_no_access.xml',
        'views/qweb_templates/customer_no_access.xml',
        'views/qweb_templates/agent_portal_dashboard.xml',
        'views/qweb_templates/customer_dashboard.xml',
        'views/qweb_templates/agent_portal_profile.xml',
        'views/qweb_templates/agent_portal_property_form.xml',
        'views/qweb_templates/agent_portal_my_properties.xml',
        'views/qweb_templates/agent_portal_property_detail.xml',

        # wizards
        'wizard/agent_registration_reject_wizard_views.xml',
        'wizard/customer_registration_reject_wizard_views.xml',

    ],
    'assets': {
        'web.assets_frontend': [
            'real_estate_management/static/src/js/property_map.js',
            # 'real_estate_management/static/src/css/property_map.css',
            # 'real_estate_management/static/src/css/agent_registration.css',
            # 'real_estate_management/static/src/css/dashboard.css',
            # 'real_estate_management/static/src/js/dashboard.js',
        ],
        'web.assets_backend': [
            'real_estate_management/static/src/css/dashboard.css',
            'real_estate_management/static/src/xml/dashboard.xml',
            'real_estate_management/static/src/js/dashboard.js',
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
        ],
    },
    'installable': True,
    'application': True,
}