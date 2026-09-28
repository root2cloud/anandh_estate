# -*- coding: utf-8 -*-
import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import secrets
import string

_logger = logging.getLogger(__name__)


class CustomerRegistration(models.Model):
    _name = 'customer.registration'
    _description = 'Customer Registration Requests'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Registration ID', readonly=True, default='New', copy=False)
    customer_name = fields.Char(string='Customer Name', required=True, tracking=True)
    email = fields.Char(string='Email', required=True, tracking=True)
    phone = fields.Char(string='Phone Number', required=True, tracking=True)
    address = fields.Char(string='Address')
    city = fields.Char(string='City', tracking=True)
    state_id = fields.Many2one('res.country.state', string='State')
    zip_code = fields.Char(string='ZIP Code')
    country_id = fields.Many2one(
        'res.country', string='Country',
        default=lambda self: self.env.ref('base.in', raise_if_not_found=False)
    )
    interested_in = fields.Selection([
        ('buy', 'Buying a Property'),
        ('rent', 'Renting a Property'),
        ('sell', 'Selling a Property'),
        ('invest', 'Investment'),
    ], string='Interested In', default='buy')
    notes = fields.Text(string='Additional Notes')

    status = fields.Selection([
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='submitted', required=True, tracking=True)

    rejection_reason = fields.Text(string='Rejection Reason', tracking=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    review_date = fields.Datetime(string='Review Date', readonly=True)
    submission_date = fields.Datetime(string='Submission Date', default=fields.Datetime.now, readonly=True)

    partner_id = fields.Many2one('res.partner', string='Linked Customer Profile', readonly=True, copy=False)

    # ─────────────────────────────────────────────────────────────
    # ⭐ NEW: PENDING "SELL" PROPERTY DETAILS
    # Captured at signup time from the "Property Details (For Sale)"
    # section of the public form, but deliberately NOT turned into a
    # property.registration record yet - that only happens once THIS
    # customer registration is approved (see action_approve /
    # _create_property_submission below). This is what keeps an
    # unapproved customer's property out of "Property Submissions".
    # ─────────────────────────────────────────────────────────────
    pending_property_name = fields.Char(string='Pending Property Name')
    pending_property_category = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('agricultural', 'Agricultural'),
    ], string='Pending Property Category')
    pending_property_price = fields.Float(string='Pending Property Price')
    pending_property_area = fields.Float(string='Pending Property Area (Sq Yards)')
    pending_property_description = fields.Text(string='Pending Property Description')
    pending_property_address = fields.Char(string='Pending Property Location')
    pending_property_city = fields.Char(string='Pending Property City')
    pending_property_state = fields.Char(string='Pending Property State')
    pending_property_image = fields.Binary(string='Pending Property Main Image')

    property_registration_id = fields.Many2one(
        'property.registration', string='Property Submission', readonly=True, copy=False,
        help="Set automatically once this customer registration is approved and its "
             "pending property details (if any) are turned into a real Property Submission. "
             "Empty until then - and stays empty forever if interested_in isn't 'sell'."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('customer.registration') or 'New'
        records = super(CustomerRegistration, self).create(vals_list)
        for record in records:
            record._send_admin_notification()
        return records

    # ─────────────────────────────────────────────────────────────
    # APPROVE
    # ─────────────────────────────────────────────────────────────
    def action_approve(self):
        """Approve and create the customer profile (res.partner) + portal login."""
        self.ensure_one()
        if self.status == 'approved':
            raise ValidationError(_("This registration is already approved!"))

        try:
            partner = self.partner_id
            if not partner:
                partner_model = self.env['res.partner'].sudo().with_context(
                    tracking_disable=True,
                    mail_create_nosubscribe=True,
                    mail_auto_subscribe=False,
                    mail_create_nolog=True,
                )
                partner = partner_model.create({
                    'name': self.customer_name,
                    'email': self.email,
                    'phone': self.phone,
                    'street': self.address,
                    'city': self.city,
                    'state_id': self.state_id.id if self.state_id else False,
                    'zip': self.zip_code,
                    'country_id': self.country_id.id if self.country_id else False,
                    'is_company': False,
                    'is_real_estate_customer': True,
                    'customer_since': fields.Date.today(),
                })
            else:
                partner.sudo().write({'is_real_estate_customer': True})

            portal_user, temp_password = self._create_portal_user_for_customer(partner)
            if portal_user:
                partner.sudo().write({'user_id': portal_user.id})

            self.write({
                'status': 'approved',
                'partner_id': partner.id,
                'reviewed_by': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })

            if temp_password:
                self.message_post(
                    body=f"✅ Approved by {self.env.user.name}. Customer profile created.<br/>"
                         f"Login: {self.email}<br/>Temporary Password: {temp_password}",
                    message_type='notification',
                )
            else:
                self.message_post(
                    body=f"✅ Approved by {self.env.user.name}. Customer profile created/linked. "
                         f"Login: {self.email}",
                    message_type='notification',
                )

            # ⭐ NEW: the customer never actually heard back before - only
            # an internal chatter note was posted (visible to admins only).
            # Send them a real congratulations email now that they're approved.
            self._send_approval_email(partner, temp_password)

            # ⭐ NEW: only now - once the CUSTOMER is approved - do we turn
            # their pending "sell" details into a real Property Submission.
            # Before this point they only sat on this record's pending_*
            # fields and never appeared in "Property Submissions" at all.
            if self.interested_in == 'sell' and not self.property_registration_id:
                self._create_property_submission()

            notif_message = (
                f'Customer {partner.name} created. Login: {self.email}   '
                f'Temporary Password: {temp_password}'
            ) if temp_password else (
                f'Customer {partner.name} created. Login: {self.email}'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success!',
                    'message': notif_message,
                    'type': 'success',
                    'sticky': True,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        except Exception as e:
            _logger.error("Error approving customer registration: %s", str(e))
            raise ValidationError(_("Error: %s") % str(e))

    def _create_portal_user_for_customer(self, partner):
        """Create (or reuse) a portal login for the approved customer.
        Returns (user, temp_password). temp_password is None when an
        existing login was reused."""
        existing_user = self.env['res.users'].sudo().search([('login', '=', self.email)], limit=1)
        if existing_user:
            _logger.info("Portal user already exists for %s", self.email)
            return existing_user, None

        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        if not portal_group:
            return False, None

        user_model = self.env['res.users'].sudo().with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
            mail_auto_subscribe=False,
            mail_create_nolog=True,
            no_reset_password=True,
        )
        user = user_model.create({
            'name': self.customer_name,
            'login': self.email,
            'email': self.email,
            'partner_id': partner.id,
            'groups_id': [(6, 0, [portal_group.id])],
            'active': True,
        })

        # ⭐ Set a working password directly instead of relying only on a
        # password-reset EMAIL (which never arrives on a dev/localhost
        # instance with no outgoing mail server configured). This is what
        # actually lets the customer log in right away.
        temp_password = self._generate_temp_password()
        user.sudo().write({'password': temp_password})

        # Also try the email flow as a courtesy, in case mail IS configured
        # on this instance — but login no longer depends on it.
        try:
            user.sudo().with_context(
                mail_notify_force_send=False,
                mail_create_nolog=True,
            ).action_reset_password()
        except Exception as e:
            _logger.warning(f"Password reset email could not be sent: {e}")

        _logger.info("✅ Portal user created for customer: %s (%s)", self.customer_name, self.email)
        return user, temp_password

    def _generate_temp_password(self, length=10):
        """Generate a readable random password (letters + digits, at least
        one of each) for a freshly-created portal login."""
        alphabet = string.ascii_letters + string.digits
        while True:
            pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
            if any(c.isdigit() for c in pwd) and any(c.isalpha() for c in pwd):
                return pwd

    # ─────────────────────────────────────────────────────────────
    # ⭐ NEW: CONGRATULATIONS EMAIL ON APPROVAL
    # ─────────────────────────────────────────────────────────────
    def _send_approval_email(self, partner, temp_password=None):
        """Email the customer directly to let them know their registration
        was approved. Separate from the admin-only chatter note above,
        which the customer never sees. Login credentials are only ever
        embedded here (never stored as a field) since temp_password is
        generated fresh and only exists in memory during this request."""
        self.ensure_one()
        if not self.email:
            return

        if temp_password:
            credentials_html = f"""
                <p>Your customer portal login is ready:</p>
                <ul>
                    <li><b>Login:</b> {self.email}</li>
                    <li><b>Temporary Password:</b> {temp_password}</li>
                </ul>
                <p>Please log in and change your password after your first sign-in.</p>
            """
        else:
            credentials_html = f"""
                <p>You can log in to your customer portal with your existing account
                (<b>{self.email}</b>).</p>
            """

        body_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
                <h2 style="color: #c7a24a; margin-bottom: 4px;">🎉 Congratulations, {self.customer_name}!</h2>
                <p>Your customer registration with <b>Real Estate Management</b> has been approved.</p>
                <p>You are now officially a registered customer and can start browsing, saving,
                   and enquiring about properties right away.</p>
                {credentials_html}
                <p style="margin-top: 20px;">Thank you for choosing us!<br/>Real Estate Team</p>
            </div>
        """

        try:
            self.env['mail.mail'].sudo().create({
                'subject': 'Congratulations! Your Customer Registration is Approved 🎉',
                'email_from': self.env.user.email_formatted or 'noreply@example.com',
                'email_to': self.email,
                'body_html': body_html,
            }).send()
        except Exception as e:
            # Never let a mail-server hiccup (e.g. no SMTP configured on a
            # dev/localhost instance) block the actual approval itself.
            _logger.warning("Could not send approval congratulations email to %s: %s", self.email, e)

    # ─────────────────────────────────────────────────────────────
    # ⭐ NEW: TURN PENDING "SELL" DETAILS INTO A REAL PROPERTY SUBMISSION
    # Only ever called from action_approve, above - never at signup time.
    # ─────────────────────────────────────────────────────────────
    def _create_property_submission(self):
        """Create the property.registration record (which is what makes
        it show up in 'Property Submissions') from this customer's
        pending_* fields, now that the customer itself has been approved.
        Also moves over any extra images that were attached to this
        record at signup time."""
        self.ensure_one()

        property_vals = {
            'customer_name': self.customer_name,
            'property_name': self.pending_property_name or 'Property for Sale',
            'phone_number': self.phone,
            'email': self.email,
            # ⭐ NOTE: the sell form doesn't collect a separate
            # "locality/area" field, only City + Exact Address, so City
            # is reused for the required "Place" field - display only,
            # doesn't affect the live property (built from location/city).
            'place': self.pending_property_city or 'Unknown',
            'category': self.pending_property_category or 'residential',
            'sq_yards': self.pending_property_area or 0.0,
            'price': self.pending_property_price or 0.0,
            'location': self.pending_property_address or 'N/A',
            'city': self.pending_property_city or 'Unknown',
            'state': self.pending_property_state or 'Unknown',
            'description': self.pending_property_description,
            'image': self.pending_property_image,
            'source': 'customer',
            'customer_registration_id': self.id,
            'status': 'submitted',
        }

        property_rec = self.env['property.registration'].sudo().create(property_vals)
        self.property_registration_id = property_rec.id
        property_rec._send_admin_notification()

        # Move any EXTRA images (beyond the main one) that were attached
        # to this customer registration at signup time over to the new
        # Property Submission, so they aren't left behind/orphaned.
        extra_attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'customer.registration'),
            ('res_id', '=', self.id),
        ])
        if extra_attachments:
            extra_attachments.write({
                'res_model': 'property.registration',
                'res_id': property_rec.id,
            })

    # ─────────────────────────────────────────────────────────────
    # REJECT
    # ─────────────────────────────────────────────────────────────
    def action_reject(self):
        self.ensure_one()
        if self.status == 'rejected':
            raise ValidationError(_("Already rejected!"))
        return {
            'name': 'Reject Registration',
            'type': 'ir.actions.act_window',
            'res_model': 'customer.registration.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_registration_id': self.id}
        }

    def action_view_customer_profile(self):
        self.ensure_one()
        if not self.partner_id:
            raise ValidationError(_("No customer profile created yet!"))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Customer Profile',
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
        }

    def _send_admin_notification(self):
        """Bell notification + activity for the admin when a new registration arrives."""
        self.ensure_one()
        admin_user = self.env.ref('base.user_admin', raise_if_not_found=False)
        if not admin_user:
            return
        admin_partner = admin_user.partner_id

        activity_type = self.env.ref(
            'real_estate_management.activity_customer_registration_review', raise_if_not_found=False
        )
        if activity_type:
            self.env['mail.activity'].sudo().create({
                'activity_type_id': activity_type.id,
                'summary': 'Approve Customer Registration',
                'note': f'New customer registration submitted by {self.customer_name}',
                'res_model_id': self.env['ir.model']._get(self._name).id,
                'res_id': self.id,
                'user_id': admin_user.id,
                'date_deadline': fields.Date.today(),
            })

        self.message_post(
            body=Markup(f"""
                🔔 <b>New Customer Registration Submitted</b><br/>
                <ul>
                    <li><b>Name:</b> {self.customer_name}</li>
                    <li><b>Email:</b> {self.email}</li>
                    <li><b>City:</b> {self.city or '-'}</li>
                </ul>
            """),
            message_type='notification',
            partner_ids=[admin_partner.id],
            subtype_xmlid='mail.mt_comment',
        )