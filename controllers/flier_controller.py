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
import uuid
import socket
import ipaddress
from urllib.parse import urlparse, urlencode

import requests
from lxml import html as lxml_html  # bundled with Odoo

from markupsafe import Markup, escape

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
    def _money_short(value):
        """1.25 Cr / 85 Lakh style price used on the flier price badge."""
        try:
            v = float(value or 0)
        except (TypeError, ValueError):
            return '\u20b90'
        if v >= 1e7:
            return '\u20b9%s Cr' % ('{:.2f}'.format(v / 1e7).rstrip('0').rstrip('.'))
        if v >= 1e5:
            return '\u20b9%s Lakh' % ('{:.2f}'.format(v / 1e5).rstrip('0').rstrip('.'))
        return '\u20b9{:,.0f}'.format(v)

    @staticmethod
    def _client_ip():
        """Visitor IP address (also behind nginx / a reverse proxy)."""
        import ipaddress
        req = request.httprequest
        ip = (req.remote_addr or '').strip()

        def _is_internal(value):
            try:
                addr = ipaddress.ip_address(value)
                return addr.is_private or addr.is_loopback
            except ValueError:
                return True

        # behind nginx / docker the direct address is an internal one -> use the forwarded header
        if not ip or _is_internal(ip):
            forwarded = (req.headers.get('X-Forwarded-For') or req.headers.get('X-Real-IP') or '')
            first = forwarded.split(',')[0].strip()
            if first:
                ip = first
        return ip

    @staticmethod
    def _is_bot():
        """True for crawlers / link-preview fetchers, which must not count as views."""
        ua = (request.httprequest.headers.get('User-Agent') or '').lower()
        if not ua:
            return True
        return any(t in ua for t in (
            'bot', 'crawler', 'spider', 'whatsapp', 'telegram', 'facebookexternalhit',
            'slurp', 'preview', 'curl/', 'wget', 'python-requests', 'headless'))

    @staticmethod
    def _highest_bid(prop):
        """Highest bid placed so far for a property (0.0 when there is none)."""
        top = request.env['flier.registration'].sudo().search(
            [('property_id', '=', prop.id), ('bid_amount', '>', 0)],
            order='bid_amount desc, id asc', limit=1)
        return top.bid_amount if top else 0.0

    @staticmethod
    def _bid_count(prop):
        return request.env['flier.registration'].sudo().search_count(
            [('property_id', '=', prop.id), ('bid_amount', '>', 0)])

    @staticmethod
    def _money_plain(prop, amount):
        symbol = (prop.currency_id.symbol if prop.currency_id else '') or ''
        return '%s%s' % (symbol, '{:,.0f}'.format(amount or 0))

    @staticmethod
    def _landmark_list(text, limit=4):
        """Nearby-landmarks text -> short list of lines for the poster."""
        parts = re.split(r'[\n;]+|,\s*(?=[A-Za-z])', text or '')
        out = []
        for part in parts:
            part = re.sub(r'^[\s\-\*\u2022\d\.\)]+', '', part).strip()
            if part and part not in out:
                out.append(part)
        return out[:limit]

    @staticmethod
    def _maps_url(prop, address):
        if prop.latitude and prop.longitude:
            return 'https://www.google.com/maps?q=%s,%s' % (prop.latitude, prop.longitude)
        query = ', '.join(filter(None, [address, prop.zip_code]))
        if query:
            return 'https://www.google.com/maps/search/?api=1&' + urlencode({'query': query})
        return ''

    @staticmethod
    def _clean_landmarks(text):
        """Hide placeholder values such as 'To be updated' on the flier."""
        text = (text or '').strip()
        if text.lower().strip('. ') in ('to be updated', 'tbd', 'n/a', 'na', 'none', '-'):
            return ''
        return text

    @staticmethod
    def _qr_png(value, size=300):
        """PNG bytes of a QR code (Odoo's own barcode renderer) or None."""
        try:
            return request.env['ir.actions.report'].sudo().barcode(
                'QR', value, width=size, height=size)
        except Exception as e:
            _logger.warning('Flier: server-side QR generation failed (%s)', e)
            return None

    @classmethod
    def _qr_data_uri(cls, value):
        """
        QR code embedded as a data URI. Returns '' when the server cannot draw it;
        the flier page then draws the same QR in the browser (data-qr attribute).
        """
        png = cls._qr_png(value, 200)
        return ('data:image/png;base64,' + base64.b64encode(png).decode()) if png else ''

    @staticmethod
    def _public_base(default_base):
        """
        Address printed inside the QR code. Set the system parameter
        `real_estate.flier_public_url` (e.g. http://16.192.24.205:8098 or your domain)
        so the QR opens from any phone; otherwise the address of the current request is used.
        """
        custom = request.env['ir.config_parameter'].sudo().get_param('real_estate.flier_public_url')
        return (custom or default_base or '').strip().rstrip('/')

    def _selection_label(self, prop, field_name):
        value = prop[field_name]
        if not value:
            return ''
        return dict(prop._fields[field_name]._description_selection(prop.env)).get(value, value)

    @staticmethod
    def _usable_html(value):
        """True when an AI Html field holds real content (not empty / placeholder)."""
        text = (value or '').strip() if not hasattr(value, 'striptags') else value.striptags().strip()
        return bool(text) and 'Information not available' not in text

    @staticmethod
    def _bullets(items):
        items = [i for i in items if i]
        if not items:
            return ''
        return Markup('<ul>%s</ul>') % Markup('').join(
            Markup('<li>%s</li>') % escape(i) for i in items)

    def _fallback_overview_html(self, prop):
        """
        Overview built only from the property's own saved fields. Used when
        the AI highlights have not been generated (yet) so that EVERY flier
        shows its own property information.
        """
        category = prop.category_id.name if prop.category_id else ''
        items = []
        if category and prop.city:
            items.append('%s property located in %s.' % (category, prop.city))
        elif prop.city:
            items.append('Property located in %s.' % prop.city)
        if prop.plot_area:
            line = 'Plot area of {:g} sq ft'.format(prop.plot_area)
            facing = self._selection_label(prop, 'facing_direction')
            if facing:
                line += ', %s facing' % facing
            items.append(line + '.')
        title = self._selection_label(prop, 'title_status')
        if title:
            items.append('Title status: %s.' % title)
        if prop.road_width:
            items.append('{:g} ft wide approach road.'.format(prop.road_width))
        if prop.price:
            line = 'Priced at %s' % self._money(prop.price)
            if prop.price_per_sqft:
                line += ' (\u20b9{:,.0f} per sq ft)'.format(prop.price_per_sqft)
            items.append(line + '.')
        if prop.gated_community:
            items.append('Located in a gated community.')
        if prop.emi_available:
            items.append('EMI facility available.')
        return self._bullets(items)

    def _fallback_nearby_html(self, prop, address):
        """Location block used when no landmarks and no AI nearby-places exist."""
        where = ', '.join(filter(None, [address, prop.zip_code]))
        if not where:
            return ''
        return self._bullets([
            'Located at %s.' % where,
            'Contact the listing agent below for details of nearby schools, hospitals and transit.',
        ])

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

        landmarks = self._clean_landmarks(prop.nearby_landmarks)

        overview_html = prop.ai_key_highlights if self._usable_html(prop.ai_key_highlights) else ''
        if not overview_html and not (prop.short_description or '').strip():
            overview_html = self._fallback_overview_html(prop)

        nearby_html = prop.ai_nearby_places if self._usable_html(prop.ai_nearby_places) else ''
        if not nearby_html and not landmarks:
            nearby_html = self._fallback_nearby_html(prop, address)

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
            'landmarks': landmarks,
            # ---- poster (reference-style flier) extras ----
            'price_short': self._money_short(prop.price),
            'city': prop.city or '',
            'state': prop.state_id.name if prop.state_id else '',
            'area_sqyd': '{:,.0f}'.format((prop.plot_area or 0) / 9.0) if prop.plot_area else '',
            'area_sqft': '{:,.0f}'.format(prop.plot_area or 0) if prop.plot_area else '',
            'price_per_sqyd': '\u20b9{:,.0f}'.format((prop.price_per_sqft or 0) * 9.0) if prop.price_per_sqft else '',
            'landmark_list': self._landmark_list(landmarks),
            'maps_url': self._maps_url(prop, address),
            'registration_pct': '{:g}'.format(prop.registration_charges or 0),
            'emi': bool(prop.emi_available),
            # rich sections shown on the detail page (Html fields -> Markup)
            'overview_html': overview_html,
            'about_html': prop.detailed_description or '',
            'nearby_html': nearby_html,
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

        # QR on the poster -> public "property information" page (photo + details)
        shown_id = data['id'] if data.get('source') == 'local' else prop.id
        info_url = '%s/property/%s/info' % (self._public_base(base_url), shown_id)
        qr_target = qr_link if ref else info_url
        qr_src = self._qr_data_uri(qr_target)
        map_link = data.get('maps_url') or qr_target

        # which of the 4 flier styles is shown (1-4); also used by shared links
        design = str(kwargs.get('design') or '1')
        if design not in ('1', '2', '3', '4'):
            design = '1'

        return request.render('real_estate_management.property_flier_page', {
            'design': design,
            'property': prop,
            'flier': data,
            'ref': ref,
            'ref_message': message,
            'qr_link': qr_link,
            'qr_src': qr_src,
            'map_link': map_link,
            'info_url': qr_target,
            'default_reference': DEFAULT_REFERENCE_LINK,
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
        address = val('address')

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

        # bid: must be a positive number higher than the current highest bid
        highest = self._highest_bid(prop)
        try:
            bid = float((val('bid_amount') or '').replace(',', ''))
        except ValueError:
            bid = 0.0
        if bid <= 0:
            errors['bid_amount'] = 'Enter your bid amount.'
        elif bid <= highest:
            errors['bid_amount'] = ('Your bid must be higher than the current highest bid (%s).'
                                    % self._money_plain(prop, highest))
        if errors:
            return self._json({'success': False, 'errors': errors,
                               'error': 'Please correct the highlighted fields.',
                               'highest_bid': self._money_plain(prop, highest) if highest else ''})

        # 1) the "Flyer Property Registrations" record shown in the backend
        try:
            flier_reg = request.env['flier.registration'].sudo().create({
                'property_id': prop.id,
                'customer_name': name,
                'phone': phone,
                'email': email,
                'address': address,
                'bid_amount': bid,
                'source': 'qr' if post.get('from_qr') else 'flier',
                'status': 'new',
            })
        except Exception:
            _logger.exception('Flier: registration failed')
            return self._json({'success': False,
                               'error': 'Something went wrong. Please try again.'})

        # 2) keep the existing customer-registration request (approval workflow) as before
        try:
            cust = request.env['customer.registration'].sudo().create({
                'customer_name': name,
                'email': email,
                'phone': phone,
                'address': address,
                'interested_in': 'buy',
                'notes': 'Registered from the flier of "%s" (property ID %s). Flyer registration: %s. Bid: %s.'
                         % (prop.name, prop.id, flier_reg.name, self._money_plain(prop, bid)),
                'status': 'submitted',
            })
            flier_reg.customer_registration_id = cust.id
        except Exception:
            _logger.exception('Flier: customer registration copy failed (flyer registration was saved)')

        return self._json({'success': True, 'reference': flier_reg.name,
                           'highest_bid': self._money_plain(prop, bid),
                           'bid_count': self._bid_count(prop)})

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

    # ─────────────────────────────────────────────────────────────
    # QR landing page: what opens when the flier's QR code is scanned
    # ─────────────────────────────────────────────────────────────
    @http.route('/property/<int:property_id>/info', type='http', auth='public', website=True)
    def property_info_page(self, property_id, **kwargs):
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            return request.not_found()

        base_url = request.httprequest.host_url.rstrip('/')
        # relative image URLs -> they work on whatever address the phone used to open the page
        data = self._flier_data_from_record(prop, '')
        gallery_all = ['/web/image/ir.attachment/%s/datas' % att.id for att in prop.gallery_image_ids]

        digits = re.sub(r'\D', '', data.get('contact_phone') or '')
        if len(digits) == 10:
            digits = '91' + digits
        page_url = '%s/property/%s/info' % (self._public_base(base_url), prop.id)
        wa_text = 'Hi, I am interested in "%s" (%s).' % (prop.name, page_url)

        # count this visit (one view per DEVICE); never break the page if it fails.
        # A device is recognised by a long-lived cookie, so two phones on the same
        # Wi-Fi / mobile network (same public IP) are counted separately.
        # Link-preview bots (WhatsApp, Telegram, Google...) are not counted.
        cookie_name = 'pv_device'
        device_id = request.httprequest.cookies.get(cookie_name) or ''
        new_device = False
        if not re.fullmatch(r'[0-9a-f]{32}', device_id):
            device_id = uuid.uuid4().hex
            new_device = True
        try:
            if self._is_bot():
                views_count = prop.views or 0
            else:
                views_count = prop.register_unique_view('dev:%s' % device_id)
        except Exception:
            _logger.exception('Flier: could not register property view')
            views_count = prop.views or 0

        response = request.render('real_estate_management.property_info_page', {
            'property': prop,
            'p': data,
            'gallery_all': gallery_all,
            'tel_href': ('tel:+%s' % digits) if digits else '',
            'wa_href': ('https://wa.me/%s?%s' % (digits, urlencode({'text': wa_text}))) if digits else '',
            'maps_url': self._maps_url(prop, data.get('address')),
            'og_image': '%s/web/image/property.property/%s/image' % (base_url, prop.id),
            'page_url': page_url,
            # chat assistant + registration form shown on this page
            'states': self._get_states(),
            'chat_property_id': prop.id,
            'highest_bid': self._highest_bid(prop),
            'highest_bid_display': self._money_plain(prop, self._highest_bid(prop)),
            'bid_count': self._bid_count(prop),
            'views_count': views_count,
        })
        if new_device:
            response.set_cookie(cookie_name, device_id, max_age=60 * 60 * 24 * 365,
                                httponly=True, samesite='Lax')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route('/property/<int:property_id>/qr.png', type='http', auth='public', website=True)
    def property_qr_image(self, property_id, **kwargs):
        """Downloadable QR code image of a property (opens its information page)."""
        prop = request.env['property.property'].sudo().browse(property_id)
        if not prop.exists() or not prop.is_published:
            return request.not_found()
        url = '%s/property/%s/info' % (
            self._public_base(request.httprequest.host_url.rstrip('/')), prop.id)
        png = self._qr_png(url, 500)
        if not png:
            return request.not_found()
        return request.make_response(png, headers=[
            ('Content-Type', 'image/png'),
            ('Content-Disposition', 'inline; filename="property-%s-qr.png"' % prop.id),
            ('Cache-Control', 'public, max-age=3600'),
        ])