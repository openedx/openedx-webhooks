# The few things we need to do in the openedx-webhooks working tree.

.DEFAULT: test

test:
	py.test --cov=openedx_webhooks

clean:
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build
