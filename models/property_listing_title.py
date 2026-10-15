# -*- coding: utf-8 -*-
from odoo import _, fields, models


class PropertyProperty(models.Model):
    """Extra fields / actions for properties added with the website
    "Add a Property" button:
      * listing_title   - headline shown on the home page card
      * approval_state  - such a property lands in Properties as
                          "Pending Approval"; clicking Approve publishes it
                          and starts the AI content generation.
    Every existing property keeps approval_state = 'approved'."""
    _inherit = 'property.property'

    listing_title = fields.Char(string='Listing Title')
    approval_state = fields.Selection([
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval', default='approved', copy=False, index=True)

    # No AI content (and no Gemini calls) until the property is approved.
    def _schedule_ai_content_generation(self):
        approved = self.filtered(lambda r: r.approval_state != 'pending')
        if not approved:
            return
        return super(PropertyProperty, approved)._schedule_ai_content_generation()

    def _mark_listing_approved(self):
        """Pending -> Approved + published. Publishing also schedules the
        AI content generation (see write() in property.py)."""
        pending = self.filtered(lambda r: r.approval_state == 'pending')
        if pending:
            pending.write({'approval_state': 'approved', 'is_published': True})
        return pending

    def action_approve_listing(self):
        """Approve button on the Properties form."""
        Registration = self.env['property.registration']
        for rec in self.filtered(lambda r: r.approval_state == 'pending'):
            regs = Registration.search([
                ('property_id', '=', rec.id), ('status', '!=', 'approved')])
            if regs:
                regs.action_approve()      # also marks this property approved
            rec._mark_listing_approved()   # no-op when already done above
        self._schedule_ai_content_generation()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Property approved'),
                'message': _('The property is published and its AI content is being generated.'),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }