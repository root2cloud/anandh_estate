# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from markupsafe import Markup
import json
import logging

_logger = logging.getLogger(__name__)


class CustomerPortalDashboard(http.Controller):

    @http.route(['/my/account-redirect'], type='http', auth='user', website=True)
    def account_redirect(self, **kw):
        """Smart post-login router. Sends the logged-in user straight to
        their own dashboard: agents go to the Agent Dashboard, customers
        go to the Customer Dashboard, anyone else falls back to the
        standard Odoo portal home."""
        user = request.env.user

        agent = request.env['real.estate.agent'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if agent:
            return request.redirect('/my/agent/dashboard')

        if user.partner_id.sudo().is_real_estate_customer:
            return request.redirect('/my/customer/dashboard')

        # Not linked to an approved agent or customer profile yet
        # (e.g. internal staff, or a registration still pending approval).
        return request.redirect('/my')

    @http.route(['/my/customer/dashboard'], type='http', auth='public', website=True)
    def customer_dashboard(self, **kw):
        """ Render the Premium Customer Dashboard """

        user = request.env.user

        # 1. SECURITY: block genuinely logged-out / public visitors.
        if not user or user._is_public():
            return request.render('real_estate_management.customer_no_access', {})

        # 2. ⭐ FIX: an Agent should not be able to open the Customer
        #    Dashboard. Agents have their own dedicated dashboard at
        #    /my/agent/dashboard - the Customer Dashboard is reserved for
        #    customer accounts only, so we detect an active agent link
        #    and redirect them there with an explanatory message instead.
        agent = request.env['real.estate.agent'].sudo().search(
            [('user_id', '=', user.id), ('is_active', '=', True)], limit=1
        )
        if agent:
            return request.render('real_estate_management.customer_no_access', {
                'message': 'The Customer Dashboard is reserved for customer accounts. '
                            'You are logged in as an Agent - please use the Agent Dashboard instead.',
                'agent_redirect': True,
            })

        Property = request.env['property.property'].sudo()

        # 2. Fetch properties linked to the logged-in customer.
        #    Properties are created by the ADMIN when they approve a
        #    property.registration (or by an agent), so create_uid never
        #    equals the customer's user id. The reliable link is the
        #    contact_email stored on the property, which is set to the
        #    customer's email at approval time.
        customer_email = (user.partner_id.email or user.login or '').strip()
        domain = [('contact_email', '=ilike', customer_email)] if customer_email else [('id', '=', False)]
        properties = Property.search(domain, order="create_date desc")

        # 3. Calculate Statistics safely
        stats = {
            'total': len(properties),
            'available': len(properties.filtered(lambda p: p.status == 'available')),
            'sold': len(properties.filtered(lambda p: p.status == 'sold')),
            'rented': len(properties.filtered(lambda p: p.status == 'rented')),
        }

        # 4. Prepare Chart Data safely
        category_counts = {}
        city_counts = {}
        for prop in properties:
            cat = prop.category_id.name if prop.category_id else 'Other'
            category_counts[cat] = category_counts.get(cat, 0) + 1

            city = prop.city or 'Unknown'
            city_counts[city] = city_counts.get(city, 0) + 1

        chart_data = {
            'categories': {
                'labels': list(category_counts.keys()),
                'data': list(category_counts.values())
            },
            'cities': {
                'labels': list(city_counts.keys()),
                'data': list(city_counts.values())
            }
        }

        values = {
            'page_name': 'customer_dashboard',
            'user': user,
            'properties': properties,
            'recent_properties': properties[:5],
            'stats': stats,
            # Markup ensures the JSON is not escaped by QWeb, preventing JS Syntax Errors
            'chart_data_json': Markup(json.dumps(chart_data)),
        }

        return request.render('real_estate_management.customer_dashboard_template', values)