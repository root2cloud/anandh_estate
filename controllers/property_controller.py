# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import json
from odoo.tools.json import scriptsafe as json_scriptsafe
import base64
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class RealEstateController(http.Controller):

    # ─────────────────────────────────────────────────────────────
    # API ENDPOINT
    # ─────────────────────────────────────────────────────────────
    @http.route('/api/investment-news', type='http', auth='public', website=True, methods=['GET'], csrf=False)
    def api_investment_news(self, **kwargs):
        city = kwargs.get('city', '').strip()
        Property = request.env['property.property'].sudo()

        news = ''
        try:
            if city:
                news = Property.get_daily_investment_news(city)
                _logger.info(f'[API] City news for "{city}": {len(news)} chars')
            else:
                news = Property.get_trending_investment_news()
                _logger.info(f'[API] Trending news: {len(news)} chars')
        except Exception as e:
            _logger.error(f'[API] News fetch error: {e}')
            news = ''

        result = json.dumps({'city': city, 'news': news})
        return request.make_response(
            result,
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-cache, no-store'),
            ]
        )

    # ─────────────────────────────────────────────────────────────
    # PROPERTY Q&A (AI-answered, grounded in that property's own facts)
    # ─────────────────────────────────────────────────────────────
    @http.route('/api/property/<int:property_id>/ask', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def api_property_ask(self, property_id, **post):
        """
        Visitor-facing endpoint for the "ask a question" icon on the
        property detail page. Accepts a 'question' form field, returns
        JSON: {'success': True, 'answer': '...'} or {'success': False,
        'error': '...'} — never raises, so the frontend can always show
        something sensible to the visitor.
        """
        prop = request.env['property.property'].sudo().browse(property_id)

        if not prop.exists() or not prop.is_published:
            result = {'success': False, 'error': 'Property not found.'}
        else:
            question = post.get('question', '')
            try:
                result = prop.answer_property_question(question)
            except Exception as e:
                _logger.error(f"Q&A endpoint error for property {property_id}: {e}")
                result = {'success': False, 'error': 'Something went wrong. Please try again.'}

        return request.make_response(
            json.dumps(result),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-cache, no-store'),
            ]
        )

    # ─────────────────────────────────────────────────────────────
    # MAIN MAP PAGE
    # ─────────────────────────────────────────────────────────────
    @http.route('/', type='http', auth='public', website=True)
    def property_map(self, **kwargs):

        Property = request.env['property.property'].sudo()
        selected_city = kwargs.get('city', '')
        # ⭐ NEW - hero search bar filters (Property Type / Price Range)
        selected_category = kwargs.get('property_type', '')
        selected_price_band = kwargs.get('price_range', '')
        # ⭐ Minimum star rating filter for the hero search bar, e.g.
        # rating=4 means "4 stars & up". Same convention as /properties.
        selected_rating = kwargs.get('rating', '')

        all_properties = Property.search([('is_published', '=', True), ('status', '=', 'available')])
        city_list = sorted(list(set([p.city for p in all_properties if p.city])))
        # ⭐ NEW - categories for the hero "Property Type" dropdown
        categories = request.env['property.category'].sudo().search([])

        # ⭐ NEW - predefined price bands for the hero "Price Range" dropdown
        price_bands = {
            'under_50l': [('price', '<', 5000000)],
            '50l_1cr': [('price', '>=', 5000000), ('price', '<', 10000000)],
            '1cr_2cr': [('price', '>=', 10000000), ('price', '<', 20000000)],
            'above_2cr': [('price', '>=', 20000000)],
        }

        # ⭐ FIX: only show properties that are actually available - sold,
        # rented, or otherwise unavailable properties should never appear
        # on this page (grid, map, or featured section).
        search_domain = [
            ('is_published', '=', True),
            ('status', '=', 'available'),
        ]
        featured_domain = [('is_published', '=', True), ('status', '=', 'available'), ('is_featured', '=', True)]

        if selected_city:
            search_domain.append(('city', '=', selected_city))
            featured_domain.append(('city', '=', selected_city))
        if selected_category:
            try:
                search_domain.append(('category_id', '=', int(selected_category)))
                featured_domain.append(('category_id', '=', int(selected_category)))
            except ValueError:
                selected_category = ''
        if selected_price_band and selected_price_band in price_bands:
            search_domain += price_bands[selected_price_band]
            featured_domain += price_bands[selected_price_band]
        if selected_rating:
            try:
                min_rating_int = max(0, min(5, int(selected_rating)))
                rating_domain = ('rating', 'in', [str(v) for v in range(min_rating_int, 6)])
                search_domain.append(rating_domain)
                featured_domain.append(rating_domain)
            except ValueError:
                selected_rating = ''

        # ⭐ FIX: the "Explore Our Iconic Properties" grid below has no map,
        # so it must NOT require latitude/longitude - that was silently
        # hiding every property without GPS coordinates from search results.
        properties = Property.search(search_domain)
        featured_properties = Property.search(featured_domain)

        # ⭐ FIX: the sidebar card list should show every property matching
        # the search filters (same "26 properties found" count as the
        # header badge) - NOT only the ones that happen to have GPS
        # coordinates saved. The map itself still only plots a pin for
        # properties that do have coordinates (handled below / in JS);
        # everything else still gets a card in the list, just no marker.
        map_properties = properties

        # ⭐ UPDATED - hero stat badges now reflect the active search filters
        # (city / property type / price range) instead of always showing the
        # overall site totals. With no filters selected, they naturally fall
        # back to the full totals, since the domains below have no extra
        # conditions in that case.
        is_searching = bool(selected_city or selected_category or selected_price_band or selected_rating)

        # Properties: total across the whole Properties menu when nothing is
        # searched, otherwise the count of properties matching the search
        # (same domain used for the "Explore Our Iconic Properties" grid).
        total_properties_count = Property.search_count([])
        filtered_properties_count = len(properties) if is_searching else total_properties_count

        # Cities: only "city" narrows this one (property type/price don't
        # change how many cities are covered).
        filtered_cities_count = 1 if selected_city else len(city_list)

        # ⭐ CHANGED - Agents/Customers now reflect who actually OWNS the
        # properties matching the search (matched via each property's
        # contact_email), instead of who separately registered with a
        # matching city. This is what makes "3 properties in Hyderabad ->
        # from N distinct agents/customers" add up correctly.
        if is_searching:
            distinct_emails = list({
                (p.contact_email or '').strip().lower()
                for p in properties if p.contact_email
            })
            if distinct_emails:
                customers_in_city = request.env['customer.registration'].sudo().search([
                    ('status', '=', 'approved'),
                    ('email', 'in', distinct_emails),
                ])
                try:
                    agents_in_city = request.env['real.estate.agent'].sudo().search([
                        ('is_active', '=', True),
                        ('email', 'in', distinct_emails),
                    ])
                except Exception:
                    _logger.warning("real.estate.agent has no 'email' field to match against - showing empty agent list")
                    agents_in_city = request.env['real.estate.agent']
            else:
                customers_in_city = request.env['customer.registration']
                agents_in_city = request.env['real.estate.agent']
        else:
            # No search active - show the overall totals, same as before.
            customers_in_city = request.env['customer.registration'].sudo().search([('status', '=', 'approved')])
            try:
                agents_in_city = request.env['real.estate.agent'].sudo().search([('is_active', '=', True)])
            except Exception:
                agents_in_city = request.env['real.estate.agent']

        filtered_agents_count = len(agents_in_city)
        filtered_customers_count = len(customers_in_city)

        # ⭐ NEW - actual agent/customer details for the "People in <city>"
        # section (only meaningful once a city is searched). getattr(...)
        # is used throughout since the exact field names on real.estate.agent
        # weren't confirmed - this degrades gracefully instead of erroring
        # if a field is named differently on your model.
        agent_data = []
        for a in agents_in_city:
            agent_data.append({
                'name': getattr(a, 'agent_name', '') or getattr(a, 'name', '') or 'Agent',
                'phone': getattr(a, 'phone', '') or getattr(a, 'whatsapp', ''),
                'email': getattr(a, 'email', ''),
                'designation': getattr(a, 'designation', ''),
                'city': getattr(a, 'city', ''),
            })

        customer_data = []
        for c in customers_in_city:
            customer_data.append({
                'name': getattr(c, 'customer_name', '') or 'Customer',
                'phone': getattr(c, 'phone', ''),
                'email': getattr(c, 'email', ''),
                'interested_in': getattr(c, 'interested_in', ''),
                'city': getattr(c, 'city', ''),
            })

        # ⭐ NEW - "unclaimed" properties: matched neither an agent nor an
        # approved customer by contact_email. This is what accounts for the
        # gap between the Properties count and (Agents + Customers) - e.g.
        # 3 properties but only 2 agents + 0 customers means 1 property's
        # contact_email doesn't match anyone in either table.
        unclaimed_properties = []
        if is_searching:
            agent_emails = {(getattr(a, 'email', '') or '').strip().lower() for a in agents_in_city}
            customer_emails = {(getattr(c, 'email', '') or '').strip().lower() for c in customers_in_city}
            known_emails = agent_emails | customer_emails
            for p in properties:
                p_email = (p.contact_email or '').strip().lower()
                if not p_email or p_email not in known_emails:
                    unclaimed_properties.append({
                        'name': p.name or '',
                        'contact_name': p.contact_name or '(not provided)',
                        'contact_email': p.contact_email or '(not provided)',
                        'contact_phone': p.contact_phone or '(not provided)',
                    })

        city_investment_info = None
        if selected_city:
            city_investment_info = Property.get_city_investment_info(selected_city)

        palette = ["#059669", "#dc2626", "#7c3aed", "#ea580c", "#2563eb", "#d97706", "#0891b2", "#9333ea"]
        category_colors = {}
        idx = 0

        property_data = []
        for prop in map_properties:
            cat = prop.category_id.name if prop.category_id else 'Property'
            if cat not in category_colors:
                category_colors[cat] = palette[idx % len(palette)]
                idx += 1

            image_url = None
            if prop.image:
                image_url = f"data:image/png;base64,{prop.image.decode('utf-8')}"
            elif prop.gallery_image_ids:
                first_image = prop.gallery_image_ids[0]
                if first_image.datas:
                    image_url = f"data:image/png;base64,{first_image.datas.decode('utf-8')}"

            full_address = ", ".join(filter(None, [prop.street, prop.city, prop.zip_code]))

            # ⭐ FIX: every property gets a card in the sidebar list now,
            # even if it has no GPS coordinates yet - only the map marker
            # is conditional on latitude/longitude being set (below and
            # in property_map.js), so a missing pin no longer means a
            # missing card.
            property_data.append({
                'id': prop.id,
                'name': prop.name or '',
                'latitude': float(prop.latitude) if prop.latitude else None,
                'longitude': float(prop.longitude) if prop.longitude else None,
                'street': prop.street or '',
                'city': prop.city or '',
                'zip_code': prop.zip_code or '',
                'price': float(prop.price) if prop.price else 0,
                'contact_phone': prop.contact_phone or '',
                'contact_email': prop.contact_email or '',
                'contact_name': prop.contact_name or '',
                'short_description': prop.short_description or '',
                'image_url': image_url,
                'property_type': cat,
                'nearby_landmarks': prop.nearby_landmarks or '',
                'views': prop.views or 0,
                'seo_title': prop.seo_title or '',
                'marker_color': category_colors[cat],
                'full_address': full_address,
                # ⭐ NEW - lets the homepage showcase list mark featured
                # listings with a "+ PREMIUM" tag, same as the old grid.
                'is_featured': bool(prop.is_featured),
                # ⭐ Star rating, plus ready-to-inject HTML for the card list.
                'rating': prop.rating or '0',
                'rating_html': prop.rating_stars_html,
            })

        _logger.info(f"🎯 RENDER - City: '{selected_city}', Properties: {len(property_data)}")

        return request.render('real_estate_management.property_map_template', {
            'property_count': filtered_properties_count,
            'properties_json': json_scriptsafe.dumps(property_data) if property_data else '[]',
            'category_colors': json_scriptsafe.dumps(category_colors),
            'city_list': city_list,
            'filtered_cities_count': filtered_cities_count,
            'selected_city': selected_city,
            'featured_properties': featured_properties,
            'city_investment_info': city_investment_info,
            # ⭐ NEW: full recordset (not just JSON) so the homepage can render
            # a plain property grid ("Explore Our Iconic Properties") without
            # needing the map at all.
            'all_properties': properties,
            # ⭐ NEW - for the hero search card + stat badges
            'categories': categories,
            'selected_category': selected_category,
            'selected_price_band': selected_price_band,
            'selected_rating': selected_rating,
            'total_agents_count': filtered_agents_count,
            'total_customers_count': filtered_customers_count,
            'agent_data': agent_data,
            'customer_data': customer_data,
            'unclaimed_properties': unclaimed_properties,
        })

    # ─────────────────────────────────────────────────────────────
    # PROPERTY DETAIL
    # ─────────────────────────────────────────────────────────────
    @http.route('/property/<int:property_id>', type='http', auth='public', website=True)
    def property_detail(self, property_id, **kwargs):
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            return request.not_found()
        # NOTE: AI content generation used to happen right here, blocking
        # this page load on a live Gemini API call (up to ~30s per retry,
        # up to 3 retries) whenever a property hadn't been AI-processed
        # yet — and it would keep re-blocking on every future visit too,
        # since a failed call never set ai_content_generated=True. That
        # was the reason property detail pages were slow to load.
        # Generation now runs out-of-band via a cron
        # (property.property.cron_generate_pending_ai_content, see
        # data/ir_cron_ai_content.xml). The template already renders fine
        # without AI content (each AI section is wrapped in t-if), so the
        # page just shows those sections once the cron catches up.
        try:
            prop.write({'views': prop.views + 1})
        except Exception as e:
            _logger.error(f"Failed to update views for property {prop.id}: {e}")
        return request.render('real_estate_management.property_detail_page', {
            'property': prop,
        })

    # ─────────────────────────────────────────────────────────────
    # PROPERTY LISTING
    # ─────────────────────────────────────────────────────────────
    @http.route('/properties', type='http', auth='public', website=True)
    def property_listing(self, **kwargs):
        search = kwargs.get('search', '')
        city = kwargs.get('city', '')
        zip_code = kwargs.get('zip_code', '')
        # ⭐ Minimum star rating filter, e.g. rating=4 means "4 stars & up".
        min_rating = kwargs.get('rating', '')

        # ⭐ "Interested In" context coming from the Customer Dashboard's
        #    "Add New Property" flow. When a customer chooses Buying /
        #    Renting / Investment (anything other than Selling), they land
        #    here to browse existing properties instead of registering a
        #    new one - and their own properties should not show up in
        #    that browsing list.
        interested_in = kwargs.get('interested_in', '')
        exclude_own = kwargs.get('exclude_own', '')

        domain = [('is_published', '=', True), ('status', '!=', 'sold')]
        if search:
            domain += ['|', '|',
                       ('name', 'ilike', search),
                       ('city', 'ilike', search),
                       ('zip_code', 'ilike', search)]
        if city:
            domain.append(('city', 'ilike', city))
        if zip_code:
            domain.append(('zip_code', 'ilike', zip_code))
        if min_rating:
            try:
                min_rating_int = max(0, min(5, int(min_rating)))
                domain.append(('rating', 'in', [str(v) for v in range(min_rating_int, 6)]))
            except ValueError:
                min_rating = ''

        # ⭐ Exclude the logged-in customer's own properties (matched the
        #    same way the customer dashboard identifies "my properties":
        #    by contact_email, since that's the reliable link back to the
        #    customer regardless of who technically created the record).
        user = request.env.user
        if exclude_own and not user._is_public():
            customer_email = (user.partner_id.email or user.login or '').strip()
            if customer_email:
                domain.append(('contact_email', 'not ilike', customer_email))

        properties = request.env['property.property'].sudo().search(domain)

        property_card_data = []
        for prop in properties:
            property_card_data.append({
                'id': prop.id,
                'name': prop.name,
                'image_url': f"data:image/png;base64,{prop.image.decode('utf-8')}" if prop.image else '',
                'category': prop.category_id.name or '',
                'price': prop.price,
                'plot_area': prop.plot_area,
                'price_per_sqft': prop.price_per_sqft,
                'city': prop.city,
                'zip_code': prop.zip_code,
                'status': prop.status,
                'status_ribbon_html': prop.status_ribbon_html,
                'rating': prop.rating or '0',
                'rating_html': prop.rating_stars_html,
            })

        return request.render('real_estate_management.property_listing_template', {
            'properties': property_card_data,
            'search': search,
            'city': city,
            'zip_code': zip_code,
            'rating': min_rating,
            'interested_in': interested_in,
            'exclude_own': exclude_own,
        })

    # ─────────────────────────────────────────────────────────────
    # EXISTING: PROPERTY REGISTRATION (Kept intact with auto-fill)
    # ─────────────────────────────────────────────────────────────
    @http.route('/property/register', type='http', auth='public', website=True)
    def show_registration_form(self, **kwargs):
        return request.render('real_estate_management.property_registration_form')

    @http.route('/property/submit', type='http', auth='public', website=True, csrf=False)
    def submit_registration(self, **post):
        try:
            upload_files = request.httprequest.files.getlist('images')
            aadhar_file = request.httprequest.files.get('aadhar_document')
            agreement_file = request.httprequest.files.get('agreement_document')

            user = request.env.user

            # ⭐ If user is logged in, pull details from their account. Otherwise, use submitted form inputs.
            if not user._is_public():
                customer_name = user.partner_id.name
                phone_number = user.partner_id.phone or 'N/A'
                email = user.partner_id.email or user.login
            else:
                customer_name = post.get('customer_name')
                phone_number = post.get('phone_number')
                email = post.get('email')

            property_vals = {
                'customer_name': customer_name,
                'property_name': post.get('property_name'),
                'phone_number': phone_number,
                'email': email,
                'facing_direction': post.get('facing_direction'),
                'place': post.get('place'),
                'category': post.get('category'),
                'sq_yards': post.get('sq_yards'),
                'price': post.get('price'),
                'location': post.get('location'),
                'city': post.get('city'),
                'state': post.get('state'),
                'status': 'submitted',
            }

            property_rec = request.env['property.registration'].sudo().create(property_vals)
            property_rec._send_admin_notification()

            for idx, file in enumerate(upload_files):
                content = base64.b64encode(file.read())
                if idx == 0:
                    property_rec.image = content
                else:
                    request.env['ir.attachment'].sudo().create({
                        'name': file.filename,
                        'res_model': 'property.registration',
                        'res_id': property_rec.id,
                        'type': 'binary',
                        'datas': content,
                        'mimetype': file.content_type,
                    })

            if aadhar_file:
                property_rec.aadhar_document = base64.b64encode(aadhar_file.read())
                property_rec.aadhar_filename = aadhar_file.filename

            if agreement_file:
                property_rec.agreement_document = base64.b64encode(agreement_file.read())
                property_rec.agreement_filename = agreement_file.filename

            return request.render('real_estate_management.property_submission_success')

        except Exception as e:
            _logger.exception("Error in property registration")
            return request.render('real_estate_management.property_submission_error', {'error': str(e)})

    # ─────────────────────────────────────────────────────────────
    # NEW: CUSTOMER REGISTRATION
    # ─────────────────────────────────────────────────────────────
    @http.route('/customer/register', type='http', auth='public', website=True)
    def show_customer_registration_form(self, **kwargs):
        states = request.env['res.country.state'].sudo().search([
            ('country_id', '=', request.env.company.country_id.id)
        ], order='name') if request.env.company.country_id else request.env['res.country.state'].sudo().search([], order='name')
        return request.render('real_estate_management.customer_registration_form', {'states': states})

    @http.route('/customer/register/submit', type='http', auth='public', website=True, csrf=False)
    def submit_customer_registration(self, **post):
        try:
            customer_vals = {
                'customer_name': post.get('customer_name'),
                'email': post.get('email'),
                'phone': post.get('phone'),
                'address': post.get('address'),
                'city': post.get('city'),
                'state_id': int(post.get('state_id')) if post.get('state_id') else False,
                'zip_code': post.get('zip_code'),
                'interested_in': post.get('interested_in') or 'buy',
                'notes': post.get('notes'),
                'status': 'submitted',
            }

            # ⭐ CHANGED: the "Property Details (For Sale)" fields are now
            # only stashed on the customer registration itself as
            # pending_* values - they are deliberately NOT turned into a
            # property.registration record here. That only happens once
            # an admin approves THIS customer registration (see
            # action_approve / _create_property_submission in
            # models/customer_registration.py), which is what keeps an
            # unapproved customer's property out of "Property Submissions".
            if post.get('interested_in') == 'sell':
                property_state_name = False
                if post.get('property_state_id'):
                    state_rec = request.env['res.country.state'].sudo().browse(
                        int(post.get('property_state_id'))
                    )
                    property_state_name = state_rec.name if state_rec.exists() else False

                customer_vals.update({
                    'pending_property_name': post.get('property_title') or 'Property for Sale',
                    'pending_property_category': post.get('property_category') or 'residential',
                    'pending_property_price': post.get('property_price') or 0.0,
                    'pending_property_area': post.get('plot_area') or 0.0,
                    'pending_property_description': post.get('property_description'),
                    'pending_property_address': post.get('property_address') or 'N/A',
                    'pending_property_city': post.get('property_city') or 'Unknown',
                    'pending_property_state': property_state_name or 'Unknown',
                })

            customer_rec = request.env['customer.registration'].sudo().create(customer_vals)

            # First uploaded image is stored as the pending main image;
            # any extras are attached to the customer registration for
            # now and get moved over to the real Property Submission
            # automatically once it's approved (see
            # _create_property_submission).
            if post.get('interested_in') == 'sell':
                upload_files = request.httprequest.files.getlist('property_images')
                for idx, file in enumerate(upload_files):
                    if not file or not file.filename:
                        continue
                    content = base64.b64encode(file.read())
                    if idx == 0:
                        customer_rec.pending_property_image = content
                    else:
                        request.env['ir.attachment'].sudo().create({
                            'name': file.filename,
                            'res_model': 'customer.registration',
                            'res_id': customer_rec.id,
                            'type': 'binary',
                            'datas': content,
                            'mimetype': file.content_type,
                        })

            return request.render('real_estate_management.customer_submission_success')

        except Exception as e:
            _logger.exception("Error in customer registration")
            return request.render('real_estate_management.customer_submission_error', {'error': str(e)})

    # ─────────────────────────────────────────────────────────────
    # AGENT REGISTRATION
    # ─────────────────────────────────────────────────────────────
    @http.route('/agent/register', type='http', auth='public', website=True)
    def agent_registration_form(self, **kwargs):
        categories = request.env['property.category'].sudo().search([])
        states = request.env['res.country.state'].sudo().search([
            ('country_id', '=', request.env.company.country_id.id)
        ], order='name')
        return request.render('real_estate_management.agent_registration_form_template', {
            'categories': categories,
            'states': states,
        })

    @http.route('/agent/register/submit', type='http', auth='public', website=True, csrf=False, methods=['POST'])
    def submit_agent_registration(self, **post):
        try:
            profile_image = request.httprequest.files.get('profile_image')
            id_proof = request.httprequest.files.get('id_proof')
            license_doc = request.httprequest.files.get('license_document')
            resume = request.httprequest.files.get('resume')
            portfolio_images = request.httprequest.files.getlist('portfolio_images')

            registration_vals = {
                'agent_name': post.get('agent_name'),
                'email': post.get('email'),
                'phone': post.get('phone'),
                'whatsapp': post.get('whatsapp'),
                'designation': post.get('designation'),
                'expertise_level': post.get('expertise_level'),
                'license_number': post.get('license_number'),
                'experience_years': int(post.get('experience_years', 0)),
                'city': post.get('city'),
                'state_id': int(post.get('state_id')),
                'zip_code': post.get('zip_code'),
                'short_bio': post.get('short_bio'),
                'detailed_bio': post.get('detailed_bio'),
                'qualifications': post.get('qualifications'),
                'languages_spoken': post.get('languages_spoken', 'English, Hindi'),
                'linkedin_url': post.get('linkedin_url'),
                'facebook_url': post.get('facebook_url'),
                'status': 'submitted',
            }

            if profile_image:
                registration_vals['profile_image'] = base64.b64encode(profile_image.read())
            if id_proof:
                registration_vals['id_proof'] = base64.b64encode(id_proof.read())
                registration_vals['id_proof_filename'] = id_proof.filename
            if license_doc:
                registration_vals['license_document'] = base64.b64encode(license_doc.read())
                registration_vals['license_filename'] = license_doc.filename
            if resume:
                registration_vals['resume'] = base64.b64encode(resume.read())
                registration_vals['resume_filename'] = resume.filename

            specialization_ids = request.httprequest.form.getlist('specialization_ids')
            if specialization_ids:
                registration_vals['specialization_ids'] = [(6, 0, [int(sid) for sid in specialization_ids])]

            registration = request.env['agent.registration'].sudo().create(registration_vals)
            registration._send_admin_notification()

            for idx, img_file in enumerate(portfolio_images):
                if img_file:
                    attachment = request.env['ir.attachment'].sudo().create({
                        'name': f'Portfolio_{idx + 1}_{img_file.filename}',
                        'res_model': 'agent.registration',
                        'res_id': registration.id,
                        'type': 'binary',
                        'datas': base64.b64encode(img_file.read()),
                        'mimetype': img_file.content_type,
                    })
                    registration.attachment_ids = [(4, attachment.id)]

            _logger.info(f"Agent registration submitted: {registration.agent_name}")
            return request.render('real_estate_management.agent_registration_success_template', {
                'registration': registration,
            })

        except Exception as e:
            _logger.exception("Error in agent registration submission")
            return request.render('real_estate_management.agent_registration_error_template', {
                'error': str(e)
            })