# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_real_estate_customer = fields.Boolean(
        string='Real Estate Customer', default=False, copy=False,
        help="Set automatically when a customer registration submitted through "
             "the website is approved by the admin."
    )
    customer_since = fields.Date(string='Customer Since', copy=False)
    registration_ids = fields.One2many(
        'customer.registration', 'partner_id', string='Registration Requests'
    )
