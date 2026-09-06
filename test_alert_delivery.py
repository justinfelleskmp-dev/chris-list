import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import alert_delivery


class AlertDeliveryTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {}, clear=True)
        self._env.start()
        self._tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._env.stop()

    def row(self, ident, priority='primary', title=None):
        return {
            'id': ident,
            'title': title or f'Listing {ident}',
            'price': '$10',
            'url': f'https://example.test/{ident}',
            'priority': priority,
        }

    def config(self, email=True, text=True):
        value = {}
        if email is not None:
            value['email'] = {
                'enabled': email,
                'transport': 'mail',
                'sender': 'sender@example.test',
                'recipient': 'recipient@example.test',
            }
        if text is not None:
            value['text'] = {
                'enabled': text,
                'recipient': '+15550001111',
                'service_id': 'iMessage-service',
            }
        (self.runtime / 'alert-config.json').write_text(json.dumps(value))

    def read_json(self, name):
        return json.loads((self.runtime / name).read_text())

    @staticmethod
    def success(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='submitted', stderr='')

    def test_migrates_legacy_pending_and_keeps_private_files_restricted(self):
        legacy = {'old-a': self.row('old-a'), 'old-b': self.row('old-b')}
        (self.runtime / 'pending.json').write_text(json.dumps(legacy))

        status = alert_delivery.notify(self.runtime, [], lambda item: True)

        state = self.read_json('alert-outbox.json')
        self.assertEqual(set(state['items']), {'old-a', 'old-b'})
        self.assertEqual(state['items']['old-a']['listing']['id'], 'old-a')
        self.assertEqual(state['items']['old-a']['channels']['email']['state'], 'pending')
        self.assertEqual(self.read_json('pending.json'), {})
        self.assertIn('waiting for configuration', status)
        self.assertNotIn('recipient@example.test', status)
        self.assertEqual(stat.S_IMODE((self.runtime / 'alert-outbox.json').stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.runtime / 'alert.lock').stat().st_mode), 0o600)

    def test_channels_retry_independently_and_repeated_ids_are_deduplicated(self):
        self.config()
        item = self.row('same-id')
        responses = [RuntimeError('private mail failure'), self.success()]

        with patch('alert_delivery.subprocess.run', side_effect=responses) as run:
            first = alert_delivery.notify(self.runtime, [item], lambda row: True)

        state = self.read_json('alert-outbox.json')
        channels = state['items']['same-id']['channels']
        self.assertEqual(channels['email']['state'], 'failed')
        self.assertEqual(channels['text']['state'], 'submitted')
        self.assertEqual(run.call_count, 2)
        self.assertIn('failed; queued for retry', first)
        self.assertNotIn('private mail failure', first)
        self.assertNotIn('recipient@example.test', first)

        with patch('alert_delivery.subprocess.run', side_effect=self.success) as retry:
            second = alert_delivery.notify(self.runtime, [item], lambda row: True)

        self.assertEqual(retry.call_count, 1)
        channels = self.read_json('alert-outbox.json')['items']['same-id']['channels']
        self.assertEqual(channels['email']['state'], 'submitted')
        self.assertEqual(channels['text']['state'], 'submitted')
        self.assertIn('submitted to app/server', second)

        with patch('alert_delivery.subprocess.run') as duplicate:
            alert_delivery.notify(self.runtime, [item], lambda row: True)
        self.assertFalse(duplicate.called)

    def test_disabled_channel_is_waived_and_does_not_backlog_when_reenabled(self):
        self.config(email=False, text=False)
        item = self.row('waived')

        with patch('alert_delivery.subprocess.run') as run:
            first = alert_delivery.notify(self.runtime, [item], lambda row: True)
        self.assertFalse(run.called)
        channels = self.read_json('alert-outbox.json')['items']['waived']['channels']
        self.assertEqual(channels['email']['state'], 'waived')
        self.assertEqual(channels['text']['state'], 'waived')
        self.assertIn('disabled', first)

        self.config(email=True, text=True)
        with patch('alert_delivery.subprocess.run') as run:
            second = alert_delivery.notify(self.runtime, [item], lambda row: True)
        self.assertFalse(run.called)
        channels = self.read_json('alert-outbox.json')['items']['waived']['channels']
        self.assertEqual(channels['email']['state'], 'waived')
        self.assertEqual(channels['text']['state'], 'waived')
        self.assertNotIn('recipient@example.test', second)

    def test_missing_channel_config_stays_pending_while_configured_channel_sends(self):
        self.config(email=None, text=True)
        item = self.row('partial-config')

        with patch('alert_delivery.subprocess.run', side_effect=self.success) as run:
            status = alert_delivery.notify(self.runtime, [item], lambda row: True)

        self.assertEqual(run.call_count, 1)
        channels = self.read_json('alert-outbox.json')['items']['partial-config']['channels']
        self.assertEqual(channels['email']['state'], 'pending')
        self.assertEqual(channels['text']['state'], 'submitted')
        self.assertIn('email: waiting for configuration', status)
        self.assertNotIn('+15550001111', status)

    def test_interrupted_submitting_record_is_held_and_never_retried_automatically(self):
        self.config(email=True, text=False)
        item = self.row('interrupted')
        state = {
            'version': 1,
            'items': {
                'interrupted': {
                    'listing': item,
                    'channels': {
                        'email': {'state': 'submitting', 'batch': 'old-intent'},
                        'text': {'state': 'pending'},
                    },
                }
            },
        }
        (self.runtime / 'alert-outbox.json').write_text(json.dumps(state))

        with patch('alert_delivery.subprocess.run') as run:
            status = alert_delivery.notify(self.runtime, [], lambda row: True)
        self.assertFalse(run.called)
        channels = self.read_json('alert-outbox.json')['items']['interrupted']['channels']
        self.assertEqual(channels['email']['state'], 'held')
        self.assertEqual(channels['text']['state'], 'waived')
        self.assertIn('held for review', status)

        with patch('alert_delivery.subprocess.run') as retry:
            alert_delivery.notify(self.runtime, [item], lambda row: True)
        self.assertFalse(retry.called)

    def test_timeout_and_osascript_1712_are_held_without_a_retry(self):
        for response in (
            alert_delivery.subprocess.TimeoutExpired('/usr/bin/osascript', 45),
            SimpleNamespace(returncode=1, stdout='', stderr='execution error -1712'),
        ):
            with self.subTest(response=type(response).__name__):
                self.config(email=True, text=False)
                item = self.row(f'uncertain-{type(response).__name__}')
                patcher = patch('alert_delivery.subprocess.run', side_effect=response) \
                    if isinstance(response, BaseException) else \
                    patch('alert_delivery.subprocess.run', return_value=response)
                with patcher as run:
                    status = alert_delivery.notify(self.runtime, [item], lambda row: True)
                self.assertEqual(run.call_count, 1)
                state = self.read_json('alert-outbox.json')
                channel = state['items'][item['id']]['channels']['email']
                self.assertEqual(channel['state'], 'held')
                self.assertIn('held for review', status)
                self.assertNotIn('-1712', status)
                self.assertNotIn('recipient@example.test', status)
                with patch('alert_delivery.subprocess.run') as retry:
                    alert_delivery.notify(self.runtime, [item], lambda row: True)
                self.assertFalse(retry.called)
                # Isolate the next subtest's state and configuration.
                for path in self.runtime.iterdir():
                    path.unlink()

    def test_mail_send_false_error_is_a_retryable_failure(self):
        self.config(email=True, text=False)
        item = self.row('mail-false')
        # MAIL_SCRIPT converts a false Mail `send` result into this known
        # nonzero osascript result, which is safe to retry.
        response = SimpleNamespace(returncode=1, stdout='', stderr='Mail did not accept the message')

        with patch('alert_delivery.subprocess.run', return_value=response):
            status = alert_delivery.notify(self.runtime, [item], lambda row: True)

        channel = self.read_json('alert-outbox.json')['items']['mail-false']['channels']['email']
        self.assertEqual(channel['state'], 'failed')
        self.assertIn('queued for retry', status)

    def test_digest_is_one_bounded_submission_per_channel_and_uses_argv_data(self):
        self.config()
        rows = [self.row(f'secondary-{i:04d}', 'secondary', f'Secondary {i:04d}') for i in range(20)]
        rows += [self.row(f'primary-{i:04d}', 'primary', f'Primary {i:04d}') for i in range(2168)]

        with patch('alert_delivery.subprocess.run', side_effect=self.success) as run:
            status = alert_delivery.notify(self.runtime, rows, lambda row: True)

        self.assertEqual(run.call_count, 2)
        email_command = run.call_args_list[0].args[0]
        text_command = run.call_args_list[1].args[0]
        self.assertEqual(email_command[0], '/usr/bin/osascript')
        self.assertEqual(text_command[0], '/usr/bin/osascript')
        email_script, email_args = email_command[2], email_command[4:]
        text_script, text_args = text_command[2], text_command[4:]
        email_body = email_args[-1]
        text_body = text_args[-1]
        self.assertIn('2188 new matches', email_body)
        self.assertIn('2188 new matches', text_body)
        self.assertIn('Primary 0000', email_body)
        self.assertIn('Primary 0009', email_body)
        self.assertNotIn('Primary 0010', email_body)
        self.assertIn('Primary 0000', text_body)
        self.assertIn('Primary 0001', text_body)
        self.assertNotIn('Primary 0002', text_body)
        self.assertIn(alert_delivery.DASHBOARD, email_body)
        self.assertIn(alert_delivery.DASHBOARD, text_body)
        # Recipient/title/body are data arguments, never interpolated into code.
        self.assertNotIn('recipient@example.test', email_script)
        self.assertNotIn('Primary 0000', email_script)
        self.assertNotIn('recipient@example.test', text_script)
        self.assertNotIn('Primary 0000', text_script)
        self.assertIn('recipient@example.test', email_args)
        self.assertIn('+15550001111', text_args)
        self.assertNotIn('recipient@example.test', status)
        self.assertNotIn('+15550001111', status)


if __name__ == '__main__':
    unittest.main()
