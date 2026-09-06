"""Delivery-state tests without contacting sellers or launching Chrome."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import message_queue
import offerup_sender


class OfferUpSenderTests(unittest.TestCase):
    def run_send(self, click_result, confirmed='true'):
        page = MagicMock()
        page.evaluate.side_effect = ['opened', 'false', 'filled', '1', click_result, confirmed]
        updates = []
        with patch.object(offerup_sender, 'ChromeTab') as chrome, patch.object(offerup_sender.time, 'sleep'):
            chrome.return_value.__enter__.return_value = page
            offerup_sender.send({'id': 'job', 'url': 'https://offerup.com/item/detail/test', 'text': 'Approved text'},
                                lambda *args: updates.append(args))
        return updates

    def test_changed_composer_is_safe_to_review(self):
        updates = self.run_send('not_clicked')
        self.assertEqual(updates[-1][1], 'needs_review')
        self.assertIn('No message sent', updates[-1][2])

    def test_unknown_click_result_is_never_retryable(self):
        self.assertEqual(self.run_send('unexpected')[-1][1], 'delivery_unconfirmed')

    def test_click_without_confirmation_is_held(self):
        self.assertEqual(self.run_send('clicked', 'false')[-1][1], 'delivery_unconfirmed')

    def test_platform_confirmation_records_sent(self):
        self.assertEqual(self.run_send('clicked')[-1][1], 'sent')

    def test_send_exception_is_held_and_resubmission_does_not_requeue(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(message_queue, 'PATH', Path(directory)/'messages.json'):
            lookup = lambda _: {'id': 'a', 'title': 'Display case', 'url': 'https://offerup.com/item/detail/test', 'platform': 'OfferUp'}
            payload = [{'id': 'a', 'text': 'Approved text'}]
            job = message_queue.enqueue(payload, lookup)['messages'][0]
            page = MagicMock()
            page.evaluate.side_effect = ['opened', 'false', 'filled', '1', RuntimeError('connection lost')]
            with patch.object(offerup_sender, 'ChromeTab') as chrome, patch.object(offerup_sender.time, 'sleep'):
                chrome.return_value.__enter__.return_value = page
                offerup_sender.send(job, message_queue.update)
            result = message_queue.enqueue(payload, lookup)['messages']
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['status'], 'delivery_unconfirmed')
