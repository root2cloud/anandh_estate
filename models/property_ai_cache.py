# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PropertyAICache(models.Model):
    _name = 'property.ai.cache'
    _description = 'Property AI Content Cache'
    _rec_name = 'city'

    city = fields.Char(string='City', required=True, index=True)
    cache_type = fields.Selection([
        ('daily_news', 'Daily News Ticker'),
        ('investment_info', 'Investment Information'),
    ], string='Cache Type', required=True, index=True)
    content = fields.Text(string='Cached Content', required=True)
    create_date = fields.Datetime(string='Cache Date', default=fields.Datetime.now)

    _sql_constraints = [
        ('unique_city_type', 'unique(city, cache_type)',
         'Cache entry already exists for this city and type!')
    ]
