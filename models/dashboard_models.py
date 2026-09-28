# -*- coding: utf-8 -*-
from odoo import models, api
import json


class PropertyDashboard(models.Model):
    _name = 'property.dashboard'
    _description = 'Real Estate Dashboard'

    @api.model
    def get_dashboard_data(self):
        """Get comprehensive dashboard statistics"""
        Property = self.env['property.property']
        Agent = self.env['real.estate.agent']
        Registration = self.env['property.registration']

        # Property Statistics
        total_properties = Property.search_count([])
        available_properties = Property.search_count([('status', '=', 'available')])
        sold_properties = Property.search_count([('status', '=', 'sold')])
        rented_properties = Property.search_count([('status', '=', 'rented')])
        featured_properties = Property.search_count([('is_featured', '=', True)])
        published_properties = Property.search_count([('is_published', '=', True)])

        # Financial Statistics
        all_properties = Property.search([])
        total_value = sum(all_properties.mapped('price'))
        available_value = sum(Property.search([('status', '=', 'available')]).mapped('price'))
        sold_value = sum(Property.search([('status', '=', 'sold')]).mapped('price'))
        avg_price = total_value / total_properties if total_properties else 0

        # Registration Statistics
        pending_registrations = Registration.search_count([('status', 'in', ['draft', 'submitted'])])
        approved_registrations = Registration.search_count([('status', '=', 'approved')])
        rejected_registrations = Registration.search_count([('status', '=', 'rejected')])

        # Agent Statistics
        total_agents = Agent.search_count([('is_active', '=', True)])
        top_agents = Agent.search([], order='total_deals desc', limit=5)

        # Category-wise Distribution
        categories = self.env['property.category'].search([])
        category_data = []
        for cat in categories:
            count = Property.search_count([('category_id', '=', cat.id)])
            if count > 0:
                category_data.append({'name': cat.name, 'count': count})

        # City-wise Distribution
        city_query = """
            SELECT city, COUNT(*) as count, SUM(price) as total_value
            FROM property_property
            WHERE city IS NOT NULL
            GROUP BY city
            ORDER BY count DESC
            LIMIT 10
        """
        self.env.cr.execute(city_query)
        city_data = self.env.cr.dictfetchall()

        # Monthly Property Additions (Last 6 months)
        monthly_query = """
            SELECT 
                TO_CHAR(create_date, 'Mon YYYY') as month,
                COUNT(*) as count
            FROM property_property
            WHERE create_date >= NOW() - INTERVAL '6 months'
            GROUP BY TO_CHAR(create_date, 'Mon YYYY'), DATE_TRUNC('month', create_date)
            ORDER BY DATE_TRUNC('month', create_date)
        """
        self.env.cr.execute(monthly_query)
        monthly_data = self.env.cr.dictfetchall()

        # Price Range Distribution
        price_ranges = [
            {'label': 'Below 50L', 'min': 0, 'max': 5000000},
            {'label': '50L - 1Cr', 'min': 5000000, 'max': 10000000},
            {'label': '1Cr - 2Cr', 'min': 10000000, 'max': 20000000},
            {'label': '2Cr - 5Cr', 'min': 20000000, 'max': 50000000},
            {'label': 'Above 5Cr', 'min': 50000000, 'max': 999999999999},
        ]

        price_distribution = []
        for range_item in price_ranges:
            count = Property.search_count([
                ('price', '>=', range_item['min']),
                ('price', '<', range_item['max'])
            ])
            price_distribution.append({
                'label': range_item['label'],
                'count': count
            })

        # Recent Properties
        recent_properties = Property.search([], order='create_date desc', limit=5)
        recent_props_data = [{
            'id': prop.id,
            'name': prop.name,
            'city': prop.city,
            'price': prop.price,
            'status': prop.status,
            'category': prop.category_id.name if prop.category_id else 'N/A',
        } for prop in recent_properties]

        return {
            'stats': {
                'total_properties': total_properties,
                'available': available_properties,
                'sold': sold_properties,
                'rented': rented_properties,
                'featured': featured_properties,
                'published': published_properties,
                'total_value': total_value,
                'available_value': available_value,
                'sold_value': sold_value,
                'avg_price': avg_price,
                'total_agents': total_agents,
                'pending_registrations': pending_registrations,
                'approved_registrations': approved_registrations,
                'rejected_registrations': rejected_registrations,
            },
            'charts': {
                'category_data': category_data,
                'city_data': city_data,
                'monthly_data': monthly_data,
                'price_distribution': price_distribution,
            },
            'top_agents': [{
                'id': agent.id,
                'name': agent.name,
                'deals': agent.total_deals,
                'sales_volume': agent.total_sales_volume,
                'active_properties': agent.active_property_count,
            } for agent in top_agents],
            'recent_properties': recent_props_data,
            'currency_symbol': self.env.company.currency_id.symbol,
        }
