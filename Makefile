.DEFAULT_GOAL := help

include Makefiles/*.mk

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

check-setup.py: ## Check setup
	python setup.py check -r -s

clean: ## Clean cache, test, and build directories
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build

test: ## Run tests
	py.test -rxefs --cov=openedx_webhooks --cov-context=test --cov-report=
	coverage html --show-contexts

test-html-coverage-report: test ## Run tests and show coverage report in browser
	open htmlcov/index.html

lint: ## Run pylint
	pylint --rcfile=pylintrc  openedx_webhooks tests

upgrade: export CUSTOM_COMPILE_COMMAND = make upgrade
upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile --upgrade -o requirements/pip-tools.txt requirements/pip-tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/dev.txt requirements/dev.in
