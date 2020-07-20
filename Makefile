.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

check-setup.py: ## Check setup
	python setup.py check -r -s

clean: ## Clean cache, test, and build directories
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build prof

test: ## Run tests
	py.test -rxefs --cov=openedx_webhooks --cov=tests --cov-context=test --cov-report=
	coverage html --show-contexts

test-html-coverage-report: test ## Run tests and show coverage report in browser
	open htmlcov/index.html

lint: ## Run pylint
	-pylint --rcfile=pylintrc openedx_webhooks tests bin setup.py
	-mypy openedx_webhooks tests

upgrade: export CUSTOM_COMPILE_COMMAND = make upgrade
upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile --upgrade -o requirements/pip-tools.txt requirements/pip-tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/dev.txt requirements/dev.in


PRIVATE_IN = requirements/private.in
PRIVATE_OUT = requirements/private.txt

pip-compile: ## Compile Python requirements without upgrading
	pip install --no-cache-dir -q pip-tools
	pip-compile requirements/base.in
	pip-compile requirements/dev.in
	pip-compile requirements/doc.in
	pip-compile requirements/test.in
ifneq (, $(wildcard $(PRIVATE_IN)))
	pip-compile $(PRIVATE_IN)
else
endif

pip-compile-upgrade: ## Compile and upgrade Python requirements
	pip install --no-cache-dir -q pip-tools
	pip-compile -U requirements/base.in
	pip-compile -U requirements/dev.in
	pip-compile -U requirements/doc.in
	pip-compile -U requirements/test.in
ifneq (, $(wildcard $(PRIVATE_IN)))
	pip-compile -U $(PRIVATE_IN)
endif

install-dev-requirements: ## Install development requirements
	pip install --no-cache-dir -q pip-tools
ifneq (, $(wildcard $(PRIVATE_OUT)))
	pip-sync $(PRIVATE_OUT)
else
	pip-sync requirements/dev.txt
endif

rq-cmd:
	$(eval remote ?= heroku)
	$(cmd) -u $(shell heroku config:get REDIS_URL -r $(remote))

rq-dashboard: ## Start and open rq-dashboard
	@$(MAKE) rq-dashboard-open &
	@$(MAKE) cmd="rq-dashboard" rq-cmd

rq-dashboard-open:
	$(eval url ?= http://localhost:9181)
	@until $$(curl -o /dev/null --silent --head --fail $(url)); do\
		sleep 1;\
	done
	open $(url)

rq-requeue-failed: ## Requeue failed RQ jobs
	@$(MAKE) cmd="rq requeue -a" rq-cmd

rqinfo: ## See RQ info
	@$(MAKE) cmd=rqinfo rq-cmd
