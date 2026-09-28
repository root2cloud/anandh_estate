# -*- coding: utf-8 -*-
from odoo import models, fields, _


class AgentRegistrationRejectWizard(models.TransientModel):
    _name = 'agent.registration.reject.wizard'
    _description = 'Reject Agent Registration'

    registration_id = fields.Many2one('agent.registration', required=True)
    rejection_reason = fields.Text(string='Rejection Reason', required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        self.registration_id.write({
            'status': 'rejected',
            'rejection_reason': self.rejection_reason,
            'reviewed_by': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })
        self.registration_id.message_post(
            body=f"❌ Rejected by {self.env.user.name}: {self.rejection_reason}",
            message_type='notification'
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Rejected',
                'message': 'Registration rejected.',
                'type': 'warning',
            }
        }
