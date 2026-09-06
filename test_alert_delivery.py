import json
import fcntl
import os
from pathlib import Path
import stat
import smtplib
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

    def config(self, email=True, text=True, copies=None):
        value = {}
        if email is not None:
            email_config = {
                'enabled': email,
                'transport': 'mail',
                'sender': 'sender@example.test',
                'recipient': 'recipient@example.test',
            }
            if copies is not None:
                email_config['copy_recipients'] = copies
            value['email'] = email_config
        if text is not None:
            value['text'] = {
                'enabled': text,
                'recipient': '+15550001111',
                'service_id': 'iMessage-service',
            }
        (self.runtime / 'alert-config.json').write_text(json.dumps(value))

    def smtp_config(self):
        (self.runtime / 'alert-config.json').write_text(json.dumps({
            'email': {
                'enabled': True,
                'transport': 'smtp',
                'host': 'smtp.example.test',
                'port': 2525,
                'sender': 'sender@example.test',
                'recipient': 'recipient@example.test',
            },
            'text': {'enabled': False, 'recipient': '+15550001111', 'service_id': 'iMessage-service'},
        }))

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

    def test_copy_recipients_have_own_receipts_and_only_failed_copy_retries(self):
        copies = ['copy-one@example.test', 'copy-two@example.test']
        self.config(text=False, copies=copies)
        item = self.row('copy-item')
        calls = []

        def submit(kind, settings, body):
            calls.append((kind, settings['recipient']))
            if settings['recipient'] == copies[0]:
                raise RuntimeError('private copy failure')

        with patch('alert_delivery.submit', side_effect=submit):
            status = alert_delivery.notify(self.runtime, [item], lambda row: True)

        destinations = alert_delivery.targets(self.read_json('alert-config.json'))
        copy_keys = [key for key in destinations if key.startswith('email-copy-')]
        self.assertEqual([recipient for _, recipient in calls], [
            'recipient@example.test', copies[0], copies[1]])
        self.assertEqual(len(copy_keys), 2)
        channels = self.read_json('alert-outbox.json')['items']['copy-item']['channels']
        self.assertEqual(channels['email']['state'], 'submitted')
        self.assertEqual(channels[copy_keys[0]]['state'], 'failed')
        self.assertEqual(channels[copy_keys[1]]['state'], 'submitted')
        self.assertNotIn('private copy failure', status)
        self.assertNotIn(copies[0], status)

        with patch('alert_delivery.submit') as retry:
            alert_delivery.notify(self.runtime, [item], lambda row: True)

        retry.assert_called_once()
        self.assertEqual(retry.call_args.args[0], 'email')
        self.assertEqual(retry.call_args.args[1]['recipient'], copies[0])
        channels = self.read_json('alert-outbox.json')['items']['copy-item']['channels']
        self.assertEqual(channels['email']['state'], 'submitted')
        self.assertEqual(channels[copy_keys[0]]['state'], 'submitted')
        self.assertEqual(channels[copy_keys[1]]['state'], 'submitted')

    def test_adding_copy_recipient_does_not_send_old_submitted_items(self):
        item = self.row('old-item')
        self.config(text=False)
        with patch('alert_delivery.submit') as first:
            alert_delivery.notify(self.runtime, [item], lambda row: True)
        first.assert_called_once()

        copies = ['new-copy@example.test']
        self.config(text=False, copies=copies)
        with patch('alert_delivery.submit') as added:
            alert_delivery.notify(self.runtime, [], lambda row: True)
        self.assertFalse(added.called)
        copy_key = next(key for key in self.read_json('alert-outbox.json')['items']['old-item']['channels']
                        if key.startswith('email-copy-'))
        self.assertEqual(
            self.read_json('alert-outbox.json')['items']['old-item']['channels'][copy_key]['state'],
            'waived')

    def test_removed_copy_is_waived_and_readding_it_does_not_replay_backlog(self):
        copy = 'temporary-copy@example.test'
        item = self.row('copy-removed')
        self.config(text=False, copies=[copy])

        def fail_copy(kind, settings, body):
            if settings['recipient'] == copy:
                raise RuntimeError('copy unavailable')

        with patch('alert_delivery.submit', side_effect=fail_copy):
            alert_delivery.notify(self.runtime, [item], lambda row: True)
        copy_key = next(key for key in self.read_json('alert-outbox.json')['items']['copy-removed']['channels']
                        if key.startswith('email-copy-'))
        self.assertEqual(
            self.read_json('alert-outbox.json')['items']['copy-removed']['channels'][copy_key]['state'],
            'failed')

        self.config(text=False)
        with patch('alert_delivery.submit') as removed:
            alert_delivery.notify(self.runtime, [], lambda row: True)
        self.assertFalse(removed.called)
        self.assertEqual(
            self.read_json('alert-outbox.json')['items']['copy-removed']['channels'][copy_key]['state'],
            'waived')

        self.config(text=False, copies=[copy])
        with patch('alert_delivery.submit') as restored:
            alert_delivery.notify(self.runtime, [], lambda row: True)
        self.assertFalse(restored.called)
        self.assertEqual(
            self.read_json('alert-outbox.json')['items']['copy-removed']['channels'][copy_key]['state'],
            'waived')

    def test_inbox_journal_survives_invalid_outbox_or_config_and_recovers(self):
        for invalid in ('outbox', 'config'):
            with self.subTest(invalid=invalid):
                self.config(text=False)
                item = self.row(f'journal-{invalid}')
                if invalid == 'outbox':
                    (self.runtime / 'alert-outbox.json').write_text(json.dumps({'version': 99, 'items': {}}))
                else:
                    (self.runtime / 'alert-config.json').write_text('{not-json')

                with patch('alert_delivery.submit') as blocked:
                    status = alert_delivery.notify(self.runtime, [item], lambda row: True)
                self.assertFalse(blocked.called)
                self.assertIn('attention', status)
                self.assertTrue(list(self.runtime.glob('alert-inbox-*.json')))

                self.config(text=False)
                if invalid == 'outbox':
                    # Recovery includes replacing the damaged state file; the
                    # journal must then be consumed and delivered exactly once.
                    (self.runtime / 'alert-outbox.json').write_text(
                        json.dumps({'version': 1, 'items': {}}))
                with patch('alert_delivery.submit') as recovered:
                    alert_delivery.notify(self.runtime, [], lambda row: True)
                recovered.assert_called_once()
                state = self.read_json('alert-outbox.json')
                self.assertEqual(state['items'][item['id']]['channels']['email']['state'], 'submitted')
                self.assertFalse(list(self.runtime.glob('alert-inbox-*.json')))

                for path in self.runtime.iterdir():
                    path.unlink()

    def test_process_lock_refuses_delivery_and_leaves_journal_for_later(self):
        self.config(text=False)
        item = self.row('locked')
        lock_path = self.runtime / 'alert.lock'
        with lock_path.open('w') as held_lock:
            fcntl.flock(held_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('alert_delivery.submit') as submit:
                status = alert_delivery.notify(self.runtime, [item], lambda row: True)
            self.assertEqual(status, 'Alerts already being processed')
            self.assertFalse(submit.called)
            self.assertTrue(list(self.runtime.glob('alert-inbox-*.json')))
            fcntl.flock(held_lock, fcntl.LOCK_UN)

        with patch('alert_delivery.submit') as recovered:
            alert_delivery.notify(self.runtime, [], lambda row: True)
        recovered.assert_called_once()
        self.assertEqual(
            self.read_json('alert-outbox.json')['items']['locked']['channels']['email']['state'],
            'submitted')

    def test_smtp_send_disconnect_is_uncertain_and_not_retried(self):
        self.smtp_config()
        item = self.row('smtp-disconnect')
        smtp = SimpleNamespace(
            starttls=lambda: None,
            send_message=lambda message: (_ for _ in ()).throw(
                smtplib.SMTPServerDisconnected('connection lost')),
            close=lambda: None,
        )

        with patch('alert_delivery.smtplib.SMTP', return_value=smtp) as factory:
            status = alert_delivery.notify(self.runtime, [item], lambda row: True)
        factory.assert_called_once_with('smtp.example.test', 2525, timeout=30)
        channel = self.read_json('alert-outbox.json')['items']['smtp-disconnect']['channels']['email']
        self.assertEqual(channel['state'], 'held')
        self.assertIn('held for review', status)

        with patch('alert_delivery.smtplib.SMTP') as retry:
            alert_delivery.notify(self.runtime, [item], lambda row: True)
        self.assertFalse(retry.called)

    def test_smtp_close_failure_after_acceptance_does_not_retry(self):
        self.smtp_config()
        item = self.row('smtp-close')

        def close_failure():
            raise OSError('QUIT failed after DATA')

        smtp = SimpleNamespace(
            starttls=lambda: None,
            send_message=lambda message: {},
            close=close_failure,
        )

        with patch('alert_delivery.smtplib.SMTP', return_value=smtp):
            status = alert_delivery.notify(self.runtime, [item], lambda row: True)

        channel = self.read_json('alert-outbox.json')['items']['smtp-close']['channels']['email']
        self.assertEqual(channel['state'], 'submitted')
        self.assertNotIn('queued for retry', status)

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
