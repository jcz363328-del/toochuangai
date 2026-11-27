"""TikTok customer service filtering, tracking and order export."""

from __future__ import annotations


DEFAULT_PAGE_SIZE = 100


def tk_customer_service(
    *,
    datetime,
    render_template,
    request,
    session,
    timedelta,
):
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (request.args.get('start_date') or default_day).strip()
    end_date = (request.args.get('end_date') or default_day).strip()
    return render_template(
        '内容生产工厂/tk_customer_service.html',
        user_id=user_id,
        user_name=user_name,
        start_date=start_date,
        end_date=end_date
    )


def _tk_extract_state_zip_tail(
    text,
    *,
    re,
):
    s = str(text or '').strip()
    m = re.match(r'^(.*?)[,\s]+([A-Za-z]{2})\s+(\d{4,10}(?:-\d{3,4})?)\s*$', s)
    if not m:
        return '', '', ''
    return m.group(1).strip(' ,'), m.group(2).strip(), m.group(3).strip()


def _tk_extract_us_zip_anywhere(
    text,
    *,
    re,
):
    s = str(text or '')
    matches = re.findall(r'(?<!\d)(\d{5}(?:-\d{4})?)(?!\d)', s)
    if not matches:
        return ''
    return matches[-1].strip()


def _tk_fallback_parse_us_address(
    raw_text,
    existing_phone='',
    *,
    _tk_extract_us_state_with_span,
    _tk_extract_us_zip_anywhere,
    _tk_guess_city_from_tail,
    _tk_split_street_city,
    re,
):
    raw = str(raw_text or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    raw = re.sub(r'\s+', ' ', raw).strip(' ,')
    phone = str(existing_phone or '').strip()
    if not raw:
        return {
            'receiver': '',
            'phone': phone,
            'address1': '',
            'city': '',
            'state': '',
            'zipcode': '',
            'country_code': ''
        }
    working = raw
    if not phone:
        phone_match = re.search(r'(\(\+?\d{1,3}\)\s*[\d\-\s]{7,}\d|\+\d[\d\-\s]{8,}\d|\b\d{3}-\d{3}-\d{4}\b|\b\d{3}-\d{4}-\d{4}\b|\b\d{10}\b)', working)
        if phone_match:
            mtext = phone_match.group(1).strip()
            digits = re.sub(r'\D', '', mtext)
            lead = '+' if '+' in mtext else ''
            extra_digits = ''
            if digits.startswith('1') and len(digits) > 11:
                extra_digits = digits[11:]
                digits = digits[:11]
            elif not digits.startswith('1') and len(digits) > 10:
                extra_digits = digits[10:]
                digits = digits[:10]
            phone = (lead + digits).strip() if digits else mtext
            before = working[:phone_match.start()].strip()
            after = working[phone_match.end():].strip()
            recovered = extra_digits.strip()
            working = ' '.join([x for x in [before, recovered, after] if x]).strip()
    normalized = working
    normalized = re.sub(r'United\s+States\s+of\s+America', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'I+NITED\s+States\s+of\s+America', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'I+NITED\s+States', ' United States ', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\bToexas\b', 'Texas', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\bdeb\.ary\b', 'debary', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')
    zipcode = _tk_extract_us_zip_anywhere(normalized)
    state, state_start, state_end = _tk_extract_us_state_with_span(normalized)
    country_code = 'US' if re.search(r'united\s+states|usa|\bus\b', normalized, flags=re.IGNORECASE) else ''
    work_no_country = re.sub(r'united\s+states(?:\s+of\s+america)?|usa', ' ', normalized, flags=re.IGNORECASE)
    if zipcode:
        work_no_country = re.sub(r'(?<!\d)' + re.escape(zipcode) + r'(?!\d)', ' ', work_no_country)
    cut_text = work_no_country
    if state and state_start >= 0:
        cut_text = work_no_country[:state_start]
    cut_text = re.sub(r'\s+', ' ', cut_text).strip(' ,')
    first_digit_match = re.search(r'\b\d+[A-Za-z\-]*\b', cut_text)
    receiver = ''
    first_part = cut_text
    if first_digit_match:
        receiver = cut_text[:first_digit_match.start()].strip(' ,')
        first_part = cut_text[first_digit_match.start():].strip(' ,')
    else:
        tokens = [t for t in cut_text.split() if t]
        if len(tokens) >= 2:
            receiver = ' '.join(tokens[:2]).strip(' ,')
            first_part = ' '.join(tokens[2:]).strip(' ,')
        elif tokens:
            receiver = tokens[0]
            first_part = ''
    address1 = first_part
    city = ''
    if first_part:
        addr_guess, city_guess = _tk_split_street_city(first_part)
        if addr_guess:
            address1 = addr_guess
        city = city_guess
        if not city:
            addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
            if city_tail:
                city = city_tail
                if addr_tail:
                    address1 = addr_tail
    return {
        'receiver': receiver.strip(' ,'),
        'phone': phone.strip(),
        'address1': address1.strip(' ,'),
        'city': city.strip(' ,'),
        'state': state.strip(),
        'zipcode': zipcode.strip(),
        'country_code': country_code
    }


def _tk_parse_wanghong_address(
    raw_address,
    *,
    _tk_country_to_iso2,
    _tk_extract_state_zip_tail,
    _tk_extract_us_state_with_span,
    _tk_extract_us_zip_anywhere,
    _tk_extract_zip_and_country,
    _tk_fallback_parse_us_address,
    _tk_guess_city_from_street_tail,
    _tk_guess_city_from_tail,
    _tk_split_street_city,
    re,
):
    raw = str(raw_address or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    raw = re.sub(r'\s+', ' ', raw).strip()
    receiver = ''
    phone = ''
    address1 = ''
    city = ''
    state = ''
    country_code = ''
    zipcode = ''
    house_no = ''
    if not raw:
        return {
            'receiver': receiver,
            'phone': phone,
            'address1': address1,
            'short_address': address1,
            'city': city,
            'state': state,
            'country_code': country_code,
            'zipcode': zipcode,
            'house_no': house_no
        }
    phone_match = re.search(r'(\(\+?\d{1,3}\)\s*[\d\-\s]{7,}\d|\+\d[\d\-\s]{8,}\d|\b\d{3}-\d{3}-\d{4}\b|\b\d{3}-\d{4}-\d{4}\b|\b\d{10}\b)', raw)
    location_part = raw
    if phone_match:
        receiver = raw[:phone_match.start()].strip(' ,')
        phone = phone_match.group(1).strip()
        phone_digits = re.sub(r'\D', '', phone)
        if phone_digits.startswith('1') and len(phone_digits) > 11:
            extra_digits = phone_digits[11:]
            phone_digits = phone_digits[:11]
            phone = ('+' + phone_digits) if '+' in phone else phone_digits
            location_part = (extra_digits + ' ' + raw[phone_match.end():].strip(' ,')).strip()
        elif (not phone_digits.startswith('1')) and len(phone_digits) > 10:
            extra_digits = phone_digits[10:]
            phone_digits = phone_digits[:10]
            phone = phone_digits
            location_part = (extra_digits + ' ' + raw[phone_match.end():].strip(' ,')).strip()
        else:
            location_part = raw[phone_match.end():].strip(' ,')
    location_part = re.sub(r'(?<=\))(?=[A-Za-z])', ' ', location_part)
    location_part = re.sub(r'[\[\]]', ' ', location_part)
    location_part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', location_part)
    location_part = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', location_part)
    location_part = re.sub(r'United\s+States\s+of\s+America', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'I+NITED\s+States\s+of\s+America', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'I+NITED\s+States', 'United States', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\bToexas\b', 'Texas', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\bdeb\.ary\b', 'debary', location_part, flags=re.IGNORECASE)
    location_part = re.sub(r'\s+', ' ', location_part).strip(' ,')
    parts = [p.strip() for p in location_part.split(',') if p and str(p).strip()]
    if parts:
        first_part = parts[0]
        address1 = first_part
        parsed_from_multi_parts = False
        if len(parts) >= 4:
            zip_candidate = ''
            for seg in reversed(parts):
                z = _tk_extract_us_zip_anywhere(seg)
                if z:
                    zip_candidate = z
                    break
            state_candidate = ''
            for seg in parts[1:]:
                st, _, _ = _tk_extract_us_state_with_span(seg)
                if st:
                    state_candidate = st
            country_candidate = ''
            joined_parts_text = ' '.join(parts)
            if re.search(r'united\s+states|usa|\bus\b', joined_parts_text, flags=re.IGNORECASE):
                country_candidate = 'US'
            addr_guess, city_guess = _tk_split_street_city(first_part)
            if addr_guess:
                address1 = addr_guess
            if len(parts) >= 2 and parts[1]:
                city = parts[1].strip()
            if (not city) and city_guess:
                city = city_guess
            if state_candidate:
                state = state_candidate
            if zip_candidate:
                zipcode = zip_candidate
            if country_candidate:
                country_code = country_candidate
            if zipcode or state:
                parsed_from_multi_parts = True
        if (not parsed_from_multi_parts) and len(parts) >= 3:
            p2 = parts[1]
            p3 = parts[2]
            if re.match(r'^[A-Za-z]{2}\s+\d{4,10}(?:-\d{3,4})?$', p3.strip()):
                addr_tail, city_tail = _tk_guess_city_from_street_tail(first_part)
                city = city_tail if city_tail else p2.strip()
                if addr_tail:
                    address1 = addr_tail
                state = p3.strip().split()[0]
                zipcode = p3.strip().split()[-1]
                country_code = 'US'
            else:
                state = p2
                zipcode, country_name = _tk_extract_zip_and_country(p3)
                country_code = _tk_country_to_iso2(country_name) if country_name else ''
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
                if not city:
                    addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
                    if city_tail:
                        city = city_tail
                        if addr_tail:
                            address1 = addr_tail
        elif len(parts) == 2:
            p2 = parts[1]
            if re.match(r'^[A-Za-z]{2}\s+\d{4,10}(?:-\d{3,4})?$', p2.strip()):
                state = p2.strip().split()[0]
                zipcode = p2.strip().split()[-1]
                country_code = 'US'
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
            else:
                state = p2
                addr_guess, city_guess = _tk_split_street_city(first_part)
                if addr_guess:
                    address1 = addr_guess
                city = city_guess
                if not city:
                    addr_tail, city_tail = _tk_guess_city_from_tail(first_part)
                    if city_tail:
                        city = city_tail
                        if addr_tail:
                            address1 = addr_tail
        else:
            prefix_no_tail, state_tail, zip_tail = _tk_extract_state_zip_tail(first_part)
            if state_tail and zip_tail:
                state = state_tail
                zipcode = zip_tail
                country_code = 'US'
                work_part = prefix_no_tail
            else:
                work_part = first_part
            addr_guess, city_guess = _tk_split_street_city(work_part)
            if addr_guess:
                address1 = addr_guess
            city = city_guess
            if not city:
                addr_tail, city_tail = _tk_guess_city_from_tail(work_part)
                if city_tail:
                    city = city_tail
                    if addr_tail:
                        address1 = addr_tail
    house_match = re.match(r'^(\d+[A-Za-z\-]*)\b', address1)
    if house_match:
        house_no = house_match.group(1)
    if not zipcode:
        zipcode = _tk_extract_us_zip_anywhere(location_part) or _tk_extract_us_zip_anywhere(raw)
    if (not state) and location_part:
        state_guess, _, _ = _tk_extract_us_state_with_span(location_part)
        if state_guess:
            state = state_guess
    if not country_code and (zipcode or state or re.search(r'united\s+states|usa|\bus\b', raw, flags=re.IGNORECASE)):
        country_code = 'US'
    if (not receiver) or (not address1) or (not city) or (not zipcode):
        fb = _tk_fallback_parse_us_address(raw, phone)
        if not receiver:
            receiver = fb.get('receiver', '')
        if not phone:
            phone = fb.get('phone', '')
        if not address1:
            address1 = fb.get('address1', '')
        if not city:
            city = fb.get('city', '')
        if not state:
            state = fb.get('state', '')
        if not zipcode:
            zipcode = fb.get('zipcode', '')
        if not country_code:
            country_code = fb.get('country_code', '')
        if not house_no:
            house_match_fb = re.match(r'^(\d+[A-Za-z\-]*)\b', str(address1 or ''))
            if house_match_fb:
                house_no = house_match_fb.group(1)
    state_codes = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    }
    raw_state = str(state or '').strip()
    state_norm, _, _ = _tk_extract_us_state_with_span(raw_state)
    if state_norm:
        state = state_norm
    else:
        upper_state = raw_state.upper()
        m_state = re.search(r'(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])', upper_state)
        if m_state and m_state.group(1) in state_codes:
            state = m_state.group(1)
    if str(state or '').strip().upper() not in state_codes:
        fb_state = _tk_fallback_parse_us_address(raw, phone).get('state', '').strip().upper()
        if fb_state in state_codes:
            state = fb_state
    return {
        'receiver': receiver,
        'phone': phone,
        'address1': address1,
        'short_address': address1,
        'city': city,
        'state': state,
        'country_code': country_code,
        'zipcode': zipcode,
        'house_no': house_no
    }


def _tk_validate_export_address(
    raw_address,
    parsed,
    order_no,
):
    errs = []
    raw = str(raw_address or '').strip()
    order_no = str(order_no or '').strip()
    if not order_no:
        errs.append('订单号为空')
    if not raw or raw in {'0', '00', '000', '-'}:
        errs.append('网红地址为空或无效')
    if not parsed.get('receiver'):
        errs.append('未识别收件人')
    if not parsed.get('address1'):
        errs.append('未识别地址1')
    if not parsed.get('city'):
        errs.append('未识别城市')
    if not parsed.get('zipcode'):
        errs.append('未识别邮编')
    return errs


def _tk_normalize_export_country(
    country_text,
    *,
    _tk_country_to_iso2,
):
    c = str(country_text or '').strip()
    if not c:
        return ''
    if len(c) == 2 and c.isalpha():
        return c.upper()
    return _tk_country_to_iso2(c)


def _tk_prepare_export_contact_fields(
    raw_address,
    parsed,
    *,
    _tk_guess_city_from_export_text,
    _tk_normalize_export_country,
    _tk_normalize_export_phone,
    _tk_parse_structured_export_address,
    _tk_refine_export_address_city,
    re,
):
    structured = _tk_parse_structured_export_address(raw_address)
    receiver = str(parsed.get('receiver') or '').strip()
    phone = str(parsed.get('phone') or '').strip()
    address1 = str(parsed.get('address1') or '').strip()
    city = str(parsed.get('city') or '').strip()
    state = str(parsed.get('state') or '').strip()
    country = str(parsed.get('country_code') or '').strip()
    zipcode = str(parsed.get('zipcode') or '').strip()
    if structured:
        receiver = receiver or structured.get('receiver', '')
        phone = phone or structured.get('phone', '')
        address1 = address1 or structured.get('address1', '')
        city = city or structured.get('city', '')
        state = state or structured.get('state', '')
        country = country or structured.get('country', '')
        zipcode = zipcode or structured.get('zipcode', '')
    country = _tk_normalize_export_country(country)
    if not country and structured:
        country = _tk_normalize_export_country(structured.get('country', ''))
    address1, city = _tk_refine_export_address_city(address1, city)
    if not city:
        city = _tk_guess_city_from_export_text(raw_address, address1=address1, state=state, zipcode=zipcode)
    if city:
        city = re.sub(r'\s+', ' ', str(city)).strip()
    return {
        'receiver': receiver,
        'phone': _tk_normalize_export_phone(phone),
        'address1': address1,
        'city': city,
        'state': state,
        'country': country,
        'zipcode': zipcode
    }


def _tk_parse_shop_names_from_request(*, request):
    vals = request.args.getlist('shops') or []
    shop_name = (request.args.get('shop_name') or '').strip()
    if shop_name:
        vals.append(shop_name)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s or s.upper() == 'ALL':
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_parse_importers_from_request(*, request):
    vals = request.args.getlist('importers') or []
    importer_name = (request.args.get('importer_name') or '').strip()
    if importer_name:
        vals.append(importer_name)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s or s.upper() == 'ALL':
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_parse_order_nos_from_request(*, request):
    vals = request.args.getlist('order_nos') or []
    order_no = (request.args.get('order_no') or '').strip()
    if order_no:
        vals.append(order_no)
    result = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        for p in str(v).replace('，', ',').split(','):
            s = p.strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            result.append(s)
    return result


def _tk_customer_service_join_key(value):
    return str(value or '').strip().upper()


def _tk_customer_service_fill_complete_tracking_numbers(
    items,
    query_fn,
    *,
    _tk_customer_service_join_key,
):
    """Replace aggregate placeholders with every distinct available tracking number.

    Tracking belongs to the shipment order for display purposes. Show every
    non-empty tracking number found for that order, even when Saihu converted the
    SKU or the order was shipped in multiple packages.
    """
    if not items:
        return items

    order_values = {}
    for item in items:
        raw_order = str(item.get('FaYangDingDanHao') or '').strip()
        order_key = _tk_customer_service_join_key(raw_order)
        if raw_order and order_key not in order_values:
            order_values[order_key] = raw_order
    if not order_values:
        return items

    order_tracks = {}

    def add_tracking(mapping, key, tracking_no):
        values = mapping.setdefault(key, [])
        normalized = _tk_customer_service_join_key(tracking_no)
        if normalized and all(
            _tk_customer_service_join_key(existing) != normalized
            for existing in values
        ):
            values.append(tracking_no)

    raw_orders = list(order_values.values())
    batch_size = 400
    for start in range(0, len(raw_orders), batch_size):
        batch = raw_orders[start:start + batch_size]
        in_clause = ', '.join(
            "N'" + value.replace("'", "''") + "'"
            for value in batch
        )
        rows = query_fn(f"""
            SELECT DanHao, SKU, GenZongHao
            FROM TK_DingDan_shouhou WITH (NOLOCK)
            WHERE DanHao IN ({in_clause})
              AND LTRIM(RTRIM(ISNULL(CAST(GenZongHao AS NVARCHAR(500)), ''))) <> ''
            ORDER BY ID ASC
        """) or []
        for row in rows:
            if isinstance(row, dict):
                order_no = row.get('DanHao') if 'DanHao' in row else row.get('danhao')
                sku = row.get('SKU') if 'SKU' in row else row.get('sku')
                tracking_no = (
                    row.get('GenZongHao')
                    if 'GenZongHao' in row
                    else row.get('genzonghao')
                )
            elif isinstance(row, (list, tuple)):
                order_no = row[0] if len(row) > 0 else ''
                sku = row[1] if len(row) > 1 else ''
                tracking_no = row[2] if len(row) > 2 else ''
            else:
                continue
            order_key = _tk_customer_service_join_key(order_no)
            tracking_text = str(tracking_no or '').strip()
            if not order_key or not tracking_text:
                continue
            add_tracking(order_tracks, order_key, tracking_text)

    for item in items:
        order_key = _tk_customer_service_join_key(item.get('FaYangDingDanHao'))
        tracking_values = order_tracks.get(order_key)
        if tracking_values:
            item['GenZongHao'] = ' / '.join(tracking_values)
    return items


def _tk_customer_service_filter_sql(
    start_date,
    end_date,
    shop_names=None,
    importer_names=None,
    order_nos=None,
):
    start_safe = start_date.replace("'", "''")
    end_safe = end_date.replace("'", "''")
    shop_names = shop_names or []
    importer_names = importer_names or []
    order_nos = order_nos or []
    shop_filter = ""
    importer_filter = ""
    order_filter = ""
    if shop_names:
        safe_vals = []
        for s in shop_names:
            safe_vals.append("'" + str(s).replace("'", "''") + "'")
        shop_filter = f" AND ISNULL(CAST(zd.dian AS NVARCHAR(100)), '') IN ({', '.join(safe_vals)})"
    if importer_names:
        safe_vals = []
        for s in importer_names:
            safe_vals.append("'" + str(s).replace("'", "''") + "'")
        importer_filter = f"""
          AND (
                CASE
                    WHEN CHARINDEX('@', ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), '')) > 0
                        THEN LTRIM(RTRIM(RIGHT(
                            ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), ''),
                            CHARINDEX('@', REVERSE(ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), ''))) - 1
                        )))
                    ELSE LTRIM(RTRIM(ISNULL(CAST(hz.DaoRuRen AS NVARCHAR(200)), '')))
                END
              ) IN ({', '.join(safe_vals)})
        """
    if order_nos:
        conds = []
        for s in order_nos:
            s_safe = str(s).replace("'", "''")
            conds.append(
                f"CHARINDEX('{s_safe}', ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')) > 0"
            )
        order_filter = " AND (" + " OR ".join(conds) + ")"
    return f"""
        hz.DaoRuShiJian >= CONVERT(date, '{start_safe}', 23)
        AND hz.DaoRuShiJian < DATEADD(day, 1, CONVERT(date, '{end_safe}', 23))
        AND ISNULL(hz.FaYangDingDanHao, '') <> ''
        AND CHARINDEX('57', ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')) = 0
        AND CHARINDEX('TKWS', UPPER(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), ''))) = 0
        {shop_filter}
        {importer_filter}
        {order_filter}
    """


def _tk_customer_service_query_total(
    start_date,
    end_date,
    shop_names=None,
    importer_names=None,
    order_nos=None,
    *,
    _tk_customer_service_filter_sql,
    sf_db,
):
    where_sql = _tk_customer_service_filter_sql(
        start_date,
        end_date,
        shop_names,
        importer_names,
        order_nos,
    )
    rows = sf_db(f"""
        SELECT COUNT(1)
        FROM TK_WangHong_HeZuo hz
        LEFT JOIN ZiDian zd
            ON hz.SKU = zd.SKU
        WHERE {where_sql}
    """) or []
    if isinstance(rows, list):
        first = rows[0] if rows else 0
    else:
        first = rows
    if isinstance(first, dict):
        first = next(iter(first.values()), 0)
    elif isinstance(first, (list, tuple)):
        first = first[0] if first else 0
    try:
        return int(first or 0)
    except (TypeError, ValueError):
        return 0


def _tk_customer_service_query_shops(
    start_date,
    end_date,
    *,
    _tk_customer_service_filter_sql,
    sf_db,
):
    where_sql = _tk_customer_service_filter_sql(start_date, end_date)
    rows = sf_db(f"""
        SELECT DISTINCT LTRIM(RTRIM(CAST(zd.dian AS NVARCHAR(100)))) AS dian
        FROM TK_WangHong_HeZuo hz
        INNER JOIN ZiDian zd
            ON hz.SKU = zd.SKU
        WHERE {where_sql}
          AND LTRIM(RTRIM(ISNULL(CAST(zd.dian AS NVARCHAR(100)), ''))) <> ''
        ORDER BY dian
    """) or []
    shops = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get('dian') if 'dian' in row else row.get('Dian')
        elif isinstance(row, (list, tuple)):
            value = row[0] if row else ''
        else:
            value = row
        value = '' if value is None else str(value).strip()
        if value:
            shops.append(value)
    return shops


def _tk_customer_service_query_rows(
    start_date,
    end_date,
    shop_names=None,
    importer_names=None,
    order_nos=None,
    page=None,
    page_size=DEFAULT_PAGE_SIZE,
    *,
    _tk_customer_service_fill_complete_tracking_numbers,
    _tk_customer_service_filter_sql,
    datetime,
    sf_db,
):
    where_sql = _tk_customer_service_filter_sql(
        start_date,
        end_date,
        shop_names,
        importer_names,
        order_nos,
    )
    pagination_sql = ""
    if page is not None:
        safe_page = max(int(page), 1)
        safe_page_size = max(int(page_size), 1)
        offset = (safe_page - 1) * safe_page_size
        pagination_sql = f"OFFSET {offset} ROWS FETCH NEXT {safe_page_size} ROWS ONLY"
    after_sale_exact_page_filter = ""
    after_sale_order_page_filter = ""
    if page is not None:
        after_sale_exact_page_filter = """
            WHERE EXISTS (
                SELECT 1
                FROM page_rows
                WHERE sh.DanHao = page_rows.FaYangDingDanHao
                  AND sh.SKU = page_rows.SKU
            )
        """
        after_sale_order_page_filter = """
            AND EXISTS (
                SELECT 1
                FROM page_rows
                WHERE sh.DanHao = page_rows.FaYangDingDanHao
            )
        """
    after_sale_exact_sql = f"""
            SELECT
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.DanHao AS NVARCHAR(100)), '')))) AS join_danhao,
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.SKU AS NVARCHAR(100)), '')))) AS join_sku,
                MAX(ISNULL(sh.GenZongHao, '')) AS GenZongHao,
                MAX(ISNULL(sh.kefubeizhu, '')) AS kefubeizhu,
                MAX(sh.fahuoshijian) AS fahuoshijian
            FROM TK_DingDan_shouhou sh
            {after_sale_exact_page_filter}
            GROUP BY
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.DanHao AS NVARCHAR(100)), '')))),
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.SKU AS NVARCHAR(100)), ''))))
    """
    # Some Saihu sample/after-sale rows use a converted SKU while retaining the
    # same order-level tracking number. Fall back by order whenever a non-empty
    # tracking number exists; the final fill step expands multi-package orders to
    # every distinct tracking number.
    after_sale_order_sql = f"""
            SELECT
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.DanHao AS NVARCHAR(100)), '')))) AS join_danhao,
                MAX(LTRIM(RTRIM(ISNULL(CAST(sh.GenZongHao AS NVARCHAR(500)), '')))) AS GenZongHao,
                MAX(sh.fahuoshijian) AS fahuoshijian
            FROM TK_DingDan_shouhou sh
            WHERE LTRIM(RTRIM(ISNULL(CAST(sh.GenZongHao AS NVARCHAR(500)), ''))) <> ''
            {after_sale_order_page_filter}
            GROUP BY
                UPPER(LTRIM(RTRIM(ISNULL(CAST(sh.DanHao AS NVARCHAR(100)), ''))))
    """
    if page is not None:
        # Page the filtered cooperation rows before joining the aggregated after-sale
        # table. This keeps the expensive join limited to the 100 visible rows.
        sql = f"""
            WITH page_rows AS (
                SELECT
                    hz.SKU,
                    zl.wanghongdizhi,
                    zd.dian,
                    hz.ID,
                    hz.DaoRuRen,
                    hz.DaoRuShiJian,
                    hz.FaYangDingDanHao
                FROM TK_WangHong_HeZuo hz
                LEFT JOIN TK_WangHong_ZiLiao zl
                    ON hz.BianHao = zl.BianHao
                LEFT JOIN ZiDian zd
                    ON hz.SKU = zd.SKU
                WHERE {where_sql}
                ORDER BY hz.ID DESC, hz.SKU ASC, hz.FaYangDingDanHao ASC
                {pagination_sql}
            )
            SELECT
                page_rows.SKU,
                page_rows.wanghongdizhi,
                page_rows.dian,
                page_rows.ID,
                page_rows.DaoRuRen,
                page_rows.DaoRuShiJian,
                page_rows.FaYangDingDanHao,
                COALESCE(NULLIF(dd_exact.GenZongHao, ''), dd_order.GenZongHao, '') AS GenZongHao,
                dd_exact.kefubeizhu,
                CASE
                    WHEN NULLIF(dd_exact.GenZongHao, '') IS NOT NULL THEN dd_exact.fahuoshijian
                    ELSE dd_order.fahuoshijian
                END AS fahuoshijian
            FROM page_rows
            LEFT JOIN ({after_sale_exact_sql}) dd_exact
                ON UPPER(LTRIM(RTRIM(ISNULL(CAST(page_rows.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_exact.join_danhao
               AND UPPER(LTRIM(RTRIM(ISNULL(CAST(page_rows.SKU AS NVARCHAR(100)), '')))) = dd_exact.join_sku
            LEFT JOIN ({after_sale_order_sql}) dd_order
                ON UPPER(LTRIM(RTRIM(ISNULL(CAST(page_rows.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_order.join_danhao
            ORDER BY page_rows.ID DESC, page_rows.SKU ASC, page_rows.FaYangDingDanHao ASC
        """
    else:
        # Export intentionally remains unpaged so users still receive all matching rows.
        sql = f"""
            SELECT
                hz.SKU,
                zl.wanghongdizhi,
                zd.dian,
                hz.ID,
                hz.DaoRuRen,
                hz.DaoRuShiJian,
                hz.FaYangDingDanHao,
                COALESCE(NULLIF(dd_exact.GenZongHao, ''), dd_order.GenZongHao, '') AS GenZongHao,
                dd_exact.kefubeizhu,
                CASE
                    WHEN NULLIF(dd_exact.GenZongHao, '') IS NOT NULL THEN dd_exact.fahuoshijian
                    ELSE dd_order.fahuoshijian
                END AS fahuoshijian
            FROM TK_WangHong_HeZuo hz
            LEFT JOIN TK_WangHong_ZiLiao zl
                ON hz.BianHao = zl.BianHao
            LEFT JOIN ZiDian zd
                ON hz.SKU = zd.SKU
            LEFT JOIN ({after_sale_exact_sql}) dd_exact
                ON UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_exact.join_danhao
               AND UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.SKU AS NVARCHAR(100)), '')))) = dd_exact.join_sku
            LEFT JOIN ({after_sale_order_sql}) dd_order
                ON UPPER(LTRIM(RTRIM(ISNULL(CAST(hz.FaYangDingDanHao AS NVARCHAR(100)), '')))) = dd_order.join_danhao
            WHERE {where_sql}
            ORDER BY hz.ID DESC, hz.SKU ASC, hz.FaYangDingDanHao ASC
        """
    rows = sf_db(sql) or []
    cols = ['SKU', 'wanghongdizhi', 'dian', 'ID', 'DaoRuRen', 'DaoRuShiJian', 'FaYangDingDanHao', 'GenZongHao', 'kefubeizhu', 'fahuoshijian']
    items = []
    for r in rows:
        if isinstance(r, dict):
            item = {}
            for k in cols:
                item[k] = r.get(k) if k in r else r.get(k.lower())
        elif isinstance(r, (list, tuple)):
            item = {cols[i]: (r[i] if i < len(r) else None) for i in range(len(cols))}
        else:
            item = {}
        for k in ['SKU', 'wanghongdizhi', 'dian', 'DaoRuRen', 'FaYangDingDanHao', 'GenZongHao', 'kefubeizhu']:
            v = item.get(k)
            item[k] = '' if v is None else str(v)
        import_user = item.get('DaoRuRen', '')
        if '@' in import_user:
            import_tail = import_user.split('@')[-1].strip()
            if import_tail:
                item['DaoRuRen'] = import_tail
        if not (item.get('kefubeizhu') or '').strip():
            id_text = '' if item.get('ID') is None else str(item.get('ID')).strip()
            importer_text = (item.get('DaoRuRen') or '').strip()
            fallback_parts = []
            if id_text:
                fallback_parts.append(f"ID:{id_text}")
            if importer_text:
                fallback_parts.append(f"导入人:{importer_text}")
            item['kefubeizhu'] = ' '.join(fallback_parts)
        t_import = item.get('DaoRuShiJian')
        if isinstance(t_import, datetime):
            item['DaoRuShiJian'] = t_import.strftime('%Y-%m-%d %H:%M:%S')
        else:
            item['DaoRuShiJian'] = '' if t_import is None else str(t_import)
        t_ship = item.get('fahuoshijian')
        if isinstance(t_ship, datetime):
            item['fahuoshijian'] = t_ship.strftime('%Y-%m-%d %H:%M:%S')
        else:
            item['fahuoshijian'] = '' if t_ship is None else str(t_ship)
        items.append(item)
    return _tk_customer_service_fill_complete_tracking_numbers(items)


def api_tk_customer_service_list(
    *,
    _TK_CUSTOMER_SERVICE_PAGE_SIZE,
    _tk_customer_service_query_rows,
    _tk_customer_service_query_total,
    _tk_parse_importers_from_request,
    _tk_parse_order_nos_from_request,
    _tk_parse_shop_names_from_request,
    datetime,
    jsonify,
    request,
    timedelta,
):
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        try:
            page = max(int(request.args.get('page') or 1), 1)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '页码必须为正整数'}), 400
        page_size = _TK_CUSTOMER_SERVICE_PAGE_SIZE
        shop_names = _tk_parse_shop_names_from_request()
        importer_names = _tk_parse_importers_from_request()
        order_nos = _tk_parse_order_nos_from_request()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        if start_date > end_date:
            return jsonify({'success': False, 'message': '开始日期不能晚于结束日期'}), 400
        total = _tk_customer_service_query_total(
            start_date,
            end_date,
            shop_names,
            importer_names,
            order_nos,
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        items = _tk_customer_service_query_rows(
            start_date,
            end_date,
            shop_names,
            importer_names,
            order_nos,
            page=page,
            page_size=page_size,
        )
        return jsonify({
            'success': True,
            'items': items,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取TK客服数据失败: {str(e)}'}), 500


def api_tk_customer_service_shops(
    *,
    _tk_customer_service_query_shops,
    datetime,
    jsonify,
    request,
    timedelta,
):
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        if start_date > end_date:
            return jsonify({'success': False, 'message': '开始日期不能晚于结束日期'}), 400
        shops = _tk_customer_service_query_shops(start_date, end_date)
        return jsonify({'success': True, 'shops': shops})
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取店铺列表失败: {str(e)}'}), 500


def _tk_customer_service_build_export_rows(
    items,
    *,
    _tk_parse_wanghong_address,
    _tk_prepare_export_contact_fields,
    _tk_validate_export_address,
):
    """Build every requested export row and separately collect validation errors.

    Address validation is advisory: a malformed address must not make a matching
    customer-service record disappear from the primary export sheet.
    """
    export_rows = []
    error_rows = []
    for item in items or []:
        raw_address = item.get('wanghongdizhi', '')
        order_no = item.get('FaYangDingDanHao', '')
        parsed = _tk_parse_wanghong_address(raw_address)
        export_contact = _tk_prepare_export_contact_fields(raw_address, parsed)
        errors = _tk_validate_export_address(raw_address, parsed, order_no)
        if errors:
            error_rows.append({
                '订单号': order_no,
                'SKU': item.get('SKU', ''),
                '店铺': item.get('dian', ''),
                '客服备注': item.get('kefubeizhu', ''),
                '网红地址原文': raw_address,
                '错误原因': '；'.join(errors)
            })

        shop_raw = str(item.get('dian') or '').strip()
        shop_label = f"{shop_raw}（自发货）" if shop_raw else ''
        export_rows.append({
            '*订单号': order_no,
            '*店铺名称': shop_label,
            '*sku': item.get('SKU', ''),
            '*数量': 1,
            '*单价': 0,
            '买家运费': '',
            '币种（默认USD）': 'USD',
            '买家指定物流': '',
            '下单时间': '',
            '发货截止时间': '',
            '发货仓库': '',
            'IOSS税号': '',
            '买家留言': '',
            '*收件人': export_contact.get('receiver', ''),
            '*地址1': export_contact.get('address1', ''),
            '地址2': '',
            '短地址': str(raw_address or '').strip(),
            '*城市': export_contact.get('city', ''),
            '州/省': export_contact.get('state', ''),
            '区/县': '',
            '*国家二字码': export_contact.get('country', '') or 'US',
            '*邮编': export_contact.get('zipcode', ''),
            '电话': export_contact.get('phone', ''),
            '手机': '',
            '邮箱': '',
            '税号': '',
            '门牌号': '',
            '订单备注': item.get('kefubeizhu', ''),
            '中文报关名': '',
            '英文报关名': '',
            '申报金额（USD）': '',
            '申报重量（g）': '',
            '材质': '',
            '用途': '',
            '海关编码': '',
            '报关属性': '',
            '业务员': '',
            '交易方式': '',
            '买方公司': ''
        })
    return export_rows, error_rows


def api_tk_customer_service_export(
    *,
    _tk_customer_service_build_export_rows,
    _tk_customer_service_query_rows,
    _tk_parse_importers_from_request,
    _tk_parse_order_nos_from_request,
    _tk_parse_shop_names_from_request,
    datetime,
    jsonify,
    request,
    send_file,
    timedelta,
):
    try:
        default_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (request.args.get('start_date') or default_day).strip()
        end_date = (request.args.get('end_date') or default_day).strip()
        shop_names = _tk_parse_shop_names_from_request()
        importer_names = _tk_parse_importers_from_request()
        order_nos = _tk_parse_order_nos_from_request()
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'}), 400
        if start_date > end_date:
            return jsonify({'success': False, 'message': '开始日期不能晚于结束日期'}), 400
        items = _tk_customer_service_query_rows(start_date, end_date, shop_names, importer_names, order_nos)
        headers = [
            '*订单号', '*店铺名称', '*sku', '*数量', '*单价', '买家运费', '币种（默认USD）', '买家指定物流', '下单时间', '发货截止时间', '发货仓库', 'IOSS税号', '买家留言',
            '*收件人', '*地址1', '地址2', '短地址', '*城市', '州/省', '区/县', '*国家二字码', '*邮编', '电话', '手机', '邮箱', '税号', '门牌号', '订单备注',
            '中文报关名', '英文报关名', '申报金额（USD）', '申报重量（g）', '材质', '用途', '海关编码', '报关属性', '业务员', '交易方式', '买方公司'
        ]
        export_rows, error_rows = _tk_customer_service_build_export_rows(items)
        import pandas as pd
        from io import BytesIO
        df = pd.DataFrame(export_rows, columns=headers)
        output = BytesIO()
        error_headers = ['订单号', 'SKU', '店铺', '客服备注', '网红地址原文', '错误原因']
        error_df = pd.DataFrame(error_rows, columns=error_headers)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='全部数据')
            error_df.to_excel(writer, index=False, sheet_name='导出错误列表')
        output.seek(0)
        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"TK客服导出_{start_date}_to_{end_date}_{now_str}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500


def api_tk_customer_service_update_note(
    *,
    dui_db,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        order_no = str(data.get('FaYangDingDanHao') or '').strip()
        sku = str(data.get('SKU') or '').strip()
        note = str(data.get('kefubeizhu') or '')
        if not order_no:
            return jsonify({'success': False, 'message': '发样订单号不能为空'}), 400
        if not sku:
            return jsonify({'success': False, 'message': 'SKU不能为空'}), 400
        order_no_safe = order_no.replace("'", "''")
        sku_safe = sku.replace("'", "''")
        note_safe = note.replace("'", "''")
        upsert_sql = (
            "IF EXISTS ("
            "    SELECT 1 FROM TK_DingDan_shouhou "
            f"    WHERE UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{order_no_safe}'))) "
            f"      AND UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{sku_safe}')))"
            ") "
            "BEGIN "
            "    UPDATE TK_DingDan_shouhou "
            f"    SET kefubeizhu = '{note_safe}' "
            f"    WHERE UPPER(LTRIM(RTRIM(ISNULL(CAST(DanHao AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{order_no_safe}'))) "
            f"      AND UPPER(LTRIM(RTRIM(ISNULL(CAST(SKU AS NVARCHAR(100)), '')))) = UPPER(LTRIM(RTRIM('{sku_safe}'))) "
            "END "
            "ELSE "
            "BEGIN "
            "    INSERT INTO TK_DingDan_shouhou (DanHao, SKU, kefubeizhu) "
            f"    VALUES ('{order_no_safe}', '{sku_safe}', '{note_safe}') "
            "END"
        )
        dui_db(upsert_sql)
        return jsonify({'success': True, 'message': '客服备注保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新客服备注失败: {str(e)}'}), 500
