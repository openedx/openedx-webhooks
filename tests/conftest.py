import os
import betamax

if not os.path.exists('tests/cassettes'):
    os.makedirs('tests/cassettes')

record_mode = 'none' if os.environ.get('CI') else 'once'

with betamax.Betamax.configure() as config:
    config.cassette_library_dir = 'tests/cassettes/'
    config.default_cassette_options['record_mode'] = record_mode
