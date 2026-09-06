import unittest
from listing_review import assess, approve, REVISION


def approved_message(row, text):
    return dict(id=row['id'], url=row['url'], title=row['title'], text=text,
                review=dict(confirmed=True, requirements_revision=REVISION, purpose='other', intent='inquiry',
                            approver='Test operator', seller='Test seller', intended_use='Other test use'))


class ReviewTests(unittest.TestCase):
    def review(self, **changes):
        r = dict(purpose='enclosure', dimension_basis='usable_inside', width=64, depth=30,
                 evidence='Seller measured the clear interior', confirmed=True, requirements_revision=REVISION,
                 approver='Operator', seller='Example seller', intended_use='Caricature enclosure', intent='offer')
        r.update(changes)
        return r

    def test_actual_undersized_cases_fail_even_as_overall_dimensions(self):
        for width, depth in [(64, 24), (72, 18)]:
            self.assertEqual(assess(self.review(width=width, depth=depth, dimension_basis='overall'))['status'], 'incompatible')

    def test_large_overall_dimensions_do_not_prove_internal_fit(self):
        self.assertEqual(assess(self.review(width=80, depth=40, dimension_basis='overall'))['status'], 'unknown')

    def test_missing_or_unattributed_dimensions_never_pass(self):
        self.assertEqual(assess(self.review(depth=None))['status'], 'unknown')
        with self.assertRaises(ValueError):
            assess(self.review(evidence=''))
        for width in ['NaN', float('inf'), True, -1]:
            with self.assertRaises(ValueError):
                assess(self.review(width=width))

    def entry(self, **changes):
        row = {'url': 'https://offerup.com/item/detail/example', 'title': 'Example case'}
        return dict(row, review=self.review(**changes)), row

    def test_unknown_fit_allows_only_questions_without_exception(self):
        entry, row = self.entry(depth=None)
        with self.assertRaises(ValueError):
            approve(entry, row)
        entry['review']['intent'] = 'inquiry'
        self.assertEqual(approve(entry, row)['assessment']['status'], 'unknown')

    def test_explicit_exception_is_preserved_without_relabeling_fit(self):
        entry, row = self.entry(depth=18, exception_reason='Approved for a separate small display, not plotter fit')
        result = approve(entry, row)
        self.assertEqual(result['assessment']['status'], 'incompatible')
        self.assertIn('small display', result['exception_reason'])

    def test_stale_listing_or_requirements_invalidates_approval(self):
        for key, value in [('title', 'Different case'), ('url', 'https://offerup.com/item/detail/other')]:
            entry, row = self.entry(); entry[key] = value
            with self.assertRaises(ValueError):
                approve(entry, row)
        entry, row = self.entry(requirements_revision='old')
        with self.assertRaises(ValueError):
            approve(entry, row)

    def test_queue_rejects_legacy_or_tampered_approval(self):
        import message_queue as q
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        row = {'id':'case', 'url':'https://offerup.com/item/detail/case', 'title':'Case', 'platform':'OfferUp'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(q,'PATH',Path(tmp)/'messages.json'):
            job=q.enqueue([approved_message(row,'Approved exact text')],lambda _:row)['messages'][0]
            q.validate_job_review(job)
            self.assertEqual(job['review']['approved_text'],'Approved exact text')
            job['text']='Changed offer'
            with self.assertRaises(ValueError):q.validate_job_review(job)
            with self.assertRaises(ValueError):q.validate_job_review({'text':'Legacy draft'})

    def test_cannot_omit_confirmation_or_approver(self):
        for changes in [{'confirmed': False}, {'approver': ''}, {'seller': ''}]:
            entry, row = self.entry(**changes)
            with self.assertRaises(ValueError):
                approve(entry, row)


if __name__ == '__main__':
    unittest.main()
