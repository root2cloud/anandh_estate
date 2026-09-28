# ========================================
# UPDATED CONTROLLER CODE
# Add this to your property_controller.py
# ========================================

from odoo import http, fields
from odoo.http import request
import json
from odoo.tools.json import scriptsafe as json_scriptsafe
import base64
import logging

_logger = logging.getLogger(__name__)


class RealEstateController(http.Controller):

    @http.route('/', type='http', auth='public', website=True)
    def property_map(self, **kwargs):

        Property = request.env['property.property'].sudo()

        # Get the selected city from URL parameters
        selected_city = kwargs.get('city', '')

        all_properties = Property.search([('is_published', '=', True)])
        city_list = sorted(list(set([p.city for p in all_properties if p.city])))

        # Build the search domain with city filter if selected
        search_domain = [
            ('is_published', '=', True),
            ('latitude', '!=', False),
            ('longitude', '!=', False)
        ]

        if selected_city:
            search_domain.append(('city', '=', selected_city))

        properties = Property.search(search_domain)

        # Fetch featured properties
        featured_domain = [('is_published', '=', True), ('is_featured', '=', True)]
        if selected_city:
            featured_domain.append(('city', '=', selected_city))
        featured_properties = Property.search(featured_domain)

        # Get city investment info
        city_investment_info = None
        if selected_city:
            city_investment_info = Property.get_city_investment_info(selected_city)

        # ============================================
        # 🆕 FETCH AI NEWS - BOTH TYPES
        # ============================================

        ai_daily_news = ""
        ai_trending_news = ""

        if selected_city:
            # City-specific news
            try:
                ai_daily_news = Property.get_daily_investment_news(selected_city)
                _logger.info(f"✅ City-specific news for {selected_city}: {len(ai_daily_news)} chars")
            except Exception as e:
                _logger.error(f"❌ Failed to fetch city news: {e}")
                ai_daily_news = ""
        else:
            # General trending news (when no city selected)
            try:
                ai_trending_news = Property.get_trending_investment_news()
                _logger.info(f"✅ Trending news fetched: {len(ai_trending_news)} chars")
            except Exception as e:
                _logger.error(f"❌ Failed to fetch trending news: {e}")
                ai_trending_news = ""

        # Build property data
        palette = ["#059669", "#dc2626", "#7c3aed", "#ea580c", "#2563eb", "#d97706", "#0891b2", "#9333ea"]
        category_colors = {}
        idx = 0

        property_data = []
        for prop in properties:
            if prop.latitude and prop.longitude:
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

                property_data.append({
                    'id': prop.id,
                    'name': prop.name or '',
                    'latitude': float(prop.latitude),
                    'longitude': float(prop.longitude),
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
                })

        # Final debug
        _logger.info(
            f"🎯 RENDER - City: '{selected_city}', Daily news: {len(ai_daily_news)}, Trending: {len(ai_trending_news)}")

        return request.render('real_estate_management.property_map_template', {
            'property_count': len(property_data),
            'properties_json': json_scriptsafe.dumps(property_data) if property_data else '[]',
            'category_colors': json_scriptsafe.dumps(category_colors),
            'city_list': city_list,
            'selected_city': selected_city,
            'featured_properties': featured_properties,
            'city_investment_info': city_investment_info,
            'ai_daily_news': ai_daily_news,  # City-specific news
            'ai_trending_news': ai_trending_news,  # General trending news
        })

    # ... rest of your controller methods remain unchanged ...