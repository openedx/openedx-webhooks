#!/usr/bin/env python
"""
Summarize the contents of Betamax cassettes::

    $ ./show_cassettes.py tests/cassettes/*.json

"""

import glob
import json
import sys

for filename in sys.argv[1:]:
    with open(filename) as cassette:
        recorded_data = json.load(cassette)
        print "{}:".format(filename)
        interactions = recorded_data['http_interactions']
        if interactions:
            for interaction in interactions:
                print "    {}".format(interaction['request']['uri'])
                status = interaction['response']['status']['code']
                if status == 200:
                    for k, v in interaction['response']['body'].items():
                        if k in ['string', 'base64_string']:
                            v = "{} bytes".format(len(v))
                        print "        {}: {}".format(k, v)
                else:
                    print "        *** {}".format(status)
        else:
            print "  - None -"
