from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
import secrets
import string

_logger = logging.getLogger(__name__)


class RealEstateAgent(models.Model):
    _name = 'real.estate.agent'
    _description = 'Real Estate Agent'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'total_sales_volume desc, total_deals desc'

    # Basic Information
    name = fields.Char(string='Agent Name*', required=True, tracking=True)
    image = fields.Image(string='Profile Photo', max_width=400, max_height=400)
    designation = fields.Selection([
        ('agent', 'Agent'),
        ('senior_agent', 'Senior Agent'),
        ('principal_agent', 'Principal Agent'),
        ('broker', 'Broker'),
    ], string='Designation*', required=True, default='agent')

    expertise_level = fields.Selection([
        ('standard', 'Standard Agent'),
        ('luxury', 'Luxury Expert'),
    ], string='Expertise Level', default='standard')

    # Contact Details
    email = fields.Char(string='Email*', required=True)
    phone = fields.Char(string='Phone*', required=True)
    whatsapp = fields.Char(string='WhatsApp Number')

    # Location
    city = fields.Char(string='City*', required=True)
    state_id = fields.Many2one('res.country.state', string='State')
    zip_code = fields.Char(string='ZIP Code')

    # Professional Details
    license_number = fields.Char(string='License Number')
    experience_years = fields.Integer(string='Years of Experience', default=0)
    specializations = fields.Many2many(
        'property.category',
        'agent_category_rel',
        'agent_id',
        'category_id',
        string='Property Specializations'
    )

    # Performance Metrics
    total_sales_volume = fields.Monetary(
        string='Total Sales Volume',
        currency_field='currency_id',
        help='Total value of properties sold'
    )
    total_deals = fields.Integer(string='Total Deals Closed', default=0)
    avg_rating = fields.Float(string='Average Rating', digits=(2, 1), default=5.0)
    review_count = fields.Integer(string='Number of Reviews', default=0)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id.id
    )

    # Linked Properties
    property_ids = fields.One2many(
        'property.property',
        'agent_id',
        string='Assigned Properties'
    )
    active_property_count = fields.Integer(
        string='Active Listings',
        compute='_compute_active_property_count',
        store=True
    )

    # Bio & Description
    short_bio = fields.Text(string='Short Bio', help='Brief introduction (100-200 chars)')
    detailed_bio = fields.Html(string='Detailed Biography')

    # Achievements
    awards = fields.Text(string='Awards & Certifications')
    languages_spoken = fields.Char(string='Languages Spoken', default='English, Hindi')

    # Availability
    is_active = fields.Boolean(string='Active Agent', default=True)
    is_accepting_clients = fields.Boolean(string='Accepting New Clients', default=True)

    # SEO
    seo_keywords = fields.Char(string='SEO Keywords')

    # Social Media
    linkedin_url = fields.Char(string='LinkedIn Profile')
    facebook_url = fields.Char(string='Facebook Profile')

    user_id = fields.Many2one('res.users', string='Portal User', readonly=True,
                              help='Portal login account for this agent')

    @api.depends('property_ids', 'property_ids.is_published')
    def _compute_active_property_count(self):
        for agent in self:
            agent.active_property_count = len(agent.property_ids.filtered('is_published'))

    @api.constrains('email')
    def _check_email(self):
        for agent in self:
            if agent.email and '@' not in agent.email:
                raise ValidationError("Please enter a valid email address")

    @api.constrains('avg_rating')
    def _check_rating(self):
        for agent in self:
            if agent.avg_rating < 0 or agent.avg_rating > 5:
                raise ValidationError("Rating must be between 0 and 5")

        # ⭐⭐⭐ CORRECT INDENTATION - AT CLASS LEVEL ⭐⭐⭐

    def action_create_portal_user(self):
        """Create portal user for agent to access portal"""
        for agent in self:
            # Validation: Check if user already exists
            if agent.user_id:
                raise UserError(_('This agent already has a portal user account!'))

            # Validation: Email is required
            if not agent.email:
                raise UserError(_('Email address is required to create portal user!'))

            # Check if a user with this email already exists
            existing_user = self.env['res.users'].sudo().search([
                ('login', '=', agent.email)
            ], limit=1)

            if existing_user:
                # Link existing user to agent
                agent.write({'user_id': existing_user.id})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('User Linked'),
                        'message': _('Existing user "%s" has been linked to this agent.') % existing_user.name,
                        'type': 'info',
                        'sticky': False,
                    }
                }

            try:
                # Get portal group
                portal_group = self.env.ref('base.group_portal')

                # Create partner first
                partner = self.env['res.partner'].sudo().create({
                    'name': agent.name,
                    'email': agent.email,
                    'phone': agent.phone,
                    'city': agent.city,
                    'zip': agent.zip_code,
                    'state_id': agent.state_id.id if agent.state_id else False,
                    'company_type': 'person',
                })

                # Create portal user
                user = self.env['res.users'].sudo().create({
                    'name': agent.name,
                    'login': agent.email,
                    'email': agent.email,
                    'partner_id': partner.id,
                    'groups_id': [(6, 0, [portal_group.id])],
                    'active': True,
                })

                # Link user to agent
                agent.write({'user_id': user.id})

                # ⭐ Set a working password directly instead of relying only on
                # a password-reset EMAIL (which never arrives on a dev/localhost
                # instance with no outgoing mail server configured). This is
                # what actually lets the agent log in right away.
                temp_password = self._generate_temp_password()
                user.sudo().write({'password': temp_password})

                # Also try the email flow as a courtesy, in case mail IS
                # configured on this instance — but login no longer depends on it.
                try:
                    user.action_reset_password()
                except Exception as e:
                    _logger.warning(f"Password reset email could not be sent: {e}")

                message = _(
                    'Portal user created! Login: %s   Temporary Password: %s\n'
                    'Share these credentials with the agent — they can change '
                    'the password after logging in at /my/agent/dashboard.'
                ) % (agent.email, temp_password)

                _logger.info(f"✅ Portal user created for agent: {agent.name} ({agent.email})")

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success!'),
                        'message': message,
                        'type': 'success',
                        'sticky': True,
                    }
                }

            except Exception as e:
                _logger.error(f"❌ Error creating portal user for {agent.name}: {str(e)}")
                raise UserError(_('Failed to create portal user: %s') % str(e))

    @api.model
    def _generate_temp_password(self, length=10):
        """Generate a readable random password (letters + digits, at least
        one of each) for a freshly-created portal login."""
        alphabet = string.ascii_letters + string.digits
        while True:
            pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
            if any(c.isdigit() for c in pwd) and any(c.isalpha() for c in pwd):
                return pwd


    def action_view_properties(self):
        """View all properties assigned to this agent"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Properties',
            'res_model': 'property.property',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    def _compute_access_url(self):
        """Override portal URL"""
        super(RealEstateAgent, self)._compute_access_url()
        for agent in self:
            agent.access_url = '/my/agent/dashboard'



