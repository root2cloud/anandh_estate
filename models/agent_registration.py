# -*- coding: utf-8 -*-
import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import secrets
import string

_logger = logging.getLogger(__name__)


class AgentRegistration(models.Model):
    _name = 'agent.registration'
    _description = 'Agent Registration Requests'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Registration ID', readonly=True, default='New', copy=False)
    agent_name = fields.Char(string='Full Name', required=True, tracking=True)
    email = fields.Char(string='Email', required=True, tracking=True)
    phone = fields.Char(string='Phone Number', required=True, tracking=True)
    whatsapp = fields.Char(string='WhatsApp Number')

    designation = fields.Selection([
        ('agent', 'Agent'),
        ('senior_agent', 'Senior Agent'),
        ('principal_agent', 'Principal Agent'),
        ('broker', 'Broker'),
    ], string='Desired Designation', required=True, default='agent')

    expertise_level = fields.Selection([
        ('standard', 'Standard Agent'),
        ('luxury', 'Luxury Expert'),
    ], string='Expertise Level', required=True, default='standard')

    license_number = fields.Char(string='License Number')
    experience_years = fields.Integer(string='Years of Experience', default=0)

    city = fields.Char(string='City', required=True)
    state_id = fields.Many2one('res.country.state', string='State', required=True)
    zip_code = fields.Char(string='ZIP Code')
    country_id = fields.Many2one('res.country', string='Country')

    short_bio = fields.Text(string='Short Bio')
    detailed_bio = fields.Html(string='Detailed Biography')
    qualifications = fields.Text(string='Qualifications')
    languages_spoken = fields.Char(string='Languages Spoken', default='English, Hindi')

    specialization_ids = fields.Many2many(
        'property.category',
        'agent_registration_category_rel',
        'registration_id',
        'category_id',
        string='Property Specializations'
    )

    profile_image = fields.Image(string='Profile Photo', max_width=400, max_height=400)
    license_document = fields.Binary(string='License Document', attachment=True)
    license_filename = fields.Char()
    id_proof = fields.Binary(string='ID Proof', attachment=True)
    id_proof_filename = fields.Char()
    resume = fields.Binary(string='Resume/CV', attachment=True)
    resume_filename = fields.Char()

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'agent_registration_attachment_rel',
        'registration_id',
        'attachment_id',
        string='Portfolio Images'
    )

    linkedin_url = fields.Char(string='LinkedIn Profile')
    facebook_url = fields.Char(string='Facebook Profile')

    status = fields.Selection([
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='submitted', required=True, tracking=True)

    rejection_reason = fields.Text(string='Rejection Reason', tracking=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    review_date = fields.Datetime(string='Review Date', readonly=True)
    agent_id = fields.Many2one('real.estate.agent', string='Agent Profile', readonly=True)
    submission_date = fields.Datetime(string='Submission Date', default=fields.Datetime.now, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('agent.registration') or 'New'
        return super(AgentRegistration, self).create(vals_list)

    def action_approve(self):
        """Approve and create agent + portal user (Optimized for fast execution & UI Reload)"""
        self.ensure_one()

        if self.status == 'approved':
            raise ValidationError("Already approved!")

        # Create agent profile values
        agent_vals = {
            'name': self.agent_name,
            'email': self.email,
            'phone': self.phone,
            'whatsapp': self.whatsapp or self.phone,
            'designation': self.designation,
            'expertise_level': self.expertise_level,
            'city': self.city,
            'state_id': self.state_id.id if self.state_id else False,
            'zip_code': self.zip_code,
            'license_number': self.license_number,
            'experience_years': self.experience_years,
            'short_bio': self.short_bio or f"Real estate professional from {self.city}",
            'detailed_bio': self.detailed_bio or self.short_bio,
            'languages_spoken': self.languages_spoken,
            'linkedin_url': self.linkedin_url,
            'facebook_url': self.facebook_url,
            'specializations': [(6, 0, self.specialization_ids.ids)] if self.specialization_ids else False,
            'image': self.profile_image,
            'is_active': True,
            'is_accepting_clients': True,
            'total_sales_volume': 0,
            'total_deals': 0,
            'avg_rating': 5.0,
            'review_count': 0,
        }

        try:
            # ⚡ Bypass unnecessary chatter tracking/subscriptions to speed up creation
            agent_model = self.env['real.estate.agent'].with_context(
                tracking_disable=True,
                mail_create_nosubscribe=True,
                mail_auto_subscribe=False,
                mail_create_nolog=True
            )
            agent = agent_model.create(agent_vals)

            # ⭐ CREATE PORTAL USER
            portal_user, temp_password = self._create_portal_user_for_agent(agent)
            agent.sudo().write({'user_id': portal_user.id})

            # Update the current registration record
            self.write({
                'status': 'approved',
                'agent_id': agent.id,
                'reviewed_by': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })

            # Post a note with the credentials so the admin can hand them to the agent
            if temp_password:
                self.message_post(
                    body=f"✅ Approved by {self.env.user.name}. Portal access created.<br/>"
                         f"Login: {self.email}<br/>Temporary Password: {temp_password}",
                    message_type='notification'
                )
            else:
                self.message_post(
                    body=f"✅ Approved by {self.env.user.name}. Linked to existing portal login: {self.email}",
                    message_type='notification'
                )

            # ⭐ NEW: the agent never actually heard back before - only an
            # internal chatter note was posted (visible to admins only).
            # Send them a real congratulations email now that they're approved.
            self._send_approval_email(agent, temp_password)

            # ⭐ Fix: Return the notification AND force the UI to reload immediately
            notif_message = (
                f'Agent {agent.name} created. Login: {self.email}   '
                f'Temporary Password: {temp_password}'
            ) if temp_password else (
                f'Agent {agent.name} created. Linked to existing login: {self.email}'
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success!',
                    'message': notif_message,
                    'type': 'success',
                    'sticky': True,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }

        except Exception as e:
            _logger.error(f"Error: {str(e)}")
            raise ValidationError(f"Error: {str(e)}")

    def _create_portal_user_for_agent(self, agent):
        """Create portal user account. Returns (user, temp_password).
        temp_password is None when an existing login was reused."""
        # Check if user exists
        existing_user = self.env['res.users'].sudo().search([
            ('login', '=', self.email)
        ], limit=1)

        if existing_user:
            # ⭐ FIX: don't silently turn an existing CUSTOMER login into an
            # agent login. If this email already has an approved customer
            # property registration, stop and make the admin decide
            # explicitly instead of quietly granting agent-portal access.
            existing_customer_reg = self.env['property.registration'].sudo().search([
                ('email', '=', self.email),
                ('status', '=', 'approved'),
            ], limit=1)
            if existing_customer_reg:
                raise ValidationError(
                    f"The email '{self.email}' already belongs to an existing "
                    f"customer account (registration: {existing_customer_reg.property_name}). "
                    f"Approving this agent application would silently grant that "
                    f"customer account access to the Agent Portal. If this person "
                    f"should really become an agent too, unlink or deactivate the "
                    f"conflicting customer data first, or use a different email "
                    f"for the agent profile."
                )
            _logger.info(f"User already exists: {self.email}")
            return existing_user, None

        # Get portal group
        portal_group = self.env.ref('base.group_portal')

        # Create partner (bypassing tracking overhead)
        partner_model = self.env['res.partner'].sudo().with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
            mail_auto_subscribe=False,
            mail_create_nolog=True
        )
        partner = partner_model.create({
            'name': agent.name,
            'email': self.email,
            'phone': self.phone,
            'city': self.city,
            'state_id': self.state_id.id if self.state_id else False,
            'is_company': False,
        })

        # Create portal user (bypassing tracking overhead)
        user_vals = {
            'name': agent.name,
            'login': self.email,
            'email': self.email,
            'partner_id': partner.id,
            'groups_id': [(6, 0, [portal_group.id])],
            'active': True,
        }

        user_model = self.env['res.users'].sudo().with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
            mail_auto_subscribe=False,
            mail_create_nolog=True,
            no_reset_password=True # Prevent immediate synchronous send if overridden
        )
        user = user_model.create(user_vals)

        # ⭐ Set a working password directly instead of relying only on a
        # password-reset EMAIL (which never arrives on a dev/localhost
        # instance with no outgoing mail server configured). This is what
        # actually lets the agent log in right away.
        temp_password = self._generate_temp_password()
        user.sudo().write({'password': temp_password})

        # Also try the email flow as a courtesy, in case mail IS configured
        # on this instance — but login no longer depends on it.
        try:
            user.sudo().with_context(
                mail_notify_force_send=False,
                mail_create_nolog=True
            ).action_reset_password()
        except Exception as e:
            _logger.warning(f"Password reset email could not be sent: {e}")

        _logger.info(f"✅ Portal user created: {agent.name} ({self.email})")

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
    def _send_approval_email(self, agent, temp_password=None):
        """Email the agent directly to let them know their application was
        approved. Separate from the admin-only chatter note above, which
        the agent never sees. Login credentials are only ever embedded
        here (never stored as a field) since temp_password is generated
        fresh and only exists in memory during this request."""
        self.ensure_one()
        if not self.email:
            return

        if temp_password:
            credentials_html = f"""
                <p>Your agent portal login is ready:</p>
                <ul>
                    <li><b>Login:</b> {self.email}</li>
                    <li><b>Temporary Password:</b> {temp_password}</li>
                </ul>
                <p>Please log in and change your password after your first sign-in.</p>
            """
        else:
            credentials_html = f"""
                <p>You can log in to your agent portal with your existing account
                (<b>{self.email}</b>).</p>
            """

        body_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
                <h2 style="color: #c7a24a; margin-bottom: 4px;">🎉 Congratulations, {self.agent_name}!</h2>
                <p>Your agent application with <b>Real Estate Management</b> has been approved.</p>
                <p>You are now officially a registered agent and can start managing listings and
                   clients through your agent portal right away.</p>
                {credentials_html}
                <p style="margin-top: 20px;">Welcome aboard!<br/>Real Estate Team</p>
            </div>
        """

        try:
            mail = self.env['mail.mail'].sudo().create({
                'subject': 'Congratulations! Your Agent Application is Approved 🎉',
                'email_from': self.env.user.email_formatted or 'noreply@example.com',
                'email_to': self.email,
                'body_html': body_html,
            })
            # ⭐ FIX: mail.mail.send() defaults to raise_exception=False, which
            # means it silently swallows ANY delivery failure (no outgoing
            # mail server configured, auth error, etc.) and just marks the
            # mail record's state as 'exception' internally — it never
            # raises, so the `except Exception` below never actually ran
            # and nothing was ever logged. Passing raise_exception=True
            # forces real failures to surface here so we can log them and
            # tell the admin, instead of the agent just never getting the
            # email with no trace of why.
            mail.send(raise_exception=True)
            _logger.info("Approval congratulations email sent to %s", self.email)
        except Exception as e:
            _logger.error(
                "Could not send approval congratulations email to %s: %s",
                self.email, e, exc_info=True,
            )
            self.message_post(
                body=Markup(
                    "⚠️ <b>Could not send the congratulations email</b> to {email}.<br/>"
                    "Reason: {reason}<br/>"
                    "Go to <i>Settings → Technical → Email → Outgoing Mail Servers</i> "
                    "and make sure a valid SMTP server is configured, then use "
                    "<i>Test Connection</i> there to confirm it works."
                ).format(email=self.email, reason=str(e)),
                message_type='notification',
            )

    def action_reject(self):
        self.ensure_one()
        if self.status == 'rejected':
            raise ValidationError("Already rejected!")
        return {
            'name': 'Reject Registration',
            'type': 'ir.actions.act_window',
            'res_model': 'agent.registration.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_registration_id': self.id}
        }

    def action_view_agent_profile(self):
        self.ensure_one()
        if not self.agent_id:
            raise ValidationError("No agent profile created!")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agent Profile',
            'res_model': 'real.estate.agent',
            'res_id': self.agent_id.id,
            'view_mode': 'form',
        }

    def _send_admin_notification(self):
        """Send bell notification + activity + beep sound"""
        self.ensure_one()

        # 🎯 Admin user
        admin_user = self.env.ref('base.user_admin')
        admin_partner = admin_user.partner_id

        # 📝 Create Activity
        self.env['mail.activity'].sudo().create({
            'activity_type_id': self.env.ref(
                'real_estate_management.activity_agent_registration_review'
            ).id,
            'summary': 'Approve Agent Registration',
            'note': f'New agent registration submitted by {self.agent_name}',
            'res_model_id': self.env['ir.model']._get(self._name).id,
            'res_id': self.id,
            'user_id': admin_user.id,
            'date_deadline': fields.Date.today(),
        })

        # 🔔 Bell + 🔊 Beep
        self.message_post(
            body=Markup(f"""
                🔔 <b>New Agent Registration Submitted</b><br/>
                <ul>
                    <li><b>Name:</b> {self.agent_name}</li>
                    <li><b>City:</b> {self.city}</li>
                    <li><b>Experience:</b> {self.experience_years} years</li>
                </ul>
            """),
            message_type='notification',
            partner_ids=[admin_partner.id],
            subtype_xmlid='mail.mt_comment',
        )