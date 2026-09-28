# -*- coding: utf-8 -*-
from odoo import models, fields


class PropertyGalleryImage(models.Model):
    _name = 'property.gallery.image'
    _description = 'Property Gallery Images'

    name = fields.Char(string='Image Name')
    property_id = fields.Many2one('property.property', string='Property',
                                  required=True, ondelete='cascade')
    image = fields.Binary(string='Image', required=True, attachment=True)
