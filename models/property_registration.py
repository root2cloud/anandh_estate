# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from markupsafe import Markup


class PropertyRegistration(models.Model):
    _name = 'property.registration'
    _description = 'Property Registration'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    customer_name = fields.Char(string='Customer Name*', required=True)
    property_name = fields.Char(string='Property Name*', required=True)
    phone_number = fields.Char(string='Phone Number*', required=True)
    place = fields.Char(string='Place*', required=True)
    category = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('agricultural', 'Agricultural'),
    ], string='Category*', required=True)
    sq_yards = fields.Float(string='Square Yards*', required=True)
    price = fields.Float(string='Expected Price*', required=True)
    location = fields.Char(string='Exact Location*', required=True)
    city = fields.Char(string='City*', required=True)
    state = fields.Char(string='State*', required=True)
    country_id = fields.Many2one(
        'res.country', string='Country*', required=True,
        default=lambda self: self.env['res.country'].search([('code', '=', 'IN')], limit=1).id
    )
    image = fields.Image(string='Main Image*', max_width=1024, max_height=1024)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)

    attachment_ids = fields.One2many('ir.attachment', 'res_id',
                                     domain=lambda self: [('res_model', '=', self._name)],
                                     string='Additional Images')

    email = fields.Char(string="Customer Email*")
    facing_direction = fields.Selection([
        ('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West'),
        ('northeast', 'North-East'), ('northwest', 'North-West'),
        ('southeast', 'South-East'), ('southwest', 'South-West')
    ], string='Facing Direction')
    road_width = fields.Float(string='Road Width (Feet)')

    # ⭐ NEW: captures the free-text "Property Description" textarea from
    # the public Customer Registration ("Selling a Property") form so it
    # isn't silently discarded, and flows through to the live property's
    # short description on approval (see _prepare_property_vals below).
    description = fields.Text(string='Property Description')

    # ⭐ NEW: link back to the customer.registration record this
    # submission came from, when it was created via the "Selling a
    # Property" branch of the public Customer Registration form. Empty
    # for submissions from the standalone /property/register form or the
    # Agent Portal - purely informational/traceability, nothing else
    # depends on it.
    customer_registration_id = fields.Many2one(
        'customer.registration', string='Customer Registration',
        readonly=True, copy=False,
        help="The customer registration this property submission was created from, "
             "if it came from the public 'Selling a Property' registration form."
    )

    # Documents
    aadhar_document = fields.Binary(string="Aadhaar Card")
    aadhar_filename = fields.Char(string="Aadhaar Filename")

    agreement_document = fields.Binary(string="Agreement Document")
    agreement_filename = fields.Char(string="Agreement Filename")

    # Track if portal user is active
    is_portal_active = fields.Boolean(string="Portal Active", default=False, copy=False)

    # ⭐ NEW: remembers which property.property this registration created,
    # so later edits/approvals know what to update instead of losing the link.
    property_id = fields.Many2one(
        'property.property', string='Linked Property',
        readonly=True, copy=False,
        help="The live property record created when this registration was approved."
    )

    # ⭐ NEW: lets the "Property Submissions" backend menu distinguish a
    # request that came from the public "Sell your property" form
    # (Customer) versus one submitted by a logged-in Agent through their
    # portal ("Add Property"). Purely informational/filterable - doesn't
    # change any existing behaviour for customer submissions.
    source = fields.Selection([
        ('customer', 'Customer'),
        ('agent', 'Agent'),
    ], string='Source', default='customer', tracking=True)

    agent_id = fields.Many2one(
        'real.estate.agent', string='Submitted By Agent',
        readonly=True, copy=False,
        help="The agent who submitted this property, if it came from the Agent Portal."
    )

    # ⭐ NEW: agent submissions pick their category from the real,
    # dynamic property.category list (not the fixed 3-option Selection
    # below). When set, this is used instead of guessing a category from
    # text - existing customer submissions never set this, so their
    # behaviour is unchanged.
    category_id = fields.Many2one(
        'property.category', string='Exact Property Category',
        copy=False,
        help="The precise category selected (used for Agent submissions). "
             "When empty, the Category field above is used instead."
    )

    # ─────────────────────────────────────────────────────────────
    # Shared vals builder — used both when creating AND when syncing
    # ─────────────────────────────────────────────────────────────
    def _prepare_property_vals(self):
        self.ensure_one()

        # ⭐ FIX: prefer the exact category (set by Agent submissions)
        # over guessing one from the free-text Category selection - the
        # old get-or-create-by-name logic below is untouched and still
        # runs exactly as before whenever category_id isn't set
        # (i.e. every existing customer submission).
        if self.category_id:
            category = self.category_id
        else:
            # Get or create category with SEO title
            category = self.env['property.category'].search([('name', '=ilike', self.category)], limit=1)
            if not category:
                category = self.env['property.category'].create({
                    'name': self.category,
                    'seo_title': f'{self.category.title()} Properties',
                    'seo_description': f'Browse {self.category} properties'
                })

        country_id = self.country_id.id if self.country_id else self.env.ref('base.in').id

        # Safely Get or Create State so Odoo never passes False
        state = self.env['res.country.state'].search([('name', '=ilike', self.state)], limit=1)
        if not state:
            state = self.env['res.country.state'].create({
                'name': self.state,
                'code': self.state[:3].upper() if self.state else 'UNK',
                'country_id': country_id
            })

        return {
            'name': self.property_name or self.customer_name or 'Property',
            'city': self.city or 'Unknown',
            'zip_code': '000000',
            'state_id': state.id,
            'country_id': country_id,
            'category_id': category.id,
            'image': self.image,
            'price': self.price or 0.0,
            'plot_area': self.sq_yards or 0.0,
            'facing_direction': self.facing_direction or 'north',
            'road_width': self.road_width or 30.0,
            'street': self.location or 'N/A',
            # ⭐ NEW: carries the "Property Description" text through to
            # the live property record. Existing submissions that never
            # set description (agent flow, older customer flow) simply
            # write an empty string here, same as before this field existed.
            'short_description': self.description or '',
            'adhar_image': self.aadhar_document or b'',
            'adhar_filename': self.aadhar_filename or 'Aadhar.pdf',
            'agreement_document': self.agreement_document or b'',
            'agreement_filename': self.agreement_filename or 'Agreement.pdf',
            'contact_name': self.customer_name or 'N/A',
            'contact_phone': self.phone_number or 'N/A',
            'contact_email': self.email or 'noreply@example.com',
            'seo_title': self.property_name or 'Property Listing',
        }

    def action_approve(self):
        for rec in self:
            # ⭐ FIX: previously only checked `status == 'approved'`. Now
            # also covers Agent submissions, whose linked property is
            # already created (so the agent sees it instantly in their
            # own portal) at submission time - status starts as
            # 'submitted' so it still shows up in "Property Submissions"
            # for review, but there's nothing new to CREATE here, only
            # sync + (for agents) publish. Existing customer flow is
            # unaffected: property_id is empty until their first
            # approval, so this still falls through to the create-new
            # logic below exactly as before.
            if rec.property_id:
                rec._sync_to_property()
                if rec.source == 'agent':
                    # ⭐ FIX: only mark it approved so it now shows up in
                    # the backend "Property Listings" - it was
                    # deliberately hidden from there since submission (see
                    # is_agent_submission_approved on property.property).
                    # Publishing to the public website is NOT automatic
                    # anymore; admin must toggle "Published" manually from
                    # Property Listings, same as any other property.
                    rec.property_id.is_agent_submission_approved = True
                rec.status = 'approved'
                continue

            vals = rec._prepare_property_vals()
            vals.update({
                'title_status': 'pending',
                'property_website_url': 'https://example.com',
                'registration_charges': 7.0,
                'emi_available': True,
                'nearby_landmarks': 'To be updated',
            })

            # Create the property
            property_obj = self.env['property.property'].with_context(default_status=False).create(vals)
            rec.property_id = property_obj.id

            # Copy attachments to new property
            attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'property.registration'),
                ('res_id', '=', rec.id)
            ])
            for attach in attachments:
                attach.copy({'res_model': 'property.property', 'res_id': property_obj.id})

            # Portal User Creation Logic
            if rec.email:
                partner = self.env['res.partner'].sudo().search([('email', '=', rec.email)], limit=1)
                if not partner:
                    partner = self.env['res.partner'].sudo().create({
                        'name': rec.customer_name,
                        'email': rec.email,
                        'phone': rec.phone_number,
                        'city': rec.city,
                    })

                user = self.env['res.users'].sudo().search([('login', '=', rec.email)], limit=1)
                if not user:
                    portal_group = self.env.ref('base.group_portal')
                    user = self.env['res.users'].sudo().with_context(no_reset_password=False).create({
                        'name': rec.customer_name,
                        'login': rec.email,
                        'email': rec.email,
                        'partner_id': partner.id,
                        'groups_id': [(6, 0, [portal_group.id])],
                    })
                    user.action_reset_password()
                    rec.is_portal_active = True
                else:
                    rec.is_portal_active = True

            rec.status = 'approved'

        # ⭐ FORCE PAGE RELOAD
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _sync_to_property(self):
        """Push the current registration values onto the already-linked property record."""
        for rec in self:
            if not rec.property_id or not rec.property_id.exists():
                raise UserError(
                    "This registration is approved but has no linked property to update. "
                    "Please contact your administrator."
                )
            vals = rec._prepare_property_vals()

            # ⭐ FIX: property.registration has no zip_code field of its
            # own, so _prepare_property_vals() always returns a
            # hardcoded placeholder here. That was harmless while this
            # sync only ever ran on Customer submissions (which never had
            # a real zip code to begin with), but now that Agent
            # submissions also flow through here on Approve, blindly
            # writing this placeholder would silently wipe out the real
            # zip code the agent originally entered. Never let sync
            # touch zip_code - whatever is already on the live property
            # is left exactly as it is.
            vals.pop('zip_code', None)

            rec.property_id.write(vals)
            rec.message_post(body="🔄 Linked property information was updated from this registration.")

    # ⭐ NEW: auto-sync whenever key fields are edited after approval
    def write(self, vals):
        res = super().write(vals)
        sync_fields = {
            'property_name', 'customer_name', 'phone_number', 'email', 'city',
            'state', 'country_id', 'location', 'price', 'sq_yards', 'category',
            'facing_direction', 'road_width', 'image', 'aadhar_document',
            'aadhar_filename', 'agreement_document', 'agreement_filename',
            'description',
        }
        if sync_fields.intersection(vals.keys()):
            for rec in self:
                if rec.status == 'approved' and rec.property_id:
                    rec._sync_to_property()
        return res

    def action_reject(self):
        """When rejected, send a rejection email to the user"""
        for record in self:
            record.status = 'rejected'

            # ⭐ NEW: if this was an Agent submission whose property was
            # already live/unpublished, make sure a rejection actually
            # keeps it off the public site.
            if record.source == 'agent' and record.property_id:
                record.property_id.is_published = False

            if record.create_uid and record.create_uid.email:
                mail_template = self.env.ref('real_estate_management.mail_template_property_rejection',
                                             raise_if_not_found=False)
                if mail_template:
                    mail_template.send_mail(record.id, force_send=True)
                else:
                    record.message_post(
                        body=f"Rejection mail template not found, but property '{record.name}' was rejected.",
                    )

        # ⭐ FORCE PAGE RELOAD
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _send_admin_notification(self):
        """Send bell notification + beep sound + activity for property registration"""
        self.ensure_one()

        admin_user = self.env.ref('base.user_admin')
        admin_partner = admin_user.partner_id

        self.env['mail.activity'].sudo().create({
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'summary': 'Approve Property Registration',
            'note': f'New property registration submitted by {self.customer_name}',
            'res_model_id': self.env['ir.model']._get(self._name).id,
            'res_id': self.id,
            'user_id': admin_user.id,
            'date_deadline': fields.Date.today(),
        })

        self.message_post(
            body=Markup(f"""
                🏠 <b>New Property Registration Submitted</b><br/>
                <ul>
                    <li><b>Customer:</b> {self.customer_name}</li>
                    <li><b>Property:</b> {self.property_name}</li>
                    <li><b>City:</b> {self.city}</li>
                    <li><b>Price:</b> ₹{self.price}</li>
                </ul>
            """),
            message_type='notification',
            partner_ids=[admin_partner.id],
            subtype_xmlid='mail.mt_comment',
        )