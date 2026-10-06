from odoo import models, fields, api, _
import logging
import requests
import json
import time

_logger = logging.getLogger(__name__)


class Property(models.Model):
    _name = 'property.property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Real Estate Property'

    # Core details
    name = fields.Char(string='Property Name*', required=True, tracking=True)
    short_description = fields.Char(string='Short Description')
    detailed_description = fields.Html(string='Detailed Description')
    category_id = fields.Many2one('property.category', string='Category*')
    is_featured = fields.Boolean(string='Featured Property', default=False)

    price = fields.Monetary(string='Total Price*', currency_field='currency_id', required=True)
    plot_area = fields.Float(string='Plot Area (Sq.Ft)*',required=True)
    price_per_sqft = fields.Float(string='Price per Sq.Ft (₹)', compute='_compute_price_per_sqft', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id.id)

    facing_direction = fields.Selection([
        ('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West'),
        ('northeast', 'North-East'), ('northwest', 'North-West'),
        ('southeast', 'South-East'), ('southwest', 'South-West')
    ], string='Facing Direction*',required=True)
    road_width = fields.Float(string='Road Width (Feet)*',required=True)
    title_status = fields.Selection([
        ('clear', 'Clear Title'), ('registered', 'Registered'),
        ('rera', 'RERA Approved'), ('dtcp', 'DTCP Approved'),
        ('hmda', 'HMDA Approved'), ('patta', 'Patta Available'),
        ('pending', 'Pending Approval')
    ], string='Title Status*',required=True)

    status = fields.Selection([
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('rented', 'Rented'),
    ], string='Property Status', default='available', tracking=True)

    # ⭐ Star rating (1-5). '0' means not rated yet. Selection is used
    # (instead of Integer) so it plugs straight into Odoo's built-in
    # widget="priority" star-picker in list/form views. Properties can be
    # filtered by this everywhere it's exposed - backend search filters,
    # the website "/properties" listing, and the homepage hero search.
    rating = fields.Selection([
        ('0', 'Not Rated'),
        ('1', '1 Star'),
        ('2', '2 Stars'),
        ('3', '3 Stars'),
        ('4', '4 Stars'),
        ('5', '5 Stars'),
    ], string='Rating', default='0', tracking=True)

    rating_stars_html = fields.Html(
        string='Rating Stars HTML',
        compute='_compute_rating_stars_html',
        sanitize=False
    )

    # ⭐ ADD THIS NEW COMPUTED FIELD
    status_ribbon_html = fields.Html(
        string='Status Ribbon HTML',
        compute='_compute_status_ribbon_html',
        sanitize=False
    )

    adhar_image = fields.Binary(
        string="Aadhaar Card*",
        attachment=True,
        store=True,
        required=True
    )
    adhar_filename = fields.Char()

    agreement_document = fields.Binary(
        string="Agreement Document*",
        attachment=True,
        store=True,
        required=True
    )
    agreement_filename = fields.Char()

    property_website_url = fields.Char(string='Property Website*')
    image = fields.Image(string='Cover Image')

    # Address
    street = fields.Char(string='Street*')
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City*', required=True)
    zip_code = fields.Char(string='ZIP*',required=True)
    state_id = fields.Many2one(
        'res.country.state', string='State*',
        domain="[('country_id','=', country_id)]", required=True
    )
    country_id = fields.Many2one('res.country', string='Country', readonly=True,
                                 default=lambda self: self.env.company.country_id.id, store=True)

    # Financials
    emi_available = fields.Boolean(string='EMI Available*', default=True,required=True)
    registration_charges = fields.Float(string='Registration Charges (%)*', default=7.0,required=True)
    registration_amount = fields.Monetary(string='Approx. Registration Amount',
                                          currency_field='currency_id',
                                          compute='_compute_registration_amount', store=True)

    # Infrastructure
    water_connection = fields.Boolean(string='Water Connection', default=True)
    electricity_connection = fields.Boolean(string='Electricity Connection', default=True)
    drainage_facility = fields.Boolean(string='Drainage Facility', default=True)
    gated_community = fields.Boolean(string='Gated Community')

    # Geolocation
    latitude = fields.Float(string='Latitude', digits=(16, 5),
                            compute='_compute_geolocation', store=True)
    longitude = fields.Float(string='Longitude', digits=(16, 5),
                             compute='_compute_geolocation', store=True)
    date_localization = fields.Date(string='Geolocation Date',
                                    compute='_compute_geolocation', store=True)

    # Contact Info
    contact_name = fields.Char(string='Contact Person*',required=True)
    contact_phone = fields.Char(string='Phone*',required=True)
    contact_email = fields.Char(string='Email*',required=True)

    # Media & SEO
    gallery_image_ids = fields.Many2many(
        'ir.attachment',
        'property_gallery_rel',
        'property_id',
        'attachment_id',
        string="Gallery Images"
    )
    image_count = fields.Integer(string='Number of Images', compute='_compute_image_count')
    seo_title = fields.Char(string='SEO Title*',required=True)
    seo_description = fields.Text(string='SEO Description')
    # Add this field to your Property model
    agent_id = fields.Many2one(
        'real.estate.agent',
        string='Assigned Agent',
        tracking=True,
        help='Real estate agent responsible for this property'
    )

    # ⭐ NEW: Gates visibility in the backend "Property Listings" view for
    # properties submitted by Agents through the Agent Portal. Defaults to
    # True so every other property (created directly in the backend, or
    # created via a Customer's "Sell your Property" registration - which
    # only ever creates the property.property record AFTER admin approval
    # anyway) is completely unaffected and stays visible exactly as before.
    # Only the Agent Portal "Add Property" flow sets this to False when it
    # creates the live property record immediately (so the agent can see
    # it right away in their own portal, before admin approval). It is
    # flipped back to True by property.registration.action_approve() once
    # admin approves the linked "Property Submissions" entry.
    is_agent_submission_approved = fields.Boolean(
        string='Agent Submission Approved',
        default=True,
        copy=False,
        help="Internal flag: False only for properties submitted by an "
             "Agent through the Agent Portal that are still pending admin "
             "approval in Property Submissions. Hides them from the "
             "backend Property Listings until approved."
    )

    # Metadata
    is_published = fields.Boolean(string='Published', default=False)
    views = fields.Integer(string='Views', default=0)
    last_viewed = fields.Datetime(string='Last Viewed')
    nearby_landmarks = fields.Text(string='Nearby Landmarks*',required=True)

    # AI Content Fields
    ai_key_highlights = fields.Html(readonly=True)
    ai_investment_data = fields.Html(readonly=True)
    ai_nearby_places = fields.Html(readonly=True)
    ai_unique_features = fields.Html(readonly=True)
    ai_lifestyle_benefits = fields.Html(readonly=True)
    ai_content_generated = fields.Boolean(default=False)
    ai_generation_date = fields.Datetime()
    # Tracks retry state so a failing/slow Gemini call is never repeated
    # synchronously inside a website page load (see property_controller.py).
    # A background cron picks up pending properties instead.
    ai_generation_attempts = fields.Integer(default=0)
    ai_last_attempt_date = fields.Datetime()

    # Kept as one shared constant so the cron's give-up threshold and the
    # status badge below always agree on what counts as "failed".
    AI_MAX_ATTEMPTS = 5

    ai_content_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('pending', 'Pending (Retrying)'),
        ('generated', 'Generated'),
        ('failed', 'Failed - Max Attempts Reached'),
    ], string='AI Content Status', compute='_compute_ai_content_status', store=True)

    # Set on every failed generate_ai_content() call, cleared on success.
    # Lets you see exactly why a property's AI content failed directly in
    # the backend, without needing access to the Odoo server logs.
    ai_last_error = fields.Text(string='Last AI Generation Error', readonly=True)

    @api.depends('ai_content_generated', 'ai_generation_attempts')
    def _compute_ai_content_status(self):
        for rec in self:
            if rec.ai_content_generated:
                rec.ai_content_status = 'generated'
            elif rec.ai_generation_attempts >= rec.AI_MAX_ATTEMPTS:
                rec.ai_content_status = 'failed'
            elif rec.ai_generation_attempts > 0:
                rec.ai_content_status = 'pending'
            else:
                rec.ai_content_status = 'not_started'

    # ==================== CITY INVESTMENT FIELDS ====================
    city_investment_reasons = fields.Html(string='City Investment Reasons', readonly=True)
    city_growth_potential = fields.Html(string='City Growth Potential', readonly=True)
    city_infrastructure = fields.Html(string='City Infrastructure', readonly=True)
    city_market_trends = fields.Html(string='City Market Trends', readonly=True)
    city_investment_generated = fields.Boolean(default=False)
    city_investment_date = fields.Datetime()
    last_city_processed = fields.Char(string='Last City Processed')

    # -------------------- COMPUTE METHODS --------------------
    @api.depends('price', 'plot_area')
    def _compute_price_per_sqft(self):
        for rec in self:
            rec.price_per_sqft = round(rec.price / rec.plot_area, 2) if rec.plot_area else 0

    @api.depends('price', 'registration_charges')
    def _compute_registration_amount(self):
        for rec in self:
            rec.registration_amount = (rec.price * rec.registration_charges / 100) if rec.price else 0

    @api.depends('gallery_image_ids')
    def _compute_image_count(self):
        for rec in self:
            rec.image_count = len(rec.gallery_image_ids)

    @api.depends('street', 'street2', 'city', 'zip_code', 'state_id', 'country_id')
    def _compute_geolocation(self):
        geo = self.env['base.geocoder']
        for rec in self:
            # Construct full address
            street = ' '.join(filter(None, [rec.street, rec.street2]))
            address_components = {
                'street': street,
                'zip': rec.zip_code or '',
                'city': rec.city or '',
                'state': rec.state_id.name or '',
                'country': rec.country_id.name or '',
            }
            if not (address_components['street'] or address_components['zip'] or address_components['city']):
                rec.latitude = rec.longitude = False
                rec.date_localization = False
                _logger.info(f"Skipping geocode for {rec.name}: insufficient address info {address_components}")
                continue

            try:
                # Log the query
                _logger.info(f"Geocoding property {rec.name} with params: {address_components}")

                # Query geocoder with structured parameters
                query = geo.geo_query_address(**address_components)
                coords = geo.geo_find(query, force_country=address_components['country'])

                # Fallback: try single string query if structured fails
                if not coords or len(coords) != 2:
                    address_str = ', '.join(
                        filter(None, [rec.street, rec.street2, rec.city, rec.state_id.name, rec.country_id.name]))
                    _logger.info(
                        f"Structured geocode failed for {rec.name}, trying fallback with address string: {address_str}")
                    coords = geo.geo_find(address_str)

                if coords and len(coords) == 2:
                    rec.latitude, rec.longitude = coords
                    rec.date_localization = fields.Date.context_today(rec)
                    _logger.info(f"Geocoded {rec.name}: latitude={rec.latitude}, longitude={rec.longitude}")
                else:
                    rec.latitude = rec.longitude = False
                    rec.date_localization = False
                    _logger.error(f"Geocode failed for {rec.name}: {address_components}")

            except Exception as e:
                rec.latitude = rec.longitude = False
                rec.date_localization = False
                _logger.error(f"Geocode error for {rec.name}: {e}")

    # REPLACE your generate_ai_content and get_city_investment_info methods with these:

    def _post_gemini_with_retry(self, url, headers, payload, timeout=30, max_retries=3, base_delay=2):
        """
        POST to the Gemini API.

        * 503 (overloaded) / short 429 (per-minute limit): retried with a short backoff.
        * Daily quota exhausted (429 "retry in ...h"), model not found (404) or still
          failing after the retries: the SAME request is automatically sent to the fallback
          models (system parameters `gemini.fallback_model` and `gemini.fallback_model_2`,
          defaults gemini-3.5-flash and gemini-3.5-flash-lite), so AI content keeps working
          when the main model has no quota left.
        Returns the final requests.Response object (callers still check status_code).
        """
        import re as _re

        def _quota_exhausted(resp):
            text = (resp.text or '').lower()
            return resp.status_code == 429 and (
                _re.search(r'retry in \d+h', text) or 'perday' in text or 'per day' in text)

        def _post_one(target_url):
            response = None
            for attempt in range(1, max_retries + 1):
                response = requests.post(target_url, headers=headers, json=payload, timeout=timeout)
                if response.status_code not in (503, 429):
                    return response
                if _quota_exhausted(response):
                    return response  # waiting will not help - try another model instead
                if attempt < max_retries:
                    delay = base_delay * attempt  # 2s, 4s, 6s...
                    _logger.warning(
                        f"⏳ Gemini API busy (status {response.status_code}), "
                        f"retrying in {delay}s (attempt {attempt}/{max_retries})...")
                    time.sleep(delay)
            return response

        response = _post_one(url)
        if response.status_code in (429, 503, 404):
            match = _re.search(r'models/([^:/?]+):generateContent', url)
            if match:
                params = self.env['ir.config_parameter'].sudo()
                fallbacks = [
                    params.get_param('gemini.fallback_model', 'gemini-3.5-flash'),
                    params.get_param('gemini.fallback_model_2', 'gemini-3.5-flash-lite'),
                ]
                for fb in fallbacks:
                    if not fb or fb == match.group(1):
                        continue
                    _logger.warning(
                        f"⚠️ Gemini model {match.group(1)} failed (status {response.status_code}); "
                        f"trying fallback model {fb}")
                    fb_response = _post_one(url.replace(f"models/{match.group(1)}:", f"models/{fb}:"))
                    if fb_response.status_code == 200:
                        return fb_response
                    response = fb_response
        return response

    def _build_property_facts_block(self):
        """
        Builds a plain-text block of this property's own real, stored
        details (only the fields actually set, so no empty/false noise).
        Shared by generate_ai_content() and answer_property_question() so
        both are grounded in the exact same source of truth about the
        property, instead of duplicating this logic in two places.
        """
        self.ensure_one()
        facts = [
            f"Property name: {self.name}",
            f"City: {self.city}",
            f"Price: ₹{self.price:,.0f}",
            f"Plot area: {self.plot_area} sqft",
        ]
        if self.price_per_sqft:
            facts.append(f"Price per sq.ft: ₹{self.price_per_sqft:,.0f}")
        if self.registration_amount:
            facts.append(f"Approx. registration amount: ₹{self.registration_amount:,.0f}")
        if self.category_id:
            facts.append(f"Category: {self.category_id.name}")
        if self.facing_direction:
            facts.append(f"Facing direction: {dict(self._fields['facing_direction'].selection).get(self.facing_direction)}")
        if self.road_width:
            facts.append(f"Road width: {self.road_width} feet")
        if self.title_status:
            facts.append(f"Title status: {dict(self._fields['title_status'].selection).get(self.title_status)}")
        if self.gated_community:
            facts.append("Located in a gated community")
        utilities = []
        if self.water_connection:
            utilities.append("water connection")
        if self.electricity_connection:
            utilities.append("electricity connection")
        if self.drainage_facility:
            utilities.append("drainage facility")
        if utilities:
            facts.append(f"Utilities already in place: {', '.join(utilities)}")
        if self.emi_available:
            facts.append(f"EMI available, registration charges approx. {self.registration_charges}%")
        if self.nearby_landmarks:
            facts.append(f"Nearby landmarks (as provided by the lister): {self.nearby_landmarks}")
        if self.short_description:
            facts.append(f"Short description: {self.short_description}")
        if self.street or self.zip_code:
            facts.append(f"Address: {self.street or ''} {self.city or ''} {self.zip_code or ''}".strip())
        if self.status:
            facts.append(f"Status: {dict(self._fields['status'].selection).get(self.status)}")

        return '\n'.join(f"- {f}" for f in facts)

    # ==================== AUTOMATIC AI CONTENT ====================
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._schedule_ai_content_generation()
        return records

    def write(self, vals):
        result = super().write(vals)
        # a property that was just published should get its content too
        if vals.get('is_published'):
            self._schedule_ai_content_generation()
        return result

    def _schedule_ai_content_generation(self):
        """Ask the scheduled action to generate AI content right now.

        This does not slow down saving: the Gemini calls run in the background
        cron job, a few seconds after the property is saved. If it fails, the
        status shows it and the "Regenerate AI Content" button can be clicked."""
        pending = self.filtered(
            lambda r: not r.ai_content_generated and r.ai_generation_attempts < r.AI_MAX_ATTEMPTS)
        if not pending:
            return
        try:
            cron = self.env.ref(
                'real_estate_management.ir_cron_generate_missing_ai_content',
                raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        except Exception as e:
            _logger.warning("Could not schedule automatic AI content generation: %s", e)

    def generate_ai_content(self):
        """Generate AI content using FREE Google Gemini API"""
        self.ensure_one()

        # Record that we attempted this, and when — regardless of outcome.
        # This is what lets the cron (see cron_generate_pending_ai_content)
        # back off from properties that keep failing instead of retrying
        # them forever, and stops any caller from re-running the same slow
        # request over and over.
        self.write({
            'ai_generation_attempts': self.ai_generation_attempts + 1,
            'ai_last_attempt_date': fields.Datetime.now(),
        })

        # Get Gemini API key (FREE from https://aistudio.google.com/app/apikey)
        api_key = self.env['ir.config_parameter'].sudo().get_param('gemini.api_key')

        if not api_key:
            _logger.error("❌ Gemini API key not configured. Get free key from https://aistudio.google.com/app/apikey")
            self.write({'ai_last_error': 'Gemini API key not configured in System Parameters (gemini.api_key).'})
            return False

        _logger.info(f"🔄 Generating AI content for property: {self.name}")

        facts_block = self._build_property_facts_block()

        prompt = (
            f"Generate detailed real estate marketing content for this SPECIFIC property. "
            f"Base every point strictly on the facts below — do not invent details that "
            f"contradict them, and do not fabricate precise statistics (like exact ROI % "
            f"or appreciation %) that weren't given; describe potential in general, "
            f"honest terms instead.\n\n"
            f"PROPERTY FACTS:\n{facts_block}\n\n"
            f"Return a JSON object with exactly these keys:\n\n"
            f"- key_highlights: array of 3-4 detailed points (1-2 full sentences each) that reference "
            f"this property's actual facts above (e.g. its facing direction, title status, category, road width)\n"
            f"- investment_data: array of 3-4 detailed points on why this specific property is a sound "
            f"investment, grounded in its title status, documentation, and location — not invented numbers\n"
            f"- nearby_places: array of 3-4 detailed points built from the nearby landmarks provided above "
            f"(if none were provided, give general locality-appropriate points for {self.city} instead)\n"
            f"- lifestyle_benefits: array of 3-4 detailed points about lifestyle benefits that follow from "
            f"this property's actual amenities/utilities/community facts above\n"
            f"- unique_features: an OBJECT (not an array) with 4 category keys, where each value is an array "
            f"of 2-3 detailed points (1-2 full sentences each) specific to that category, using the facts above:\n"
            f"    \"Design & Architecture\": points about layout, plot size, facing direction, road width\n"
            f"    \"Sustainability & Eco-Features\": points about the utilities/connections actually listed above\n"
            f"    \"Security & Amenities\": points about gated community status and common facilities, if applicable\n"
            f"    \"Investment Value\": points about this property's actual title status, EMI availability, and registration details\n\n"
            f"Every point must be specific to THIS property's facts, not generic filler like 'great location'. "
            f"Return ONLY valid JSON, no markdown, no extra text."
        )

        headers = {
            'Content-Type': 'application/json'
        }

        payload = {
            'contents': [
                {'parts': [{'text': prompt}]}
            ],
            'systemInstruction': {
                'parts': [{'text': 'You are a real estate analyst. Return only JSON.'}]
            },
            'generationConfig': {
                'temperature': 0.3,
                'maxOutputTokens': 2500,
                'responseMimeType': 'application/json'
            }
        }

        gemini_model = self.env['ir.config_parameter'].sudo().get_param('gemini.model', 'gemini-3.6-flash')
        gemini_url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{gemini_model}:generateContent?key={api_key}'
        )

        try:
            _logger.info("📤 Calling FREE Gemini API...")

            response = self._post_gemini_with_retry(
                gemini_url,
                headers=headers,
                payload=payload,
                timeout=30
            )

            _logger.info(f"📥 Response status: {response.status_code}")

            if response.status_code != 200:
                _logger.error(f"API Error: {response.text}")
                self.write({'ai_last_error': f"Gemini API returned status {response.status_code}: {response.text[:500]}"})
                return False

            response_data = response.json()
            response_text = response_data['candidates'][0]['content']['parts'][0]['text'].strip()

            # Clean JSON
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            try:
                ai_data = json.loads(response_text)
                _logger.info(f"✅ Parsed AI data with keys: {list(ai_data.keys())}")
            except json.JSONDecodeError as e:
                _logger.error(f"JSON parse error: {e}\nResponse: {response_text}")
                snippet = response_text[:300] if response_text else '(empty response)'
                self.write({'ai_last_error': f"Could not parse AI response as JSON: {e}. Raw output: {snippet}"})
                return False

            # Convert to HTML — handles both flat lists (simple sections) and
            # dicts (category -> list of points), which render as sub-headings.
            def to_html(data):
                if not data:
                    return '<ul><li>Information not available</li></ul>'
                if isinstance(data, dict):
                    groups = ''
                    for category, points in data.items():
                        if isinstance(points, list):
                            items = ''.join([f'<li>{point}</li>' for point in points])
                        else:
                            items = f'<li>{points}</li>'
                        groups += (
                            f'<div class="feature-group">'
                            f'<h4 class="feature-subheading">{category}</h4>'
                            f'<ul>{items}</ul>'
                            f'</div>'
                        )
                    return groups
                if isinstance(data, list):
                    items = ''.join([f'<li>{item}</li>' for item in data])
                    return f'<ul>{items}</ul>'
                return f'<ul><li>{data}</li></ul>'

            self.write({
                'ai_key_highlights': to_html(ai_data.get('key_highlights', [])),
                'ai_investment_data': to_html(ai_data.get('investment_data', [])),
                'ai_nearby_places': to_html(ai_data.get('nearby_places', [])),
                'ai_unique_features': to_html(ai_data.get('unique_features', [])),
                'ai_lifestyle_benefits': to_html(ai_data.get('lifestyle_benefits', [])),
                'ai_content_generated': True,
                'ai_generation_date': fields.Datetime.now(),
                'ai_last_error': False,
            })

            _logger.info(f"✅ AI content saved for property: {self.name}")
            return True

        except Exception as e:
            _logger.error(f"❌ Error: {e}")
            self.write({'ai_last_error': f"{type(e).__name__}: {e}"})
            return False

    def _build_property_qa_context(self):
        """
        Facts + the already-generated listing highlights (stripped to plain
        text) so the assistant can answer 'advantages', 'is it a good
        investment', 'what is nearby' etc. with real content instead of
        only the raw field values.
        """
        self.ensure_one()
        from odoo.tools import html2plaintext

        block = self._build_property_facts_block()
        extras = []
        for label, value in (
            ('Key highlights', self.ai_key_highlights),
            ('Investment notes', self.ai_investment_data),
            ('Unique features', self.ai_unique_features),
            ('Lifestyle benefits', self.ai_lifestyle_benefits),
            ('Nearby places', self.ai_nearby_places),
        ):
            if value:
                text = html2plaintext(value).strip()
                text = ' '.join(text.split())
                if text and 'Information not available' not in text:
                    extras.append(f"{label}: {text[:600]}")
        if extras:
            block += "\n\nADDITIONAL LISTING NOTES:\n" + "\n".join(f"- {e}" for e in extras)
        return block

    @staticmethod
    def _qa_generation_config(model_name):
        """
        Generation settings per model family. Thinking tokens count against
        maxOutputTokens, so a small limit makes answers stop mid-word.
        We keep thinking minimal and give plenty of headroom.
        """
        config = {
            'temperature': 0.4,
            'maxOutputTokens': 1024,
        }
        name = (model_name or '').lower()
        if 'gemini-2.5' in name and 'pro' not in name:
            config['thinkingConfig'] = {'thinkingBudget': 0}
        elif name.startswith('gemini-3'):
            config['thinkingConfig'] = {'thinkingLevel': 'low'}
        return config

    @staticmethod
    def _trim_to_last_sentence(text):
        """If a reply was cut off, drop the dangling fragment."""
        text = (text or '').strip()
        if not text or text[-1] in '.!?':
            return text
        cut = max(text.rfind('. '), text.rfind('! '), text.rfind('? '))
        if cut > 40:
            return text[:cut + 1].strip()
        return text

    # Small per-worker cache so repeated questions don't burn Gemini quota.
    _QA_CACHE = {}
    _QA_CACHE_TTL = 600  # seconds

    def _local_qa_answer(self, question):
        """
        Rule-based answer built ONLY from this property's stored fields.
        Used when Gemini is rate-limited / overloaded / returns nothing, so
        the visitor always gets a useful reply instead of an error.
        """
        self.ensure_one()
        q = (question or '').lower()

        import re

        def has(*words):
            # short words (emi, road, rate...) must match as whole words
            return any(
                (re.search(r'\b' + re.escape(w) + r'\b', q) if len(w) <= 4 else w in q)
                for w in words
            )

        def sel(field, value):
            return dict(self._fields[field].selection).get(value) if value else None

        city = self.city or 'this area'
        price = f"₹{self.price:,.0f}" if self.price else None
        pps = f"₹{self.price_per_sqft:,.0f}" if self.price_per_sqft else None
        reg_amt = f"₹{self.registration_amount:,.0f}" if self.registration_amount else None
        title = sel('title_status', self.title_status)
        facing = sel('facing_direction', self.facing_direction)
        utilities = [n for n, on in (
            ('water', self.water_connection),
            ('electricity', self.electricity_connection),
            ('drainage', self.drainage_facility),
        ) if on]

        # Price per sq.ft
        if has('sq ft', 'sqft', 'sq.ft', 'sq feet', 'square', 'per sq', 'rate'):
            if pps:
                return (f"The price is {pps} per sq.ft. For {self.plot_area:g} sq.ft "
                        f"that comes to {price} in total.")
        # Registration
        if has('registration', 'stamp'):
            if reg_amt:
                return (f"Registration charges are about {self.registration_charges:g}% of the price, "
                        f"roughly {reg_amt} on {price}.")
        # EMI / loan
        if has('emi', 'loan', 'finance', 'installment', 'instalment'):
            if self.emi_available:
                return (f"Yes, EMI is available on this property (price {price}). "
                        f"Contact the agent for bank options and rates.")
            return "EMI is not listed for this property. Please contact the agent about financing."
        # Total price
        if has('price', 'cost', 'how much', 'budget', 'amount'):
            if price:
                extra = f" That is {pps} per sq.ft." if pps else ""
                return f"The listed price is {price} for {self.plot_area:g} sq.ft.{extra}"
        # Size
        if has('area', 'size', 'plot', 'big', 'large'):
            return f"The plot area is {self.plot_area:g} sq.ft in {city}."
        # Facing
        if has('facing', 'direction', 'vastu'):
            if facing:
                return f"This property is {facing}-facing."
        # Road
        if has('road'):
            if self.road_width:
                return f"It has a {self.road_width:g}-foot wide road."
        # Legal
        if has('title', 'legal', 'document', 'approval', 'approved', 'rera', 'dtcp', 'clear'):
            if title:
                return (f"Title status is {title}. Please verify the original documents "
                        f"with the agent before booking.")
        # Utilities
        if has('water', 'electric', 'drain', 'utilit', 'facilit', 'amenit'):
            if utilities:
                gated = " It is also in a gated community." if self.gated_community else ""
                return f"Utilities in place: {', '.join(utilities)}.{gated}"
        # Location / nearby
        if has('nearby', 'near', 'landmark', 'location', 'where', 'address', 'located'):
            addr = ' '.join(p for p in (self.street, self.city, self.zip_code) if p)
            lm = ' '.join((self.nearby_landmarks or '').split())[:200]
            out = f"It is located at {addr}." if addr else f"It is located in {city}."
            if lm:
                out += f" Nearby: {lm}"
            return out

        # Advantages / is it good to buy / anything else -> highlights
        points = []
        if title:
            points.append(f"{title} title")
        if self.road_width:
            points.append(f"{self.road_width:g}-foot road")
        if utilities:
            points.append(f"{', '.join(utilities)} available")
        if self.emi_available:
            points.append("EMI available")
        if self.gated_community:
            points.append("gated community")
        if facing:
            points.append(f"{facing}-facing")
        if pps:
            points.append(f"{pps} per sq.ft")
        if points:
            return (f"Key advantages in {city}: {'; '.join(points[:5])}. "
                    f"Visit the site and verify documents before deciding.")
        return f"This is a {self.plot_area:g} sq.ft property in {city} priced at {price}. Contact the agent for more details."

    def answer_property_question(self, question, history=None):
        """
        Answer a visitor's question about THIS property with a short,
        informative reply grounded in the stored listing data.

        Reliability order: cache -> Gemini (primary, fallback, lite model)
        -> rule-based local answer. The visitor should never see an error
        just because Gemini is busy.

        `history` is optional: a list of {'role': 'user'|'bot', 'text': '...'}.
        Returns {'success': True, 'answer': '...'} or {'success': False, 'error': '...'}.
        """
        self.ensure_one()

        question = (question or '').strip()
        if not question:
            return {'success': False, 'error': 'Please enter a question.'}
        question = question[:500]

        # 1) cache (only when there is no chat history influencing the answer)
        cache_key = (self.id, ' '.join(question.lower().split()), str(self.write_date))
        if not history:
            hit = self._QA_CACHE.get(cache_key)
            if hit and time.time() - hit[0] < self._QA_CACHE_TTL:
                return {'success': True, 'answer': hit[1]}

        params = self.env['ir.config_parameter'].sudo()
        api_key = params.get_param('gemini.api_key')
        if not api_key:
            _logger.error("❌ Gemini API key not configured for property Q&A. Using local answer.")
            return {'success': True, 'answer': self._local_qa_answer(question)}

        context_block = self._build_property_qa_context()

        history_text = ''
        if history and isinstance(history, list):
            lines = []
            for turn in history[-4:]:
                if not isinstance(turn, dict):
                    continue
                who = 'Visitor' if turn.get('role') == 'user' else 'Assistant'
                txt = str(turn.get('text', '')).strip()[:300]
                if txt:
                    lines.append(f"{who}: {txt}")
            if lines:
                history_text = "RECENT CHAT:\n" + "\n".join(lines) + "\n\n"

        prompt = (
            f"PROPERTY DATA:\n{context_block}\n\n"
            f"{history_text}"
            f"VISITOR'S QUESTION: {question}\n\n"
            f"HOW TO ANSWER:\n"
            f"1. Answer exactly what was asked. Do not just repeat the location or the "
            f"property name.\n"
            f"2. Use ONLY the property data above. Never invent numbers, approvals, "
            f"distances or amenities. If something asked is not in the data, say so in "
            f"a few words and suggest contacting the agent for it.\n"
            f"3. Question types:\n"
            f"   - 'Is it good to buy / worth it / good investment': give a clear "
            f"verdict (e.g. 'Yes, it looks like a solid option because...') with 2-3 "
            f"concrete reasons from the data (price per sq.ft, title status, road width, "
            f"utilities, EMI, location). Add one short caveat, e.g. verify documents "
            f"and visit the site before deciding.\n"
            f"   - 'Advantages / benefits / features': list the 3-4 strongest real "
            f"points separated by commas or semicolons.\n"
            f"   - 'Price / cost / EMI / registration': give the exact figures.\n"
            f"   - 'Location / nearby': use the address and listed landmarks.\n"
            f"   - Greetings or unrelated questions: reply in one line and steer back "
            f"to the property.\n"
            f"4. Format: plain text, no markdown, no bullets, maximum 3 short sentences "
            f"(about 60 words). Always finish the last sentence. Prices in ₹ with commas."
        )

        headers = {'Content-Type': 'application/json'}
        system_instruction = {
            'parts': [{'text': (
                'You are a concise, honest real estate assistant for a single property '
                'listing. Give direct, specific, helpful answers with real numbers from the '
                'listing. No filler, no marketing fluff, no guarantees of returns.'
            )}]
        }

        # Up to three different models, de-duplicated, in order.
        models_to_try = []
        for m in (
            params.get_param('gemini.model', 'gemini-3.6-flash'),
            params.get_param('gemini.fallback_model', 'gemini-3.5-flash'),
            params.get_param('gemini.fallback_model_2', 'gemini-3.5-flash-lite'),
        ):
            if m and m not in models_to_try:
                models_to_try.append(m)

        last_status, last_text = None, ''

        def call(model_name, with_thinking):
            gen_cfg = self._qa_generation_config(model_name)
            if not with_thinking:
                gen_cfg.pop('thinkingConfig', None)
            payload = {
                'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'systemInstruction': system_instruction,
                'generationConfig': gen_cfg,
            }
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   f'{model_name}:generateContent?key={api_key}')
            # Short retries: keep the visitor's wait low, then move to next model.
            return self._post_gemini_with_retry(
                url, headers=headers, payload=payload, timeout=20, max_retries=2, base_delay=1)

        for model_name in models_to_try:
            try:
                response = call(model_name, with_thinking=True)

                # Some models reject thinkingConfig -> retry the same model without it.
                if response.status_code == 400 and 'think' in response.text.lower():
                    _logger.warning(f"Q&A: '{model_name}' rejected thinkingConfig, retrying without it.")
                    response = call(model_name, with_thinking=False)

                if response.status_code != 200:
                    last_status, last_text = response.status_code, response.text[:300]
                    _logger.warning(
                        f"Q&A Gemini error, property {self.id}, model '{model_name}': "
                        f"{last_status} {last_text}")
                    continue

                data = response.json()
                candidates = data.get('candidates') or []
                candidate = candidates[0] if candidates else {}
                parts = candidate.get('content', {}).get('parts', []) or []
                answer = ' '.join(
                    p.get('text', '').strip()
                    for p in parts
                    if p.get('text') and not p.get('thought')
                ).strip()

                if not answer:
                    last_status = 200
                    last_text = (f"empty answer, finishReason={candidate.get('finishReason')}, "
                                 f"promptFeedback={data.get('promptFeedback')}")
                    _logger.warning(f"Q&A Gemini empty, property {self.id}, model '{model_name}': {last_text}")
                    continue

                if candidate.get('finishReason') == 'MAX_TOKENS':
                    answer = self._trim_to_last_sentence(answer)

                if len(self._QA_CACHE) > 500:
                    self._QA_CACHE.clear()
                if not history:
                    self._QA_CACHE[cache_key] = (time.time(), answer)
                return {'success': True, 'answer': answer}

            except Exception as e:
                last_status, last_text = 'exception', str(e)
                _logger.warning(f"Q&A error, property {self.id}, model '{model_name}': {e}")
                continue

        # Every model failed -> answer from the stored data instead of an error.
        _logger.error(
            f"❌ Q&A: all Gemini models failed for property {self.id} "
            f"({models_to_try}); last: {last_status} {last_text}. Using local answer.")
        try:
            return {'success': True, 'answer': self._local_qa_answer(question)}
        except Exception as e:
            _logger.error(f"❌ Q&A local fallback failed for property {self.id}: {e}")
            return {'success': False, 'error': 'Sorry, something went wrong. Please try again.'}

    @api.model
    def cron_generate_pending_ai_content(self, batch_size=5, max_attempts=None):
        """Background job (see data/ir_cron_ai_content.xml) that generates
        AI content a few properties at a time.

        This used to run inline inside the /property/<id> website
        controller on every page view whose property lacked AI content,
        which meant a visitor's page load blocked on a live Gemini API
        call (up to ~30s per attempt, retried up to 3x) — and would do so
        again on *every subsequent visit* if the call ever failed, since
        the failure path never marked the property as done. That is what
        made "Property Details" feel slow to load.

        Now the controller no longer calls generate_ai_content() at all;
        this cron does it out-of-band instead, a handful of properties at
        a time, and gives up on a property after `max_attempts` failures
        so a broken/rate-limited API key can't cause endless retries.
        """
        if max_attempts is None:
            max_attempts = self.AI_MAX_ATTEMPTS

        # Properties that were never tried come first (so a freshly created
        # property is handled before old ones that keep failing).
        pending = self.search([
            ('ai_content_generated', '=', False),
            ('ai_generation_attempts', '<', max_attempts),
        ], limit=batch_size, order='ai_generation_attempts asc, id desc')

        for prop in pending:
            try:
                prop.generate_ai_content()
            except Exception as e:
                _logger.error(f"❌ Cron AI generation failed for property {prop.id}: {e}")
            # Commit after each property so a slow/failing item doesn't
            # cost the whole batch's progress if the cron is interrupted.
            self.env.cr.commit()

        return True

    @api.model
    def _cron_generate_missing_ai_content(self):
        """Entry point called by the scheduled action in data/ai_content_cron.xml.

        The scheduled action calls model._cron_generate_missing_ai_content(),
        but only cron_generate_pending_ai_content() existed, so the nightly job
        failed every time and properties never got their AI overview / nearby
        places. This wrapper makes the scheduled action work."""
        return self.cron_generate_pending_ai_content(batch_size=10)

    @api.model
    def get_city_investment_info(self, city_name):
        """Generate city investment info using FREE Google Gemini API"""
        if not city_name:
            return None

        # Check cache
        cached = self.search([
            ('last_city_processed', '=', city_name),
            ('city_investment_generated', '=', True)
        ], limit=1)

        if cached:
            _logger.info(f"✅ Found cached city data for {city_name}")
            return {
                'city': city_name,
                'ai_investment_reasons': cached.city_investment_reasons or '',
                'ai_growth_potential': cached.city_growth_potential or '',
                'ai_infrastructure': cached.city_infrastructure or '',
                'ai_market_trends': cached.city_market_trends or '',
                'ai_content_generated': True,
            }

        # Get Gemini API key
        api_key = self.env['ir.config_parameter'].sudo().get_param('gemini.api_key')

        if not api_key:
            _logger.error("❌ Gemini API key not configured")
            return {
                'city': city_name,
                'ai_investment_reasons': '<p>Please configure Gemini API key to see investment data.</p>',
                'ai_growth_potential': '<p>Get a free API key from https://aistudio.google.com/app/apikey</p>',
                'ai_infrastructure': '<p>Configuration needed.</p>',
                'ai_market_trends': '<p>Configuration needed.</p>',
                'ai_content_generated': False,
            }

        _logger.info(f"📝 Generating city investment data for: {city_name}")

        prompt = (
            f"Create real estate investment summary for {city_name}, India.\n\n"
            f"Return JSON with these keys (each as array of 2-3 bullet points):\n"
            f"- investment_reasons: Why invest here\n"
            f"- growth_potential: Future developments\n"
            f"- infrastructure: Transport & amenities\n"
            f"- market_trends: Current property trends\n\n"
            f"Return ONLY valid JSON."
        )

        headers = {
            'Content-Type': 'application/json'
        }

        payload = {
            'contents': [
                {'parts': [{'text': prompt}]}
            ],
            'systemInstruction': {
                'parts': [{'text': 'You are a real estate analyst. Return only JSON.'}]
            },
            'generationConfig': {
                'temperature': 0.3,
                'maxOutputTokens': 1500,
                'responseMimeType': 'application/json'
            }
        }

        gemini_model = self.env['ir.config_parameter'].sudo().get_param('gemini.model', 'gemini-3.6-flash')
        gemini_url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{gemini_model}:generateContent?key={api_key}'
        )

        def error_result(reason):
            """Return a visible error message instead of silently going blank."""
            _logger.error(f"❌ get_city_investment_info failed for {city_name}: {reason}")
            msg = f'<p>AI generation failed: {reason}. Check Odoo server logs for details.</p>'
            return {
                'city': city_name,
                'ai_investment_reasons': msg,
                'ai_growth_potential': '<p>Please retry once the issue above is fixed.</p>',
                'ai_infrastructure': '<p>Configuration needed.</p>',
                'ai_market_trends': '<p>Configuration needed.</p>',
                'ai_content_generated': False,
            }

        try:
            _logger.info("📤 Calling Gemini API for city data...")

            response = self._post_gemini_with_retry(
                gemini_url,
                headers=headers,
                payload=payload,
                timeout=30
            )

            if response.status_code != 200:
                _logger.error(f"API Error ({response.status_code}): {response.text}")
                return error_result(f"Gemini API returned status {response.status_code} — {response.text[:200]}")

            response_data = response.json()

            candidate = response_data.get('candidates', [{}])[0]
            finish_reason = candidate.get('finishReason', '')
            parts = candidate.get('content', {}).get('parts', [])

            if not parts:
                _logger.error(f"Gemini returned no content. Full response: {response_data}")
                return error_result(
                    f"Gemini returned no content (finishReason: {finish_reason or 'unknown'})"
                )

            response_text = parts[0].get('text', '').strip()

            if finish_reason == 'MAX_TOKENS':
                _logger.warning(f"⚠️ Gemini response was cut off (hit max_tokens). Raw text: {response_text}")

            # Clean JSON — strip whitespace first, then strip markdown code fences if present
            response_text = response_text.strip()
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            try:
                city_data = json.loads(response_text)
                _logger.info(f"✅ Parsed city data with keys: {list(city_data.keys())}")
            except json.JSONDecodeError as e:
                # Fallback: try to extract just the { ... } substring in case the
                # model added stray text before/after the JSON object.
                try:
                    start = response_text.index('{')
                    end = response_text.rindex('}') + 1
                    city_data = json.loads(response_text[start:end])
                    _logger.info(f"✅ Parsed city data after extracting JSON substring: {list(city_data.keys())}")
                except (ValueError, json.JSONDecodeError):
                    _logger.error(f"JSON parse error: {e}\nRaw response: {response_text}")
                    snippet = response_text[:250] if response_text else '(empty response)'
                    reason = "Response was cut off (too long)" if finish_reason == 'MAX_TOKENS' else "Could not parse the AI's response as JSON"
                    return error_result(f"{reason}. Raw AI output: {snippet}")

            # Convert to HTML
            def to_html(data):
                if not data:
                    return '<p>Information not available.</p>'
                if isinstance(data, list):
                    items = ''.join([f'<li>{item}</li>' for item in data])
                    return f'<ul>{items}</ul>'
                if isinstance(data, str):
                    return f'<p>{data}</p>'
                return '<p>Information not available.</p>'

            investment_reasons = to_html(city_data.get('investment_reasons', ''))
            growth_potential = to_html(city_data.get('growth_potential', ''))
            infrastructure = to_html(city_data.get('infrastructure', ''))
            market_trends = to_html(city_data.get('market_trends', ''))

            # Cache the data
            city_property = self.search([
                ('city', '=', city_name),
                ('is_published', '=', True)
            ], limit=1)

            if city_property:
                city_property.write({
                    'city_investment_reasons': investment_reasons,
                    'city_growth_potential': growth_potential,
                    'city_infrastructure': infrastructure,
                    'city_market_trends': market_trends,
                    'city_investment_generated': True,
                    'city_investment_date': fields.Datetime.now(),
                    'last_city_processed': city_name,
                })
                _logger.info(f"✅ Cached city data in property ID: {city_property.id}")

            return {
                'city': city_name,
                'ai_investment_reasons': investment_reasons,
                'ai_growth_potential': growth_potential,
                'ai_infrastructure': infrastructure,
                'ai_market_trends': market_trends,
                'ai_content_generated': True,
            }

        except Exception as e:
            return error_result(f"{type(e).__name__}: {e}")

    def action_regenerate_ai_content(self):
        """Button to regenerate AI content.

        Shows a notification and then reloads the form automatically, so the
        status bar (Generated / Pending), the red error box and the AI tabs
        are up to date without pressing F5."""
        self.ensure_one()
        success = self.generate_ai_content()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success' if success else 'Error',
                'message': ('AI content generated successfully!' if success
                            else 'Failed to generate AI content. See the red box on the form for the reason.'),
                'type': 'success' if success else 'danger',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            }
        }

    def action_regenerate_ai_content_bulk(self):
        """
        Bulk button/action for generating AI content on multiple selected
        properties at once (e.g. from the list view: select rows -> Action ->
        Regenerate AI Content). Loops through every record in self, so unlike
        action_regenerate_ai_content it does NOT return early after the first one.
        A short pause between calls is added to stay under free-tier rate limits.
        """
        success_count = 0
        failure_count = 0
        failed_names = []

        for rec in self:
            try:
                if rec.generate_ai_content():
                    success_count += 1
                else:
                    failure_count += 1
                    failed_names.append(rec.name)
            except Exception as e:
                _logger.error(f"❌ Bulk AI generation error for {rec.name}: {e}")
                failure_count += 1
                failed_names.append(rec.name)

            # Small pause between calls so a batch of properties doesn't
            # slam the free-tier Gemini rate limit all at once.
            time.sleep(1.5)

        if failure_count == 0:
            message = f"AI content generated successfully for all {success_count} propert{'y' if success_count == 1 else 'ies'}."
            notif_type = 'success'
        else:
            message = (
                f"Generated for {success_count} propert{'y' if success_count == 1 else 'ies'}, "
                f"failed for {failure_count}: {', '.join(failed_names[:5])}"
                + ('...' if len(failed_names) > 5 else '') + ". Check server logs for details."
            )
            notif_type = 'warning' if success_count else 'danger'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bulk AI Content Generation',
                'message': message,
                'type': notif_type,
                'sticky': failure_count > 0,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            }
        }

        # ⭐ ADD THIS COMPUTE METHOD (add after your other compute methods)

    @api.model
    def build_rating_stars_html(self, rating):
        """Shared star-HTML builder. Used both by the compute field below
        (for real records, e.g. the property detail page) and directly by
        the website controllers for dict-based card lists (the homepage
        sidebar/map cards and the /properties grid), which don't have a
        record to read a computed field from.
        """
        try:
            value = int(rating or 0)
        except (TypeError, ValueError):
            value = 0
        value = max(0, min(5, value))
        stars = ''.join(
            '<i class="fa fa-star"></i>' if i <= value else '<i class="fa fa-star-o"></i>'
            for i in range(1, 6)
        )
        return '<span class="property-star-rating" data-rating="%s">%s</span>' % (value, stars)

    def _compute_rating_stars_html(self):
        for rec in self:
            rec.rating_stars_html = self.build_rating_stars_html(rec.rating)

    def _compute_status_ribbon_html(self):
        """Generate status ribbon HTML for use in templates"""
        for rec in self:
            if rec.status == 'available':
                rec.status_ribbon_html = '''
                       <span class="status-ribbon ribbon-available" 
                             style="position: absolute; top: 0; right: 0; 
                                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                    color: white; padding: 0.5rem 0.9rem; 
                                    font-size: 11px; font-weight: 700; 
                                    letter-spacing: 1px; z-index: 10;
                                    border-radius: 0 0 0 8px;
                                    box-shadow: 0 3px 12px rgba(0,0,0,0.3);">
                           <i class="fa fa-check-circle"></i> AVAILABLE
                       </span>
                   '''
            elif rec.status == 'sold':
                rec.status_ribbon_html = '''
                       <span class="status-ribbon ribbon-sold" 
                             style="position: absolute; top: 0; right: 0; 
                                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                                    color: white; padding: 0.5rem 0.9rem; 
                                    font-size: 11px; font-weight: 700; 
                                    letter-spacing: 1px; z-index: 10;
                                    border-radius: 0 0 0 8px;
                                    box-shadow: 0 3px 12px rgba(0,0,0,0.3);">
                           <i class="fa fa-tag"></i> SOLD
                       </span>
                   '''
            elif rec.status == 'rented':
                rec.status_ribbon_html = '''
                       <span class="status-ribbon ribbon-rented" 
                             style="position: absolute; top: 0; right: 0; 
                                    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                                    color: white; padding: 0.5rem 0.9rem; 
                                    font-size: 11px; font-weight: 700; 
                                    letter-spacing: 1px; z-index: 10;
                                    border-radius: 0 0 0 8px;
                                    box-shadow: 0 3px 12px rgba(0,0,0,0.3);">
                           <i class="fa fa-key"></i> RENTED
                       </span>
                   '''
            else:
                rec.status_ribbon_html = ''

    @api.model
    def get_daily_investment_news(self, city_name):
        """
        Fetch AI-generated daily investment news for a specific city

        Args:
            city_name (str): Name of the city

        Returns:
            str: Investment news text for the ticker
        """
        if not city_name:
            return ""

        try:
            gemini_api_key2 = self.env['ir.config_parameter'].sudo().get_param('gemini_api_key2', '')

            if not gemini_api_key2:
                _logger.warning(f"Gemini API key not configured for city: {city_name}")
                return self._get_fallback_city_news(city_name)

            gemini_model = self.env['ir.config_parameter'].sudo().get_param('gemini.model', 'gemini-3.6-flash')
            url = (
                'https://generativelanguage.googleapis.com/v1beta/models/'
                f'{gemini_model}:generateContent?key={gemini_api_key2}'
            )

            headers = {
                "Content-Type": "application/json"
            }

            prompt = f"""You are a real estate investment expert. Generate a concise, engaging news ticker text (max 200 words) about top investment opportunities in {city_name}, India.

    Format as a flowing news ticker with separators (|) between points. Include:
    - Top 3-4 investment hotspots/areas in {city_name}
    - Key growth factors (infrastructure, IT parks, metro, etc.)
    - Price trends (appreciation rates)
    - Best property types for investment

    Example format: "🏙️ {city_name} Real Estate Update | 📈 Gachibowli Area: 15% Annual Appreciation | 🚇 Metro Expansion Boosts Property Value | 💼 IT Hub Growth in Financial District | 🏘️ Residential Plots High in Demand | ⚡ Book Premium Locations Now"

    Keep it engaging, data-driven, and ticker-friendly with emojis."""

            payload = {
                "contents": [
                    {"parts": [{"text": prompt}]}
                ],
                "systemInstruction": {
                    "parts": [{"text": "You are a real estate market analyst providing investment insights for property investors."}]
                },
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 300,
                    "topP": 1
                }
            }

            response = self._post_gemini_with_retry(url, headers=headers, payload=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                ai_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                _logger.info(f"✅ AI News generated for {city_name}: {ai_text[:100]}...")
                return ai_text
            else:
                _logger.error(f"Gemini API Error for {city_name}: {response.status_code}")
                return self._get_fallback_city_news(city_name)

        except requests.exceptions.Timeout:
            _logger.error(f"Gemini API timeout for {city_name}")
            return self._get_fallback_city_news(city_name)

        except Exception as e:
            _logger.error(f"Error fetching AI news for {city_name}: {e}")
            return self._get_fallback_city_news(city_name)

    def _get_fallback_city_news(self, city_name):
        """Fallback static news if AI fails"""
        return (
            f"🏙️ {city_name} Real Estate Market Update | "
            f"📈 Property Appreciation: 10-15% Annually | "
            f"🚇 Infrastructure Development Underway | "
            f"💼 IT & Commercial Hub Expansion | "
            f"🏘️ Residential & Commercial Plots Available | "
            f"⚡ Premium Locations - Limited Availability | "
            f"📞 Contact Us for Best Deals in {city_name}"
        )

    # ========================================
    # METHOD 2: General Trending News
    # ========================================

    @api.model
    def get_trending_investment_news(self):
        """
        Fetch AI-generated trending investment markets across India
        Called when no city is selected (All Cities view)

        Returns:
            str: Trending investment markets text
        """
        try:
            gemini_api_key2 = self.env['ir.config_parameter'].sudo().get_param('gemini_api_key2', '')

            if not gemini_api_key2:
                _logger.warning("Gemini API key not configured for trending news")
                return self._get_fallback_trending_news()

            gemini_model = self.env['ir.config_parameter'].sudo().get_param('gemini.model', 'gemini-3.6-flash')
            url = (
                'https://generativelanguage.googleapis.com/v1beta/models/'
                f'{gemini_model}:generateContent?key={gemini_api_key2}'
            )

            headers = {
                "Content-Type": "application/json"
            }

            prompt = """You are a real estate investment expert. Generate a concise overview (max 250 words) of the TOP 5 TRENDING real estate investment markets in India right now.

    Format as flowing text highlighting:
    - The 5 hottest cities/regions for real estate investment
    - Why these markets are trending (infrastructure, IT growth, connectivity)
    - Average appreciation rates
    - Key investment types (residential, commercial, plots)

    Make it engaging and data-driven. Use emojis to highlight key points.

    Example format: "🔥 India's Top Investment Markets | 🏙️ Bangalore: IT boom driving 18% appreciation in Whitefield & Electronic City | 🌆 Pune: Metro expansion boosting Hinjewadi & Baner by 15% | 🏖️ Goa: Tourism revival pushing coastal properties 20%+ | 💼 Hyderabad: Pharma & tech hubs in Gachibowli seeing 16% growth | 🌟 Mumbai: Navi Mumbai metro bringing 12% returns"

    Keep it concise, engaging, and ticker-friendly."""

            payload = {
                "contents": [
                    {"parts": [{"text": prompt}]}
                ],
                "systemInstruction": {
                    "parts": [{"text": "You are a real estate market analyst providing trending investment insights across India."}]
                },
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 400,
                    "topP": 1
                }
            }

            response = self._post_gemini_with_retry(url, headers=headers, payload=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                ai_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                _logger.info(f"✅ Trending news generated: {ai_text[:100]}...")
                return ai_text
            else:
                _logger.error(f"Gemini API Error for trending: {response.status_code}")
                return self._get_fallback_trending_news()

        except requests.exceptions.Timeout:
            _logger.error("Gemini API timeout for trending news")
            return self._get_fallback_trending_news()

        except Exception as e:
            _logger.error(f"Error fetching trending news: {e}")
            return self._get_fallback_trending_news()

    def _get_fallback_trending_news(self):
        """Fallback static trending news if AI fails"""
        return (
            "🔥 India's Hottest Real Estate Markets | "
            "🏙️ Bangalore: Tech Hub Driving 18% Annual Growth in Whitefield & Electronic City | "
            "🌆 Hyderabad: Pharma & IT Sectors Boosting Gachibowli, Madhapur by 16% | "
            "💼 Pune: Metro Expansion Pushing Hinjewadi & Baner Properties 15%+ | "
            "🏖️ Goa: Tourism Revival Driving Coastal Real Estate 20% | "
            "🌟 Mumbai: Navi Mumbai Infrastructure Development Bringing Strong Returns | "
            "📊 Best Time to Invest in Tier-1 & Emerging Tier-2 Cities!"
        )

# @api.model
    # def get_city_investment_info(self, city_name):
    #     """
    #     Get or generate AI investment information for a city
    #     """
    #     if not city_name:
    #         return None
    #
    #     # Search if we already have this city's investment data in any property
    #     existing = self.search([
    #         ('last_city_processed', '=', city_name),
    #         ('city_investment_generated', '=', True)
    #     ], limit=1)
    #
    #     if existing:
    #         return {
    #             'city': city_name,
    #             'ai_investment_reasons': existing.city_investment_reasons,
    #             'ai_growth_potential': existing.city_growth_potential,
    #             'ai_infrastructure': existing.city_infrastructure,
    #             'ai_market_trends': existing.city_market_trends,
    #             'ai_content_generated': True,
    #         }
    #
    #     # Get API key
    #     api_key = self.env['ir.config_parameter'].sudo().get_param('openai.api_key')
    #     if not api_key:
    #         _logger.error("OpenAI API key not configured")
    #         return None
    #
    #     print(f"Generating AI investment content for city: {city_name}")
    #
    #     prompt = (
    #         f"Create a concise, premium, and trustworthy real estate investment summary for {city_name}, India. "
    #         "Return a JSON object with exactly four keys, each containing a short paragraph (2–3 sentences max): "
    #         "'investment_reasons' — Explain why this city is a reliable and smart choice for real estate investment. Focus on safety, job growth, lifestyle, and investor confidence. "
    #         "'growth_potential' — Highlight upcoming developments, government initiatives, and economic growth that boost long-term value. "
    #         "'infrastructure' — Summarize key transport links, urban projects, and quality-of-life improvements. "
    #         "'market_trends' — Describe current property and rental trends that indicate steady demand and appreciation. "
    #         "Use warm, confident language that builds trust with first-time investors — make it sound like expert advice backed by real urban and economic growth data. "
    #         "Avoid lists — write naturally in full sentences with a realistic tone suitable for a luxury real estate website."
    #     )
    #
    #
    #
    #     headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    #     payload = {
    #         'model': 'gpt-4o-mini',
    #         'messages': [
    #             {'role': 'system',
    #              'content': 'You are a real estate investment analyst. Provide factual data about cities in India with focus on real estate investment potential.'},
    #             {'role': 'user', 'content': prompt}
    #         ],
    #         'max_tokens': 600,
    #         'temperature': 0.3
    #     }
    #
    #     try:
    #         res = requests.post(
    #             'https://api.openai.com/v1/chat/completions',
    #             headers=headers,
    #             json=payload,
    #             timeout=30
    #         )
    #         res.raise_for_status()
    #         response_data = res.json()
    #         response_text = response_data['choices'][0]['message']['content']
    #
    #         if response_text.startswith:
    #             response_text = response_text.replace("```json", "").replace("```", "")
    #
    #         try:
    #             js = json.loads(response_text)
    #
    #             def list_to_html(lst):
    #                 if not isinstance(lst, list) or not lst:
    #                     return str(lst) if lst else ''
    #                 return '<ul>' + ''.join(f'<li>{item}</li>' for item in lst) + '</ul>'
    #
    #             investment_reasons = list_to_html(js.get('investment_reasons', ''))
    #             growth_potential = list_to_html(js.get('growth_potential', ''))
    #             infrastructure = list_to_html(js.get('infrastructure', ''))
    #             market_trends = list_to_html(js.get('market_trends', ''))
    #
    #             # Store in a dummy property record to cache the data
    #             city_cache = self.search([('last_city_processed', '=', city_name)], limit=1)
    #             if not city_cache:
    #                 # Create a dummy record just to store city data
    #                 city_cache = self.create({
    #                     'name': f'City Data - {city_name}',
    #                     'city': city_name,
    #                     'city_investment_reasons': investment_reasons,
    #                     'city_growth_potential': growth_potential,
    #                     'city_infrastructure': infrastructure,
    #                     'city_market_trends': market_trends,
    #                     'city_investment_generated': True,
    #                     'city_investment_date': fields.Datetime.now(),
    #                     'last_city_processed': city_name,
    #                     'is_published': False,
    #                 })
    #             else:
    #                 city_cache.write({
    #                     'city_investment_reasons': investment_reasons,
    #                     'city_growth_potential': growth_potential,
    #                     'city_infrastructure': infrastructure,
    #                     'city_market_trends': market_trends,
    #                     'city_investment_generated': True,
    #                     'city_investment_date': fields.Datetime.now(),
    #                     'last_city_processed': city_name,
    #                 })
    #
    #             print(f"AI city investment content generated and stored for {city_name}")
    #
    #             return {
    #                 'city': city_name,
    #                 'ai_investment_reasons': investment_reasons,
    #                 'ai_growth_potential': growth_potential,
    #                 'ai_infrastructure': infrastructure,
    #                 'ai_market_trends': market_trends,
    #                 'ai_content_generated': True,
    #             }
    #
    #         except Exception as e:
    #             print(f"JSON parse error for city: {e}")
    #             return None
    #
    #     except Exception as e:
    #         print(f"AI generation failed for city {city_name}: {e}")
    #         return None