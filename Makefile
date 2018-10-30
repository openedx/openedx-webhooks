.DEFAULT_GOAL := help

include Makefiles/*.mk

# Generates a help message. Borrowed from https://github.com/pydanny/cookiecutter-djangopackage.
help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@perl -nle'print $& if m{^[\.a-zA-Z_-]+:.*?## .*$$}' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}'

check-setup.py: ## Check setup
	python setup.py check -r -s

clean: ## Clean cache, test, and build directories
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build

test: ## Run tests
	py.test -rxs --cov=openedx_webhooks

test-html-coverage-report: ## Run tests and show coverage report in browser
	py.test -rxs --cov=openedx_webhooks --cov-report=html
	open htmlcov/index.html

upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile --upgrade -o requirements/pip-tools.txt requirements/pip-tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/dev.txt requirements/dev.in
