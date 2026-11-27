"""Address normalization for TikTok exports."""
import re


def _tk_country_to_iso2(country_name):
    s = re.sub(r'[^a-zA-Z ]', ' ', str(country_name or '')).strip().lower()
    s = re.sub(r'\s+', ' ', s)
    if not s:
        return ''
    mapping = {
        'united states': 'US',
        'united states of america': 'US',
        'usa': 'US',
        'us': 'US',
        'china': 'CN',
        'hong kong': 'HK',
        'united kingdom': 'GB',
        'uk': 'GB',
        'great britain': 'GB',
        'canada': 'CA',
        'australia': 'AU',
        'germany': 'DE',
        'france': 'FR',
        'italy': 'IT',
        'spain': 'ES',
        'japan': 'JP',
        'korea': 'KR',
        'south korea': 'KR',
        'singapore': 'SG',
        'malaysia': 'MY',
        'thailand': 'TH',
        'vietnam': 'VN',
        'philippines': 'PH',
        'indonesia': 'ID'
    }
    if s in mapping:
        return mapping[s]
    parts = [p for p in s.split(' ') if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()


def _tk_split_street_city(first_part):
    text = str(first_part or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) <= 1:
        return text, ''
    suffixes = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    unit_words = {'apt', 'apartment', 'unit', 'ste', 'suite', '#', 'fl', 'floor', 'rm', 'room', 'bldg'}
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    split_idx = -1
    for i, tk in enumerate(tokens):
        norm = re.sub(r'[^a-zA-Z]', '', tk).lower()
        if norm in suffixes:
            split_idx = i
    if split_idx < 0 or split_idx >= len(tokens) - 1:
        return text, ''
    j = split_idx + 1
    while j < len(tokens):
        norm = re.sub(r'[^a-zA-Z#]', '', tokens[j]).lower()
        if norm in unit_words:
            j += 1
            if j < len(tokens) and re.search(r'\d', tokens[j]):
                j += 1
            continue
        break
    if j >= len(tokens):
        return text, ''
    city_tokens = tokens[j:]
    if len(city_tokens) == 1:
        norm_city = re.sub(r'[^a-zA-Z]', '', city_tokens[0]).lower()
        if norm_city in suffixes:
            return text, ''
    if len(city_tokens) >= 2:
        first_city_norm = re.sub(r'[^a-zA-Z]', '', city_tokens[0]).lower()
        if first_city_norm in direction_words:
            city = city_tokens[0] + ' ' + city_tokens[1]
            if len(city_tokens) > 2:
                city = city + ' ' + ' '.join(city_tokens[2:])
        else:
            city = ' '.join(city_tokens)
    else:
        city = city_tokens[0]
    address1 = ' '.join(tokens[:j]).strip()
    return address1, city.strip()


def _tk_extract_zip_and_country(part):
    text = str(part or '').strip()
    zip_match = re.search(r'(\d{4,10}(?:-\d{3,4})?)\s*$', text)
    if not zip_match:
        return '', text
    zipcode = zip_match.group(1)
    country_name = text[:zip_match.start()].strip(' ,')
    return zipcode, country_name


def _tk_extract_us_state_with_span(text):
    s = str(text or '')
    if not s:
        return '', -1, -1
    state_codes = {
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    }
    name_map = {
        'virginia': 'VA',
        'texas': 'TX',
        'toexas': 'TX',
        'florida': 'FL',
        'ohio': 'OH'
    }
    lower_s = s.lower()
    best_name = ''
    best_name_span = (-1, -1)
    for name, code in name_map.items():
        for m in re.finditer(r'\b' + re.escape(name) + r'\b', lower_s):
            best_name = code
            best_name_span = m.span()
    if best_name:
        return best_name, best_name_span[0], best_name_span[1]
    best_code = ''
    best_span = (-1, -1)
    for m in re.finditer(r'(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])', s):
        code = m.group(1)
        if code in state_codes:
            best_code = code
            best_span = m.span(1)
    if best_code:
        return best_code, best_span[0], best_span[1]
    return '', -1, -1


def _tk_guess_city_from_tail(prefix_text):
    text = str(prefix_text or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) == 1:
        return '', tokens[0]
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    two_word_city_tail = {'haven', 'hills', 'falls', 'springs', 'heights', 'beach', 'city', 'park', 'point', 'bay'}
    last_norm = re.sub(r'[^a-zA-Z]', '', tokens[-1]).lower()
    prev_norm = re.sub(r'[^a-zA-Z]', '', tokens[-2]).lower() if len(tokens) >= 2 else ''
    if len(tokens) >= 2 and (prev_norm in direction_words or last_norm in two_word_city_tail):
        return ' '.join(tokens[:-2]).strip(), (tokens[-2] + ' ' + tokens[-1]).strip()
    return ' '.join(tokens[:-1]).strip(), tokens[-1].strip()


def _tk_guess_city_from_street_tail(prefix_text):
    text = str(prefix_text or '').strip()
    if not text:
        return '', ''
    tokens = text.split()
    if len(tokens) < 2:
        return '', ''
    suffixes = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    last_norm = re.sub(r'[^a-zA-Z]', '', tokens[-1]).lower()
    prev_norm = re.sub(r'[^a-zA-Z]', '', tokens[-2]).lower()
    if last_norm in suffixes and prev_norm in direction_words:
        addr = ' '.join(tokens[:-2]).strip()
        city = (tokens[-2] + ' ' + tokens[-1]).strip()
        return addr, city
    return '', ''


def _tk_parse_structured_export_address(raw_address):
    text = str(raw_address or '').strip()
    parts = [p.strip() for p in text.replace('，', ',').split(',') if str(p).strip()]
    if len(parts) < 7:
        return {}
    return {
        'receiver': parts[0],
        'phone': parts[1],
        'address1': parts[2],
        'city': parts[3],
        'state': parts[4],
        'country': parts[5],
        'zipcode': parts[6]
    }


def _tk_normalize_export_phone(phone_text):
    digits = re.sub(r'\D', '', str(phone_text or ''))
    if not digits:
        return '0000000000'
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    elif len(digits) > 10:
        digits = digits[-10:]
    return digits or '0000000000'


def _tk_refine_export_address_city(address1, city):
    addr = str(address1 or '').strip()
    city_text = str(city or '').strip()
    if not city_text:
        return addr, city_text
    tokens = [t for t in city_text.split() if t]
    if not tokens:
        return addr, ''
    street_words = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    direction_words = {'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west'}
    norm_tokens = [re.sub(r'[^a-zA-Z]', '', t).lower() for t in tokens]
    should_move_to_addr = False
    if len(tokens) == 1:
        one = norm_tokens[0]
        if (not one) or one in street_words or one in direction_words or len(one) <= 1:
            should_move_to_addr = True
    elif len(tokens) == 2:
        first = norm_tokens[0]
        second = norm_tokens[1]
        if (first in direction_words and second in street_words) or (first in street_words and second in street_words):
            should_move_to_addr = True
    if should_move_to_addr:
        merged = (addr + ' ' + city_text).strip() if addr else city_text
        return re.sub(r'\s+', ' ', merged).strip(), ''
    return addr, city_text


def _tk_guess_city_from_export_text(raw_address, address1='', state='', zipcode=''):
    text = str(raw_address or '').replace('\u00A0', ' ').replace('\u3000', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''
    state_code = str(state or '').strip().upper()
    zip_code = str(zipcode or '').strip()
    city_candidate = ''
    if state_code:
        if zip_code:
            p = re.compile(rf"([A-Za-z][A-Za-z\s\.\-']{{1,50}}?)\s*,?\s*{re.escape(state_code)}\s+{re.escape(zip_code)}", re.IGNORECASE)
            m = p.search(text)
            if m:
                city_candidate = str(m.group(1) or '').split(',')[-1].strip()
        if not city_candidate:
            p = re.compile(rf"([A-Za-z][A-Za-z\s\.\-']{{1,50}}?)\s*,?\s*{re.escape(state_code)}\s+\d{{5}}(?:-\d{{4}})?", re.IGNORECASE)
            m = p.search(text)
            if m:
                city_candidate = str(m.group(1) or '').split(',')[-1].strip()
    if (not city_candidate) and address1:
        addr = re.sub(r'\s+', ' ', str(address1)).strip()
        if addr and addr.lower() in text.lower():
            pos = text.lower().find(addr.lower())
            tail = text[pos + len(addr):].strip(' ,')
            if tail:
                seg = tail.split(',')[0].strip()
                if seg and re.search(r'[A-Za-z]', seg):
                    city_candidate = seg
    if city_candidate:
        city_candidate = re.sub(r'[^A-Za-z\s\.\-]', ' ', city_candidate)
        city_candidate = re.sub(r'\s+', ' ', city_candidate).strip(" .,-'")
    if not city_candidate or len(city_candidate) < 2:
        return ''
    street_words = {
        'st', 'street', 'rd', 'road', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
        'ln', 'lane', 'ct', 'court', 'cir', 'circle', 'pl', 'place', 'pkwy', 'parkway',
        'way', 'trl', 'trail', 'hwy', 'highway', 'ter', 'terrace'
    }
    tokens = [re.sub(r'[^a-zA-Z]', '', t).lower() for t in city_candidate.split() if t]
    if tokens and all(t in street_words for t in tokens):
        return ''
    return city_candidate
