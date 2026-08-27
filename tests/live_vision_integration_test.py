import os
os.environ['ATLAS_VISION_ENABLED'] = 'true'
os.environ['ATLAS_VISION_BASE_URL'] = 'http://10.9.96.13:8765'
os.environ['ATLAS_VISION_TIMEOUT'] = '10'
from atlas_core.network.remote_vision_client import RemoteVisionClient

client = RemoteVisionClient()
print('=== LIVE INTEGRATION TEST ===')
print('Enabled:', client.enabled)
print('Base URL:', client.base_url)
print()

print('[1] GET /health')
h = client.get_health()
print(h)
print()

print('[2] GET /api/v1/vision/status')
s = client.get_status()
print(s)
print()

print('[3] connection_state()')
state = client.connection_state()
print('  =>', state)
print()

print('[4] GET /api/v1/incidents (first incident)')
inc = client.get_incidents()
incidents = inc.get('data', {}).get('incidents', [])
if incidents:
    first = incidents[0]
    print('  incident_id:', first.get('incident_id'))
    print('  incident_type:', first.get('incident_type'))
    print('  severity:', first.get('severity'))
    print('  status:', first.get('status'))
else:
    print(inc)
print()

print('[5] GET /api/v1/security/alerts (first alert)')
alerts_resp = client.get_security_alerts()
alerts = alerts_resp.get('data', {}).get('alerts', [])
if alerts:
    a = alerts[0]
    print('  alert_id:', a.get('alert_id'))
    print('  severity:', a.get('severity'))
    print('  acknowledged:', a.get('acknowledged'))
    print('  message:', a.get('message', '')[:80])
else:
    print(alerts_resp)
print()

print('[6] GET /api/v1/incidents/recent')
recent = client.get_recent_incidents()
recent_list = recent.get('data', {}).get('incidents', [])
print(' ', len(recent_list), 'recent incidents returned')
if recent_list:
    print('  latest:', recent_list[0].get('incident_id'), recent_list[0].get('created_at'))
print()

print('[7] acknowledge_command (should return unsupported - not in Vision API)')
ack = client.acknowledge_command('inc-test-123')
print('  status:', ack.get('status'))
print()

print('[8] Simulate Vision goes offline then recovers')
import urllib.error
import unittest.mock as mock

with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('Connection refused')):
    offline_result = client.get_health()
    print('  Offline result status:', offline_result.get('status'))
    print('  error_type:', offline_result.get('error_type'))
    print('  connection_state:', client.connection_state())
print('  Recovery (real):', client.connection_state())
print()

print('=== INTEGRATION TEST COMPLETE ===')
