# -*- coding: utf-8 -*-
"""
Flier feature ("Create a Flier" button on the property detail page).

Routes
------
GET /property/<id>/flier            -> printable flier page
POST /property/<id>/flier/register  -> saves the "Registration" card of the flier as a
                                       customer.registration (JSON reply)
GET /api/property/<id>/flier-data   -> JSON with the flier data of a property
                                       (lets another copy of this site, e.g. the
                                       Hostinger one, be used as a data source)

Reference link
--------------
The flier page has a "Reference link" box. What happens with it:
  * link contains /property/<id>  -> that property's info is loaded
        - same host as this site      -> read from this database
        - a host in the allowed list  -> fetched server-side from that site
  * any other link (e.g. only the site home page) -> the current property's
        info is used and the link is printed on the flier as the QR/visit link.

Allowed remote hosts (SSRF protection) are read from the system parameter
`real_estate.flier_allowed_hosts` (comma separated). Default:
darksalmon-lark-825368.hostingersite.com
"""
import base64
import json
import logging
import re
import socket
import ipaddress
from urllib.parse import urlparse, urlencode

import requests
from lxml import html as lxml_html  # bundled with Odoo

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

DEFAULT_REFERENCE_LINK = 'https://darksalmon-lark-825368.hostingersite.com/'
DEFAULT_ALLOWED_HOSTS = 'darksalmon-lark-825368.hostingersite.com'
PROPERTY_PATH_RE = re.compile(r'/property/(\d+)')


class PropertyFlierController(http.Controller):

    # ─────────────────────────────────────────────────────────────
    # helpers
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _money(value):
        try:
            return '₹{:,.2f}'.format(float(value or 0))
        except (TypeError, ValueError):
            return '₹0.00'

    @staticmethod
    def _clean_landmarks(text):
        """Hide placeholder values such as 'To be updated' on the flier."""
        text = (text or '').strip()
        if text.lower().strip('. ') in ('to be updated', 'tbd', 'n/a', 'na', 'none', '-'):
            return ''
        return text

    @staticmethod
    def _qr_data_uri(value):
        """QR code embedded as a data URI (no extra request, works when printing/PNG)."""
        try:
            png = request.env['ir.actions.report'].sudo().barcode('QR', value, width=200, height=200)
            return 'data:image/png;base64,' + base64.b64encode(png).decode()
        except Exception as e:
            _logger.warning('Flier: QR generation failed (%s)', e)
            return '/report/barcode/?' + urlencode({
                'barcode_type': 'QR', 'value': value, 'width': 200, 'height': 200})

    def _selection_label(self, prop, field_name):
        value = prop[field_name]
        if not value:
            return ''
        return dict(prop._fields[field_name]._description_selection(prop.env)).get(value, value)

    def _flier_data_from_record(self, prop, base_url):
        """Build the plain dict the flier template renders, from a DB record."""
        address = ', '.join(filter(None, [
            prop.street, prop.city, prop.state_id.name if prop.state_id else '',
        ]))
        amenities = []
        if prop.water_connection:
            amenities.append('Water Connection')
        if prop.electricity_connection:
            amenities.append('Electricity')
        if prop.drainage_facility:
            amenities.append('Drainage Facility')
        if prop.gated_community:
            amenities.append('Gated Community')
        if prop.emi_available:
            amenities.append('EMI Available')

        gallery = []
        for att in prop.gallery_image_ids[:3]:
            gallery.append('%s/web/image/ir.attachment/%s/datas' % (base_url, att.id))

        return {
            'id': prop.id,
            'name': prop.name or '',
            'price': self._money(prop.price),
            'price_per_sqft': '₹{:,.0f}/sq ft'.format(prop.price_per_sqft or 0),
            'category': prop.category_id.name if prop.category_id else '',
            'address': address,
            'zip_code': prop.zip_code or '',
            'plot_area': '{:g}'.format(prop.plot_area or 0),
            'facing': self._selection_label(prop, 'facing_direction'),
            'title_status': self._selection_label(prop, 'title_status'),
            'road_width': '{:g}'.format(prop.road_width or 0),
            'status': self._selection_label(prop, 'status'),
            'rating': int(prop.rating or 0),
            'description': prop.short_description or '',
            'landmarks': self._clean_landmarks(prop.nearby_landmarks),
            # rich sections shown on the detail page (Html fields -> Markup)
            'overview_html': prop.ai_key_highlights or '',
            'about_html': prop.detailed_description or '',
            'nearby_html': prop.ai_nearby_places or '',
            'amenities': amenities,
            'contact_name': prop.contact_name or '',
            'contact_phone': prop.contact_phone or '',
            'contact_email': prop.contact_email or '',
            'image_url': '%s/web/image/property.property/%s/image' % (base_url, prop.id),
            'gallery': gallery,
            'property_url': '%s/property/%s' % (base_url, prop.id),
            'source': 'local',
        }

    # -- remote fetching ------------------------------------------------
    def _allowed_hosts(self):
        raw = request.env['ir.config_parameter'].sudo().get_param(
            'real_estate.flier_allowed_hosts', DEFAULT_ALLOWED_HOSTS)
        return {h.strip().lower() for h in (raw or '').split(',') if h.strip()}

    @staticmethod
    def _host_is_public(host):
        """Refuse hosts that resolve to private / loopback / link-local IPs."""
        try:
            for info in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def _abs(origin, src):
        if not src:
            return ''
        if src.startswith(('http://', 'https://', 'data:')):
            return src
        return origin + (src if src.startswith('/') else '/' + src)

    def _fetch_remote(self, origin, prop_id):
        """Try the JSON endpoint first, then scrape the public detail page."""
        headers = {'User-Agent': 'Mozilla/5.0 (FlierBot)'}

        # 1) JSON endpoint (works when the remote site runs this same module)
        try:
            r = requests.get('%s/api/property/%s/flier-data' % (origin, prop_id),
                             headers=headers, timeout=10)
            if r.ok and 'json' in r.headers.get('Content-Type', ''):
                data = r.json()
                if data.get('success') and data.get('property'):
                    d = data['property']
                    d['source'] = 'remote-api'
                    return d
        except Exception as e:
            _logger.info('Flier: remote JSON endpoint not available (%s)', e)

        # 2) scrape the public property page using this module's own markup
        try:
            r = requests.get('%s/property/%s' % (origin, prop_id), headers=headers, timeout=15)
            if not r.ok:
                return None
            doc = lxml_html.fromstring(r.content)

            def xp(cls, sub=''):
                return doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]%s" % (cls, sub))

            def clean(el):
                return ' '.join(el.text_content().split())

            def txt(cls):
                els = xp(cls)
                return clean(els[0]) if els else ''

            name = txt('property-title-main')
            if not name:
                return None
            highlights = [clean(e) for e in xp('highlight-item')]
            amenities = [clean(e) for e in xp('amenity-card')]
            imgs = [self._abs(origin, i.get('src')) for i in xp('gallery-main', '//img')]
            info_rows = [clean(e) for e in xp('info-row')]
            return {
                'id': int(prop_id),
                'name': name,
                'price': txt('property-price'),
                'price_per_sqft': txt('price-per-sqft'),
                'category': '',
                'address': txt('property-address'),
                'zip_code': '',
                'plot_area': '', 'facing': '', 'title_status': '', 'road_width': '',
                'status': '',
                'rating': len(xp('property-detail-rating', "//*[contains(@class,'fa-star')]")),
                'description': txt('description-text') or txt('rich-content'),
                'landmarks': '',
                'overview_html': '', 'about_html': '', 'nearby_html': '',
                'amenities': amenities,
                'highlights': highlights,
                'contact_name': txt('agent-name'),
                'contact_phone': info_rows[0] if info_rows else '',
                'contact_email': info_rows[1] if len(info_rows) > 1 else '',
                'image_url': imgs[0] if imgs else '',
                'gallery': imgs[1:4],
                'property_url': '%s/property/%s' % (origin, prop_id),
                'source': 'remote-scrape',
            }
        except Exception as e:
            _logger.warning('Flier: could not scrape %s/property/%s: %s', origin, prop_id, e)
            return None

    def _resolve_reference(self, ref, base_url):
        """
        Returns (data_or_None, message, qr_link)
        data is None => use the current property.
        """
        ref = (ref or '').strip()
        if not ref:
            return None, '', ''
        if not re.match(r'^https?://', ref, re.I):
            ref = 'https://' + ref
        parsed = urlparse(ref)
        if not parsed.netloc:
            return None, 'That does not look like a valid link.', ''

        qr_link = ref
        m = PROPERTY_PATH_RE.search(parsed.path)
        if not m:
            return None, 'Link saved on the flier. Add /property/<id> to it to load another property.', qr_link

        prop_id = int(m.group(1))
        host = parsed.netloc.lower()
        current_host = urlparse(base_url).netloc.lower()

        # same site -> DB
        if host == current_host:
            rec = request.env['property.property'].sudo().browse(prop_id)
            if rec.exists() and rec.is_published:
                return self._flier_data_from_record(rec, base_url), '', qr_link
            return None, 'Property %s was not found on this site.' % prop_id, qr_link

        # other site -> only if allow-listed and public
        if host not in self._allowed_hosts():
            return None, ('%s is not in the allowed hosts list '
                          '(system parameter real_estate.flier_allowed_hosts).' % host), qr_link
        if not self._host_is_public(parsed.hostname):
            return None, 'That host is not allowed.', qr_link

        origin = '%s://%s' % (parsed.scheme, parsed.netloc)
        data = self._fetch_remote(origin, prop_id)
        if not data:
            return None, 'Could not read property %s from %s.' % (prop_id, host), qr_link
        return data, '', qr_link

    # ─────────────────────────────────────────────────────────────
    # routes
    # ─────────────────────────────────────────────────────────────
    @http.route('/property/<int:property_id>/flier', type='http', auth='public', website=True)
    def property_flier(self, property_id, **kwargs):
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            return request.not_found()

        base_url = request.httprequest.host_url.rstrip('/')
        ref = kwargs.get('ref', '') or ''

        data, message, qr_link = self._resolve_reference(ref, base_url)
        if data is None:
            data = self._flier_data_from_record(prop, base_url)
        if not qr_link:
            qr_link = data['property_url']

        qr_src = self._qr_data_uri(qr_link)

        # the AI chat card asks about the property shown on the flier; when the
        # flier was loaded from another site, fall back to the current property
        chat_property_id = data['id'] if data.get('source') == 'local' else prop.id

        return request.render('real_estate_management.property_flier_page', {
            'property': prop,
            'flier': data,
            'ref': ref,
            'ref_message': message,
            'qr_link': qr_link,
            'qr_src': qr_src,
            'default_reference': DEFAULT_REFERENCE_LINK,
            # ---- registration + chat cards (below the flier) ----
            'states': self._get_states(),
            'chat_property_id': chat_property_id,
        })

    # ─────────────────────────────────────────────────────────────
    # Registration card (below the flier)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _get_states():
        State = request.env['res.country.state'].sudo()
        company_country = request.env.company.country_id
        if company_country:
            return State.search([('country_id', '=', company_country.id)], order='name')
        return State.search([], order='name')

    @staticmethod
    def _json(payload, status=200):
        return request.make_response(
            json.dumps(payload),
            headers=[('Content-Type', 'application/json'),
                     ('Cache-Control', 'no-cache, no-store')],
            status=status)

    @http.route('/property/<int:property_id>/flier/register', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def property_flier_register(self, property_id, **post):
        """Registration card on the flier page -> customer.registration (status: submitted)."""
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            return self._json({'success': False, 'error': 'Property not found.'})

        def val(key):
            return (post.get(key) or '').strip()

        name, phone, email = val('full_name'), val('phone'), val('email')
        address, city, pincode = val('address'), val('city'), val('pincode')
        state_raw = val('state_id')

        errors = {}
        if not name:
            errors['full_name'] = 'Full name is required.'
        if not re.match(r'^\+?[0-9][0-9\s\-]{6,14}$', phone):
            errors['phone'] = 'Enter a valid phone number.'
        # customer.registration.email is a required field on the model
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            errors['email'] = 'Enter a valid email address.'
        if not address:
            errors['address'] = 'Address is required.'
        if not state_raw.isdigit():
            errors['state_id'] = 'Please select a state.'
        if not city:
            errors['city'] = 'City is required.'
        if not re.match(r'^[0-9]{6}$', pincode):
            errors['pincode'] = 'Enter a 6-digit pincode.'
        if errors:
            return self._json({'success': False, 'errors': errors,
                               'error': 'Please correct the highlighted fields.'})

        try:
            reg = request.env['customer.registration'].sudo().create({
                'customer_name': name,
                'email': email,
                'phone': phone,
                'address': address,
                'city': city,
                'state_id': int(state_raw),
                'zip_code': pincode,
                'interested_in': 'buy',
                'notes': 'Registered from the flier of "%s" (property ID %s).' % (prop.name, prop.id),
                'status': 'submitted',
            })
            return self._json({'success': True, 'reference': reg.name})
        except Exception:
            _logger.exception('Flier: registration failed')
            return self._json({'success': False,
                               'error': 'Something went wrong. Please try again.'})

    @http.route('/api/property/<int:property_id>/flier-data', type='http', auth='public',
                website=True, methods=['GET'], csrf=False)
    def property_flier_data(self, property_id, **kwargs):
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            result = {'success': False, 'error': 'Property not found.'}
        else:
            base_url = request.httprequest.host_url.rstrip('/')
            result = {'success': True, 'property': self._flier_data_from_record(prop, base_url)}
        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json'),
                     ('Cache-Control', 'no-cache, no-store')])