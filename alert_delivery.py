"""Local alert outbox. App/server submission is not confirmed recipient delivery.

Private alert-config.json has email {enabled,transport,sender,recipient} and
text {enabled,recipient,service_id}. Missing channels wait for configuration;
explicit enabled:false waives pending/new items permanently for that channel.
Outbox submitting/held records require human review before any retry.
"""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import smtplib
import socket
import subprocess
import tempfile
import uuid
from email.message import EmailMessage

DASHBOARD = 'https://justinfelleskmp-dev.github.io/chris-list/'
CHANNELS = ('email', 'text')


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path, fallback):
    return json.loads(path.read_text()) if path.exists() else fallback


def atomic(path, value):
    fd, name = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def clean(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def digest(rows, channel):
    rows = sorted(rows, key=lambda r: (r.get('priority') == 'secondary', str(r.get('id'))))
    limit = 10 if channel == 'email' else 2
    lines = [f'Chris List: {len(rows)} new matches', DASHBOARD]
    for row in rows[:limit]:
        lines.append(clean(row.get('title'), 140 if channel == 'email' else 70) + ' — ' + clean(row.get('price'), 30))
        if channel == 'email':
            url = str(row.get('url', ''))
            if url.startswith(('http://', 'https://')) and len(url) <= 500:
                lines.append(clean(url, 500))
    if len(rows) > limit: lines.append(f'+ {len(rows)-limit} more on the dashboard')
    return '\n'.join(lines)


class UncertainSubmission(Exception):
    pass


MAIL_SCRIPT = '''on run argv
 tell application "Mail"
  set outgoing to make new outgoing message with properties {visible:false, sender:item 1 of argv, subject:item 3 of argv, content:(item 4 of argv) & return}
  tell outgoing
   make new to recipient at end of to recipients with properties {address:item 2 of argv}
  end tell
  if not (send outgoing) then error "Mail did not accept the message" number 1001
 end tell
 return "submitted"
end run'''
TEXT_SCRIPT = '''on run argv
 tell application "Messages"
  set targetService to service id (item 1 of argv)
  set targetBuddy to buddy (item 2 of argv) of targetService
  send (item 3 of argv) to targetBuddy
 end tell
 return "submitted"
end run'''


def applescript(script, args):
    try:
        result = subprocess.run(['/usr/bin/osascript', '-e', script, '--', *args],
                                capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired as e:
        raise UncertainSubmission('App response timed out; check delivery before retrying') from e
    if result.returncode:
        error = result.stderr.strip()[:1000]
        if '-1712' in error or result.returncode < 0:
            raise UncertainSubmission(error)
        raise RuntimeError(error)
    if result.stdout.strip() != 'submitted':
        raise UncertainSubmission('App response did not confirm submission')


def configured(channel, config):
    if config.get('enabled') is False: return False
    required = ('recipient', 'service_id') if channel == 'text' else ('recipient', 'sender')
    if not all(isinstance(config.get(k), str) and config[k].strip() for k in required): return False
    if channel == 'email' and config.get('transport', 'mail') == 'smtp':
        return bool(config.get('host'))
    return channel == 'text' or config.get('transport', 'mail') == 'mail'


def submit(channel, config, body):
    if channel == 'text':
        applescript(TEXT_SCRIPT, [config['service_id'], config['recipient'], body]); return
    if config.get('transport', 'mail') == 'mail':
        applescript(MAIL_SCRIPT, [config['sender'], config['recipient'], body.splitlines()[0], body]); return
    message = EmailMessage()
    message['From'] = config['sender']; message['To'] = config['recipient']
    message['Subject'] = body.splitlines()[0]; message.set_content(body)
    smtp = smtplib.SMTP(config['host'], int(config.get('port', 587)), timeout=30)
    try:
        smtp.starttls()
        if config.get('username'): smtp.login(config['username'], config.get('password', ''))
        try:
            refused = smtp.send_message(message)
            if refused: raise RuntimeError('SMTP recipient refused')
        except (smtplib.SMTPServerDisconnected, socket.timeout, OSError) as e:
            raise UncertainSubmission('SMTP disconnected during submission') from e
    finally:
        # QUIT failures after DATA acceptance must not turn success into a retry.
        smtp.close()


def load_config(runtime):
    config = read(runtime/'alert-config.json', {})
    if not isinstance(config, dict): raise ValueError('Invalid alert configuration')
    if 'email' not in config and os.getenv('CHRIS_SMTP_HOST'):
        config['email'] = {'transport':'smtp', 'host':os.getenv('CHRIS_SMTP_HOST'),
            'port':os.getenv('CHRIS_SMTP_PORT', '587'), 'sender':os.getenv('CHRIS_MAIL_FROM'),
            'recipient':os.getenv('CHRIS_MAIL_TO'), 'username':os.getenv('CHRIS_SMTP_USER'),
            'password':os.getenv('CHRIS_SMTP_PASSWORD')}
    for channel in CHANNELS:
        if not isinstance(config.get(channel, {}), dict): raise ValueError('Invalid channel configuration')
    return config


def notify(runtime, new, relevant):
    runtime = Path(runtime); runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    lockfd = os.open(runtime/'alert.lock', os.O_CREAT|os.O_RDWR, 0o600)
    with os.fdopen(lockfd, 'w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 'Alerts already being processed'
        try: return _notify(runtime, new, relevant)
        except Exception as e:
            # The public feed must never expose raw errors or private settings.
            atomic(runtime/'alert-error.json', {'at':stamp(), 'error':str(e)[:1000]})
            return 'Alerts need attention; see private local delivery log'


def _notify(runtime, new, relevant):
    path = runtime/'alert-outbox.json'
    state = read(path, {'version':1, 'items':{}})
    if state.get('version') != 1 or not isinstance(state.get('items'), dict):
        raise ValueError('Unsupported alert outbox')
    items = state['items']
    legacy = read(runtime/'pending.json', {})
    for row in [*legacy.values(), *new]:
        key = str(row['id'])
        if key not in items and relevant(row):
            items[key] = {'listing':row, 'channels':{c:{'state':'pending'} for c in CHANNELS}}
    for item in items.values():
        for receipt in item['channels'].values():
            if receipt['state'] == 'submitting':
                receipt.update(state='held', error='Interrupted submission; check delivery before retrying')
        if not relevant(item['listing']):
            for receipt in item['channels'].values():
                if receipt['state'] in ('pending', 'failed'): receipt.update(state='waived', reason='No longer relevant')
    # Durable migration precedes clearing legacy queue or sending any message.
    atomic(path, state)
    if legacy: atomic(runtime/'pending.json', {})
    config = load_config(runtime)
    summary = []
    for channel in CHANNELS:
        settings = config.get(channel, {})
        waiting = [item for item in items.values() if item['channels'][channel]['state'] in ('pending', 'failed')]
        held = sum(item['channels'][channel]['state'] == 'held' for item in items.values())
        if settings.get('enabled') is False:
            for item in waiting: item['channels'][channel] = {'state':'waived', 'at':stamp(), 'reason':'Channel disabled'}
            atomic(path, state)
            summary.append(channel+': disabled' + (f'; {held} held for review' if held else '')); continue
        if not waiting:
            summary.append(channel+(': held for review' if held else ': no pending alerts')); continue
        if not configured(channel, settings):
            summary.append(channel+': waiting for configuration'); continue
        body = digest([item['listing'] for item in waiting], channel)
        batch = uuid.uuid4().hex
        atomic(runtime/('latest-'+channel+'-alert.json'), {'batch':batch, 'body':body, 'at':stamp()})
        for item in waiting: item['channels'][channel] = {'state':'submitting', 'at':stamp(), 'batch':batch}
        atomic(path, state)
        try:
            submit(channel, settings, body)
        except UncertainSubmission as e:
            outcome = 'held'; detail = str(e)[:1000]
        except Exception as e:
            outcome = 'failed'; detail = str(e)[:1000]
        else:
            outcome = 'submitted'; detail = 'Accepted by app/server; recipient delivery not confirmed'
        for item in waiting:
            item['channels'][channel].update(state=outcome, at=stamp(), detail=detail)
        atomic(path, state)
        summary.append(channel+': '+{'submitted':'submitted to app/server', 'failed':'failed; queued for retry', 'held':'held for review'}[outcome])
        if held: summary[-1] += f'; {held} earlier items held for review'
    return '; '.join(summary)
