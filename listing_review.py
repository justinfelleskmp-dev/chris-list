"""Deterministic, listing-specific review. No inference or external calls."""
import math

REVISION = 'enclosure-64x30-v1'


def dimension(value):
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValueError('Dimensions must be positive numbers in inches')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('Dimensions must be positive numbers in inches') from None
    if not math.isfinite(value) or not 0 < value < 10000:
        raise ValueError('Dimensions must be positive numbers in inches')
    return value


def assess(review):
    purpose = review.get('purpose')
    if purpose not in {'enclosure', 'machine', 'other'}:
        raise ValueError('Choose the intended use of this listing')
    if purpose != 'enclosure':
        return {'status': 'not_applicable', 'reason': 'Enclosure dimensions do not apply to the stated use'}
    width, depth = dimension(review.get('width')), dimension(review.get('depth'))
    basis = review.get('dimension_basis')
    if basis not in {'unknown', 'overall', 'usable_inside'}:
        raise ValueError('Identify whether dimensions are overall or usable inside')
    if basis != 'unknown' and ((width is not None and width < 64) or (depth is not None and depth < 30)):
        return {'status': 'incompatible', 'reason': 'Below the required 64-inch usable width or 30-inch usable depth'}
    if basis == 'usable_inside' and width is not None and depth is not None:
        if not str(review.get('evidence', '')).strip():
            raise ValueError('Record the source of the usable internal dimensions')
        return {'status': 'compatible', 'reason': 'Recorded usable interior meets the width/depth minimum; other fit requirements still need review'}
    return {'status': 'unknown', 'reason': 'Both usable internal dimensions need evidence; overall dimensions cannot prove fit'}


def approve(entry, row):
    review = entry.get('review')
    if not isinstance(review, dict) or review.get('confirmed') is not True:
        raise ValueError('Review and explicitly approve this exact listing and message before sending')
    if review.get('requirements_revision') != REVISION:
        raise ValueError('Requirements changed; reopen the listing review before sending')
    if entry.get('url') != row['url'] or entry.get('title') != row['title']:
        raise ValueError('Listing changed; reopen the listing and review its message')
    def required(key, label):
        raw = review.get(key, '')
        value = raw.strip() if isinstance(raw, str) else ''
        if not value or len(value) > 2000:
            raise ValueError(label + ' is required (maximum 2000 characters)')
        return value
    approver = required('approver', 'Approver name')
    seller = required('seller', 'Seller name from the listing')
    intended_use = required('intended_use', 'Intended use')
    intent = review.get('intent')
    if intent not in {'inquiry', 'offer'}:
        raise ValueError('Choose whether this is a question or an offer/pickup request')
    fit = assess(review)
    exception = str(review.get('exception_reason', '')).strip()
    if len(exception) > 2000:
        raise ValueError('Exception reason is too long')
    if (fit['status'] == 'incompatible' or (fit['status'] == 'unknown' and intent == 'offer')) and not exception:
        raise ValueError(fit['reason'] + '. Ask for evidence first, or explicitly record why this exception is approved.')
    # A use-change is explicit and auditable, not an inferred waiver from "offer $40".
    return {'approver': approver, 'seller': seller, 'intended_use': intended_use,
            'purpose': review['purpose'], 'intent': intent, 'requirements_revision': REVISION,
            'width': dimension(review.get('width')), 'depth': dimension(review.get('depth')),
            'dimension_basis': review.get('dimension_basis', 'unknown'),
            'evidence': str(review.get('evidence', '')).strip()[:2000],
            'exception_reason': exception, 'assessment': fit,
            'source': 'Explicit private-app review; approver name is self-reported, not authenticated'}
