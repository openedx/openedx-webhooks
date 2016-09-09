.DEFAULT_GOAL := test

PRIVATE_IN = requirements/private.in
PRIVATE_TXT = requirements/private.txt
requirement-files = requirements/base.txt requirements/dev.txt requirements/test.txt

ifneq (, $(wildcard $(PRIVATE_TXT)))
requirement-files += $(PRIVATE_TXT)
endif


check-setup.py:
	python setup.py check -r -s


clean:
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build


install-requirements: ## install development environment requirements
	pip install -q pip-tools
	pip-sync $(requirement-files)


pip-compile: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -q pip-tools
	pip-compile --upgrade requirements/base.in
	pip-compile --upgrade requirements/dev.in
	pip-compile --upgrade requirements/doc.in
	pip-compile --upgrade -o requirements/test.txt requirements/base.in requirements/doc.in requirements/test.in
ifneq (, $(wildcard $(PRIVATE_IN)))
	pip-compile --upgrade $(PRIVATE_IN)
endif


test:
	py.test --cov=openedx_webhooks
