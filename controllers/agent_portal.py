# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError
import base64
import logging

_logger = logging.getLogger(__name__)


class AgentPortalController(http.Controller):
    """Secure Agent Portal - Similar to Family Members"""

    def _get_logged_in_agent(self):
        """Get agent for current logged-in user"""
        if not request.env.user or request.env.user._is_public():
            return False

        # Search for agent linked to this user
        agent = request.env['real.estate.agent'].search([
            ('user_id', '=', request.env.user.id),
            ('is_active', '=', True)
        ], limit=1)

        return agent

    def _deny_agent_access(self, message=None):
        """⭐ Consistent 'access restricted' screen for any non-agent
        (e.g. a customer) who tries to reach an agent-only page, instead of
        silently redirecting them to /my with no explanation.

        ⭐ FIX: mirrors the Customer Dashboard's agent block. When the
        visitor here is specifically a logged-in Customer (not just any
        non-agent), show a tailored message and send them to their own
        Customer Dashboard instead of the generic buttons.
        """
        user = request.env.user
        is_customer = bool(user) and not user._is_public() and bool(user.partner_id.sudo().is_real_estate_customer)

        if is_customer and not message:
            return request.render('real_estate_management.agent_no_access', {
                'message': 'The Agent Portal is reserved for registered agents. '
                            'You are logged in as a Customer - please use the Customer Dashboard instead.',
                'customer_redirect': True,
            })

        return request.render('real_estate_management.agent_no_access', {
            'message': message or 'You do not have access to the Agent Portal. '
                                   'This area is reserved for registered agents.',
        })

    def _is_internal_staff(self):
        """⭐ True only for real backend/admin users - never for portal
        customers or portal agents. Used to lock down the internal /dashboard."""
        user = request.env.user
        return bool(user) and not user._is_public() and user.has_group('base.group_user')

    @http.route(['/my/agent/dashboard'], type='http', auth='public', website=True)
    def agent_dashboard(self, **kw):
        """Main dashboard - like family members portal"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        # ⭐ Same fix as agent_my_properties: use sudo() so related
        #    sub-models (category, gallery, etc.) don't throw AccessError
        #    for portal agents. Explicit agent_id domain keeps this
        #    scoped to only this agent's own properties.
        properties = request.env['property.property'].sudo().search([
            ('agent_id', '=', agent.id)
        ], order='create_date desc')

        # Stats
        stats = {
            'total_properties': len(properties),
            'published': len(properties.filtered('is_published')),
            'pending': len(properties.filtered(lambda p: not p.is_published)),
            'total_views': sum(properties.mapped('views')),
        }

        return request.render('real_estate_management.agent_portal_dashboard', {
            'agent': agent,
            'properties': properties[:10],  # Show recent 10
            'stats': stats,
        })

    @http.route(['/my/agent/profile'], type='http', auth='user', website=True)
    def agent_profile(self, **kw):
        """View own profile"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        return request.render('real_estate_management.agent_portal_profile', {
            'agent': agent,
        })

    @http.route(['/my/agent/properties'], type='http', auth='user', website=True)
    def agent_my_properties(self, **kw):
        """List of MY properties only"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        # ⭐ FIX: .sudo() is required here. property.category (and other
        #    related sub-models like gallery images) only grant read
        #    access to Internal Users - a portal Agent user has no ACL
        #    on 'property.category'. The agent_portal_my_properties
        #    template reads prop.category_id.name for each row, which
        #    was throwing "You are not allowed to access 'Property
        #    Category'" for portal agents. The domain below already
        #    restricts the result to this agent's own properties, so
        #    sudo() here does not leak any other agent's data.
        properties = request.env['property.property'].sudo().search([
            ('agent_id', '=', agent.id)
        ], order='create_date desc')

        return request.render('real_estate_management.agent_portal_my_properties', {
            'agent': agent,
            'properties': properties,
            'success': kw.get('success'),
        })

    @http.route(['/my/agent/property/add'], type='http', auth='user', website=True)
    def agent_add_property_form(self, **kw):
        """Add property form - like registration form"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        categories = request.env['property.category'].sudo().search([])

        return request.render('real_estate_management.agent_portal_add_property', {
            'agent': agent,
            'categories': categories,
            'error': kw.get('error'),
        })

    @http.route(['/my/agent/property/submit'], type='http', auth='user', website=True, csrf=False, methods=['POST'])
    def agent_submit_property(self, **post):
        """Submit property with detailed error handling"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        try:
            _logger.info(f"=== Starting property submission for agent: {agent.name} ===")

            # Get uploaded files
            files = request.httprequest.files
            main_image = files.get('main_image')
            gallery_images = files.getlist('gallery_images')

            _logger.info(f"POST data received: {list(post.keys())}")
            _logger.info(f"Files received: main_image={main_image is not None}, gallery_count={len(gallery_images)}")

            # Get state from form or use agent's state
            state_id = post.get('state_id')
            if state_id and state_id != '':
                try:
                    state_id = int(state_id)
                except (ValueError, TypeError):
                    state_id = agent.state_id.id if agent.state_id else False
            else:
                state_id = agent.state_id.id if agent.state_id else False

            # ⭐ BUILD PROPERTY VALUES WITH ALL REQUIRED FIELDS
            property_vals = {
                # Basic required fields
                'name': post.get('property_name', '').strip() or 'Untitled Property',
                'agent_id': agent.id,
                'is_published': False,
                # ⭐ NEW: hides this property from the backend "Property
                # Listings" until an admin approves it in "Property
                # Submissions". See is_agent_submission_approved on
                # property.property for details.
                'is_agent_submission_approved': False,
                'status': 'available',

                # Location (required)
                'city': post.get('city', '').strip() or 'Not Specified',
                'state_id': state_id,
                'zip_code': post.get('zip_code', '').strip() or '000000',

                # Price & Area (required)
                'price': float(post.get('price', 0) or 0),
                'plot_area': float(post.get('plot_area', 100) or 100),

                # ⭐ REQUIRED FIELDS WITH DEFAULTS
                'facing_direction': 'east',  # Default value
                'road_width': 30.0,  # Default 30 feet
                'title_status': 'pending',  # Default status
                'seo_title': post.get('property_name', '').strip() or 'Property for Sale',
                'nearby_landmarks': post.get('address', '').strip() or 'Updated soon',

                # Contact info
                'contact_name': agent.name,
                'contact_email': agent.email,
                'contact_phone': agent.phone,
            }

            # Add optional fields if provided
            if post.get('property_type'):
                property_vals['property_type'] = post.get('property_type')

            if post.get('bedrooms'):
                try:
                    property_vals['bedrooms'] = int(post.get('bedrooms', 0))
                except (ValueError, AttributeError):
                    property_vals['bedrooms'] = 0

            if post.get('bathrooms'):
                try:
                    property_vals['bathrooms'] = int(post.get('bathrooms', 0))
                except (ValueError, AttributeError):
                    property_vals['bathrooms'] = 0

            if post.get('street'):
                property_vals['street'] = post.get('street').strip()

            # if post.get('address'):
            #     property_vals['address'] = post.get('address').strip()

            if post.get('short_description'):
                property_vals['short_description'] = post.get('short_description').strip()

            if post.get('description'):
                property_vals['detailed_description'] = post.get('description').strip()

            # Category
            category_id = post.get('category_id')
            if category_id and category_id != '':
                try:
                    property_vals['category_id'] = int(category_id)
                except (ValueError, TypeError):
                    pass

            # Main image
            if main_image and hasattr(main_image, 'read'):
                try:
                    image_data = main_image.read()
                    if image_data:
                        property_vals['image'] = base64.b64encode(image_data)
                        _logger.info("Main image uploaded successfully")
                except Exception as img_err:
                    _logger.error(f"Image upload error: {img_err}")

            _logger.info(f"Creating property with values: {property_vals}")

            # Create property
            PropertyModel = request.env['property.property'].sudo()
            property_obj = PropertyModel.create(property_vals)

            _logger.info(f"✅ Property created successfully: ID={property_obj.id}, Name={property_obj.name}")

            # Handle gallery images
            if gallery_images:
                GalleryModel = request.env['property.gallery.image'].sudo()
                for idx, img_file in enumerate(gallery_images):
                    if img_file and hasattr(img_file, 'read') and img_file.filename:
                        try:
                            img_data = img_file.read()
                            if img_data:
                                GalleryModel.create({
                                    'property_id': property_obj.id,
                                    'image': base64.b64encode(img_data),
                                    'name': img_file.filename,
                                })
                                _logger.info(f"Gallery image {idx + 1} uploaded: {img_file.filename}")
                        except Exception as gal_err:
                            _logger.error(f"Gallery image {idx + 1} error: {gal_err}")

            _logger.info("=== Property submission completed successfully ===")

            # ⭐ NEW: also create a linked "Property Submissions" entry so
            # this agent-submitted property shows up in the same backend
            # queue (Real Estate > Property Submissions) that customer
            # "Sell your property" requests already use. This does NOT
            # change anything above - the live property record is still
            # created immediately exactly as before, so the agent still
            # sees it right away in their own "My Properties"/Dashboard.
            # This entry is purely for admin visibility + Approve/Reject;
            # Approve now also publishes the listing, Reject unpublishes it.
            try:
                category_rec = property_obj.category_id
                category_guess = 'residential'
                if category_rec and category_rec.name:
                    cname = category_rec.name.lower()
                    if 'commercial' in cname:
                        category_guess = 'commercial'
                    elif 'agri' in cname:
                        category_guess = 'agricultural'

                registration_vals = {
                    'customer_name': agent.name,
                    'property_name': property_obj.name,
                    'phone_number': agent.phone or 'N/A',
                    'email': agent.email or '',
                    'place': (post.get('address', '') or '').strip() or property_obj.city,
                    'category': category_guess,
                    'category_id': category_rec.id if category_rec else False,
                    'sq_yards': property_obj.plot_area,
                    'price': property_obj.price,
                    'location': property_obj.street or property_obj.city,
                    'city': property_obj.city,
                    # ⭐ FIX: use the property's own already-resolved
                    # state (which falls back through the submitted form
                    # value / agent's state / etc - see state_id logic
                    # above) instead of only the agent's profile state.
                    # Avoids ever passing an empty string here, which
                    # would make _prepare_property_vals() search for a
                    # blank-named state and could create a bogus one.
                    'state': property_obj.state_id.name if property_obj.state_id else '',
                    'image': property_obj.image,
                    'status': 'submitted',
                    'source': 'agent',
                    'agent_id': agent.id,
                    'property_id': property_obj.id,
                }
                registration_rec = request.env['property.registration'].sudo().create(registration_vals)
                registration_rec._send_admin_notification()
                _logger.info(f"✅ Linked Property Submission entry created: ID={registration_rec.id}")
            except Exception as reg_err:
                # Never let the submissions-queue entry block the actual
                # property creation above - the property itself already
                # saved successfully regardless of this.
                _logger.error(f"Could not create Property Submission entry for agent property {property_obj.id}: {reg_err}")

            return request.redirect('/my/agent/properties?success=1')

        except Exception as e:
            _logger.exception(f"❌ CRITICAL ERROR in property submission")
            _logger.error(f"Error type: {type(e).__name__}")
            _logger.error(f"Error message: {str(e)}")

            return request.redirect('/my/agent/property/add?error=1')

    @http.route(['/my/agent/property/<int:property_id>'], type='http', auth='user', website=True)
    def agent_property_detail(self, property_id, **kw):
        """View property - only if belongs to THIS agent"""
        agent = self._get_logged_in_agent()

        if not agent:
            return self._deny_agent_access()

        # ⭐ sudo() so category_id / gallery_image_ids can be read in the
        #    detail template without AccessError; ownership is still
        #    strictly checked right below before anything is rendered.
        property_obj = request.env['property.property'].sudo().browse(property_id)

        # Security: Check ownership
        if not property_obj.exists() or property_obj.agent_id != agent:
            return self._deny_agent_access('You do not have access to this property.')

        return request.render('real_estate_management.agent_portal_property_detail', {
            'agent': agent,
            'property': property_obj,
        })

    @http.route(['/my/agent/property/update_status'], type='http', auth='user', methods=['POST'], csrf=True)
    def update_property_status(self, property_id=None, new_status=None, **kwargs):
        """Update property status - HTTP POST endpoint"""
        try:
            _logger.info(f"📝 Status update request: property_id={property_id}, new_status={new_status}")

            # Validate inputs
            if not property_id or not new_status:
                return request.make_json_response({
                    'success': False,
                    'message': 'Missing required parameters.'
                })

            # Get logged in agent
            agent = self._get_logged_in_agent()

            if not agent:
                return request.make_json_response({
                    'success': False,
                    'message': 'Agent not found. Please login again.'
                })

            # Get property and verify ownership
            property_obj = request.env['property.property'].sudo().search([
                ('id', '=', int(property_id)),
                ('agent_id', '=', agent.id)
            ], limit=1)

            if not property_obj:
                return request.make_json_response({
                    'success': False,
                    'message': 'Property not found or you do not have permission.'
                })

            # Validate status
            if new_status not in ['available', 'sold', 'rented']:
                return request.make_json_response({
                    'success': False,
                    'message': 'Invalid status value.'
                })

            # Update status
            old_status = property_obj.status
            property_obj.write({'status': new_status})

            _logger.info(f"✅ Property '{property_obj.name}' status: {old_status} → {new_status} (Agent: {agent.name})")

            return request.make_json_response({
                'success': True,
                'message': f'Status updated to "{new_status.upper()}" successfully!',
                'new_status': new_status
            })

        except Exception as e:
            _logger.exception(f"❌ Error updating status: {e}")
            return request.make_json_response({
                'success': False,
                'message': 'An error occurred. Please try again.'
            })

    @http.route('/dashboard', type='http', auth='user', website=True)
    def real_estate_dashboard(self, **kwargs):
        # ⭐ FIX: this used to have NO real access check at all (the old
        # comment said "Assuming admin access check" but never performed
        # one), so any logged-in user - including a customer - could open
        # /dashboard and see every property, agent and registration via
        # .sudo(). Now it's locked to internal staff only.
        if not self._is_internal_staff():
            return self._deny_agent_access(
                'This dashboard is restricted to internal staff.'
            )

        Property = request.env['property.property'].sudo()
        Agent = request.env['real.estate.agent'].sudo()
        PropReg = request.env['property.registration'].sudo()
        AgentReg = request.env['agent.registration'].sudo()
        Category = request.env['property.category'].sudo()

        all_properties = Property.search([])
        agents = Agent.search([])
        prop_regs = PropReg.search([])
        agent_regs = AgentReg.search([])
        categories = Category.search([])
        city_list = sorted(list(set([p.city for p in all_properties if p.city])))

        # Compute stats, JSON for charts, etc.
        values = {
            'all_properties': all_properties,
            'agents': agents,
            'prop_regs': prop_regs,
            'agent_regs': agent_regs,
            'categories': categories,
            'city_list': city_list,
            # Add more as needed
        }
        return request.render('real_estate_management.real_estate_dashboard', values)