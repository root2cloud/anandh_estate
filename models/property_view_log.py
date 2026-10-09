# -*- coding: utf-8 -*-
from odoo import fields, models


class PropertyViewLog(models.Model):
    """One row per (property, visitor IP address): used to count unique views."""
    _name = 'property.view.log'
    _description = 'Property View (unique per IP address)'
    _order = 'last_view desc, id desc'

    property_id = fields.Many2one('property.property', string='Property', required=True,
                                  ondelete='cascade', index=True)
    ip_address = fields.Char(string='IP Address', required=True, index=True)
    view_count = fields.Integer(string='Visits', default=1)
    first_view = fields.Datetime(string='First Visit', default=fields.Datetime.now, readonly=True)
    last_view = fields.Datetime(string='Last Visit', default=fields.Datetime.now)

    _sql_constraints = [
        ('property_ip_unique', 'unique(property_id, ip_address)',
         'This IP address is already counted for this property.'),
    ]