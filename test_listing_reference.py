import unittest
from unittest.mock import patch

import listing_reference as references


class ListingReferenceTests(unittest.TestCase):
    def setUp(self):
        self.case = {'id': 'case-1', 'url': 'https://example.test/item/case-1', 'title': 'Glass case'}
        self.piano = {'id': 'piano-1', 'url': 'https://example.test/item/piano-1', 'title': 'Player piano'}

    def test_known_code_and_exact_url(self):
        code = references.reference(self.case)
        self.assertEqual(len(code), 15)
        self.assertIs(references.resolve('Offer '+code+' $40', [self.case, self.piano]), self.case)
        self.assertIs(references.resolve('Review '+self.case['url'], [self.case, self.piano]), self.case)

    def test_missing_stale_and_title_only_references_fail(self):
        with self.assertRaises(ValueError):
            references.resolve('Offer $40 for the Glass case', [self.case])
        with self.assertRaises(ValueError):
            references.resolve('Offer '+references.reference(self.case), [self.piano])
        with self.assertRaises(ValueError):
            references.resolve('Offer '+self.case['url'], [dict(self.case, url='https://example.test/item/replaced')])

    def test_two_references_are_ambiguous(self):
        with self.assertRaises(ValueError):
            references.resolve(references.reference(self.case)+' '+references.reference(self.piano), [self.case, self.piano])
        with self.assertRaises(ValueError):
            references.resolve(references.reference(self.case)+' '+self.case['url'], [self.case])

    def test_punctuation_around_url_is_ignored(self):
        text = 'Please review ('+self.case['url']+').'
        self.assertIs(references.resolve(text, [self.case]), self.case)

    def test_identical_duplicates_are_allowed(self):
        self.assertIs(references.resolve(references.reference(self.case), [self.case, dict(self.case)]), self.case)

    def test_conflicting_same_code_records_fail_closed(self):
        class Digest:
            def hexdigest(self):
                return 'ABCDEF123456'+'0'*52
        conflicting = dict(self.piano, id='case-2')
        with patch.object(references.hashlib, 'sha256', return_value=Digest()):
            with self.assertRaises(ValueError):
                references.resolve('Use CL-ABCDEF123456', [self.case, conflicting])

    def test_rows_require_id_url_and_title(self):
        for field in ('id', 'url', 'title'):
            row = dict(self.case)
            row[field] = ''
            with self.subTest(field=field), self.assertRaises(ValueError):
                references.reference(row)


if __name__ == '__main__':
    unittest.main()
