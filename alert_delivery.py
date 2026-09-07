"""Local alert outbox. App/server submission is not confirmed recipient delivery.

Private alert-config.json has email {enabled,transport,sender,recipient} and
text {enabled,recipient,service_id}. Missing channels wait for configuration;
explicit enabled:false waives pending/new items permanently for that channel.
Outbox submitting/held records require human review before any retry.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import smtplib
import socket
import subprocess
import tempfile
import uuid
from email.message import EmailMessage
from listing_reference import reference

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
    heading = 'Chris List: alert reliability test' if rows and all(r.get('is_test') is True for r in rows) else f'Chris List: {len(rows)} new matches'
    lines = [heading, DASHBOARD+'#results']
    for row in rows[:limit]:
        lines.append(reference(row)+' '+clean(row.get('title'), 140 if channel == 'email' else 70) + ' — ' + clean(row.get('price'), 30))
        url = str(row.get('url', ''))
        if url.startswith(('http://', 'https://')) and len(url) <= 500:
            lines.append(clean(url, 500))
    if len(rows) > limit: lines.append(f'+ {len(rows)-limit} more on the dashboard')
    lines.append('Include the CL reference or listing link when requesting an offer. Requests still need exact-message review before sending.')
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
        rejected = any(code in error for code in ('-1743','-1719','-1728','-600','-10814','-1708','-2740')) or 'Mail did not accept the message' in error
        if not rejected or result.returncode < 0:
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
        try: smtp.close()
        except Exception: pass


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


def targets(config):
    result = {c: (c, config.get(c, {})) for c in CHANNELS}
    email = config.get('email', {})
    copies = email.get('copy_recipients', [])
    if not isinstance(copies, list) or len(copies) > 10:
        raise ValueError('Email copy recipients must be a list of at most ten addresses')
    seen = {str(email.get('recipient', '')).strip().lower()}
    for address in copies:
        if not isinstance(address, str) or not address.strip() or any(x in address for x in '\r\n,;') or '@' not in address:
            raise ValueError('Invalid email copy recipient')
        address = address.strip()
        if address.lower() in seen: continue
        seen.add(address.lower())
        key = 'email-copy-' + hashlib.sha256(address.lower().encode()).hexdigest()[:16]
        result[key] = ('email', dict(email, recipient=address))
    return result


def health(runtime):
    """Non-sensitive operational status for the private app."""
    runtime = Path(runtime)
    try:
        state = read(runtime/'alert-outbox.json', {'items':{}})
        current = targets(load_config(runtime))
        channels = []
        for key, (kind, settings) in current.items():
            receipts = [item['channels'][key] for item in state['items'].values() if key in item['channels']]
            counts = {name:sum(r['state']==name for r in receipts) for name in ('pending','failed','held','submitting','submitted')}
            last = max((r.get('at','') for r in receipts if r['state']=='submitted'), default=None)
            channels.append({'name': 'Email copy' if key.startswith('email-copy-') else kind.capitalize(),
                'configured':configured(kind, settings), 'enabled':settings.get('enabled') is not False,
                'counts':counts, 'last_submission':last})
        return {'channels':channels, 'needs_attention':any(c['counts']['held'] or c['counts']['failed'] or (c['enabled'] and not c['configured']) for c in channels)}
    except Exception:
        return {'channels':[], 'needs_attention':True, 'error':'Private alert records or configuration need attention'}


def notify(runtime, new, relevant):
    runtime = Path(runtime); runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    # Journal before attempting the lock: another delivery process may be busy,
    # but the scanner must still retain these discoveries before its feed advances.
    if new:
        atomic(runtime/('alert-inbox-'+uuid.uuid4().hex+'.json'), new)
    lockfd = os.open(runtime/'alert.lock', os.O_CREAT|os.O_RDWR, 0o600)
    with os.fdopen(lockfd, 'w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 'Alerts already being processed'
        try: return _notify(runtime, [], relevant)
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
    known_channels = set(CHANNELS) | {c for item in items.values() for c in item['channels']}
    legacy = read(runtime/'pending.json', {})
    inboxes = sorted(runtime.glob('alert-inbox-*.json'))
    incoming = list(new)
    for inbox in inboxes: incoming.extend(read(inbox, []))
    new_ids = set()
    for row in [*legacy.values(), *incoming]:
        key = str(row['id'])
        if key not in items and relevant(row):
            new_ids.add(key)
            items[key] = {'listing':row, 'channels':{c:{'state':'pending'} for c in known_channels}}
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
    destinations = targets(config)
    # Removed copy destinations are explicitly waived, so restoring a copy
    # doesn't unexpectedly replay records discovered while it was absent.
    previous = {key for item in items.values() for key in item['channels']}
    for key in previous - destinations.keys(): destinations[key] = ('email', {'enabled':False})
    for item_id, item in items.items():
        for key in destinations:
            if key not in item['channels']:
                item['channels'][key] = {'state':'pending' if item_id in new_ids else 'waived',
                    'reason':'Destination added after this item was queued'}
    atomic(path, state)
    for inbox in inboxes: inbox.unlink()
    summary = []
    for channel, (kind, settings) in destinations.items():
        label = 'email copy' if channel.startswith('email-copy-') else channel
        waiting = [item for item in items.values() if item['channels'][channel]['state'] in ('pending', 'failed')]
        held = sum(item['channels'][channel]['state'] == 'held' for item in items.values())
        if settings.get('enabled') is False:
            for item in waiting: item['channels'][channel] = {'state':'waived', 'at':stamp(), 'reason':'Channel disabled'}
            atomic(path, state)
            summary.append(label+': disabled' + (f'; {held} held for review' if held else '')); continue
        if not waiting:
            summary.append(label+(': held for review' if held else ': no pending alerts')); continue
        if not configured(kind, settings):
            summary.append(label+': waiting for configuration'); continue
        body = digest([item['listing'] for item in waiting], kind)
        batch = uuid.uuid4().hex
        atomic(runtime/('latest-'+channel+'-alert.json'), {'batch':batch, 'body':body, 'at':stamp()})
        for item in waiting: item['channels'][channel] = {'state':'submitting', 'at':stamp(), 'batch':batch}
        atomic(path, state)
        try:
            submit(kind, settings, body)
        except UncertainSubmission as e:
            outcome = 'held'; detail = str(e)[:1000]
        except Exception as e:
            outcome = 'failed'; detail = str(e)[:1000]
        else:
            outcome = 'submitted'; detail = 'Accepted by app/server; recipient delivery not confirmed'
        for item in waiting:
            item['channels'][channel].update(state=outcome, at=stamp(), detail=detail)
        atomic(path, state)
        summary.append(label+': '+{'submitted':'submitted to app/server', 'failed':'failed; queued for retry', 'held':'held for review'}[outcome])
        if held: summary[-1] += f'; {held} earlier items held for review'
    return '; '.join(summary)
