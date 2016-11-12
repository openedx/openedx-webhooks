.DEFAULT_GOAL := test

PRIVATE_IN = requirements/private.in
PRIVATE_TXT = requirements/private.txt


check-setup.py:
	python setup.py check -r -s


clean:
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build


install-requirements: ## install development environment requirements
	pip install -q pip-tools
	pip-sync requirements/*.txt


pip-compile: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -q pip-tools
	pip-compile --upgrade requirements/base.in
	pip-compile --upgrade requirements/dev.in
	pip-compile --upgrade requirements/doc.in
	pip-compile --upgrade requirements/test.in
ifneq (, $(wildcard $(PRIVATE_IN)))
	pip-compile --upgrade $(PRIVATE_IN)
endif


test:
	py.test --cov=openedx_webhooks


test-html-coverage-report:
	py.test --cov=openedx_webhooks --cov-report=html
	open htmlcov/index.html
