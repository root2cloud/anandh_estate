from odoo import models, fields


class PropertyCategory(models.Model):
    _name = 'property.category'
    _description = 'Property Category'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # ⭐ ADD THIS LINE

    name = fields.Char('Category Name*', required=True)
    description = fields.Text('Description')
    parent_left = fields.Integer('Left Parent', index=True)
    parent_right = fields.Integer('Right Parent', index=True)
    image = fields.Binary('Image')
    seo_title = fields.Char('SEO Title*',required=True)
    seo_description = fields.Text('SEO Description')
    color = fields.Integer(string='Color', default=0)

    property_ids = fields.One2many('property.property', 'category_id', string='Properties')
