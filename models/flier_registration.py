# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FlierRegistration(models.Model):
    """Registrations submitted from a property flier / flier QR page."""
    _name = 'flier.registration'
    _description = 'Flyer Property Registration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'submission_date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, default='New', copy=False)
    property_id = fields.Many2one('property.property', string='Property', required=True,
                                  ondelete='restrict', index=True, tracking=True)
    currency_id = fields.Many2one(related='property_id.currency_id', string='Currency', readonly=True)
    property_price = fields.Monetary(related='property_id.price', currency_field='currency_id',
                                     string='Property Price', readonly=True)
    bid_amount = fields.Monetary(string='Bid Amount', currency_field='currency_id', tracking=True,
                                 help='Amount offered by the customer for this property.')
    customer_name = fields.Char(string='Full Name', required=True, tracking=True)
    phone = fields.Char(string='Phone Number', required=True, tracking=True)
    email = fields.Char(string='Email', required=True)
    address = fields.Char(string='Address')
    state_id = fields.Many2one('res.country.state', string='State')
    city = fields.Char(string='City')
    zip_code = fields.Char(string='Pincode')
    source = fields.Selection([
        ('flier', 'Flyer'),
        ('qr', 'Flyer QR Page'),
    ], string='Registered From', default='flier', readonly=True)
    submission_date = fields.Datetime(string='Submitted On', default=fields.Datetime.now, readonly=True)
    status = fields.Selection([
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('closed', 'Closed'),
    ], string='Status', default='new', tracking=True, required=True)
    note = fields.Text(string='Internal Notes')
    customer_registration_id = fields.Many2one(
        'customer.registration', string='Customer Registration', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('flier.registration') or 'New'
        return super().create(vals_list)

    def action_mark_contacted(self):
        self.write({'status': 'contacted'})

    def action_mark_closed(self):
        self.write({'status': 'closed'})

    def action_reset_new(self):
        self.write({'status': 'new'})

    def action_open_property(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'property.property',
            'res_id': self.property_id.id,
            'view_mode': 'form',
            'target': 'current',
        }