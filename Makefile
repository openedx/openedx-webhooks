.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

check-setup.py: ## Check setup
	python setup.py check -r -s

clean: ## Clean cache, test, and build directories
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build prof

testschema: ## Install a schema under test.
	# Get the version of repo-tools-data-schema that corresponds to our branch.
	pip uninstall -y repo-tools-data-schema
	pip install -U git+https://github.com/openedx/repo-tools-data-schema.git@$$(git rev-parse --abbrev-ref HEAD)

TEST_FLAGS = $(TEST_ARGS) -rxefs --cov=openedx_webhooks --cov=tests --cov-report=

test: ## Run tests
	pytest $(TEST_FLAGS) --cov-context=test
	coverage html --show-contexts
	coverage xml

fulltest: ## Run tests with randomness to emulate flaky GitHub
	pytest $(TEST_FLAGS)
	pytest $(TEST_FLAGS) --cov-append -m flaky_github --disable-warnings --percent-404=1 --count=100
	coverage html

test-html-coverage-report: test ## Run tests and show coverage report in browser
	open htmlcov/index.html

pylint: ## Run pylint
	-pylint --rcfile=pylintrc openedx_webhooks tests setup.py

TYPEABLE = openedx_webhooks tests
mypy: ## Run mypy to check type annotations
	-mypy $(TYPEABLE)

PIP_COMPILE = pip-compile --allow-unsafe --resolver=backtracking ${COMPILE_OPTS}
compile-requirements: export CUSTOM_COMPILE_COMMAND=make upgrade
compile-requirements: ## Update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	$(PIP_COMPILE) --rebuild -o requirements/pip.txt requirements/pip.in
	$(PIP_COMPILE) -o requirements/pip-tools.txt requirements/pip-tools.in
	pip install -qr requirements/pip.txt
	pip install -qr requirements/pip-tools.txt
	$(PIP_COMPILE) -o requirements/base.txt requirements/base.in
	$(PIP_COMPILE) -o requirements/test.txt requirements/test.in
	$(PIP_COMPILE) -o requirements/dev.txt requirements/dev.in
	$(PIP_COMPILE) -o requirements/doc.txt requirements/doc.in

upgrade: ## Update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	$(MAKE) compile-requirements COMPILE_OPTS="--upgrade"

upgrade-package: ## Update just one package to the latest usable release
	@test -n "$(package)" || { echo "\nUsage: make upgrade-package package=...\n"; exit 1; }
	$(MAKE) compile-requirements COMPILE_OPTS="--upgrade-package $(package)"

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
	@# This run of mypy is to discover the missing type stubs, then we install them
	-mypy $(TYPEABLE) > /dev/null
	mypy --install-types --non-interactive

DEPLOY_PROD_APP=openedx-webhooks
DEPLOY_STAGING_APP=openedx-webhooks-staging
DEPLOY_STAGING_BRANCH=HEAD
DEPLOY_STAGING_REMOTE=heroku
# Set to true to use git over SSH
DEPLOY_USE_SSH=
ifeq (,$(DEPLOY_USE_SSH))
HEROKU_LOGIN_COMMAND=login
HEROKU_GIT_REMOTE_ARGS=
else
HEROKU_LOGIN_COMMAND=keys:add
HEROKU_GIT_REMOTE_ARGS=--ssh-git
endif

deploy-configure:  ## configure heroku for deployment
	heroku apps >/dev/null 2>&1 || \
		heroku "$(HEROKU_LOGIN_COMMAND)"
	git remote get-url "$(DEPLOY_STAGING_REMOTE)" >/dev/null 2>&1 || \
		heroku git:remote --app "$(DEPLOY_STAGING_APP)" $(HEROKU_GIT_REMOTE_ARGS)
	@echo
	git remote -v

deploy-check: deploy-configure  ## check heroku deployments
	@echo
	heroku releases --app "$(DEPLOY_STAGING_APP)" -n 1 2>/dev/null
	heroku releases --app "$(DEPLOY_PROD_APP)" -n 1 2>/dev/null
	@echo

deploy-stage:  ## deploy master to stage via heroku
	make deploy-stage-branch DEPLOY_STAGING_BRANCH=master

deploy-stage-branch: deploy-check  ## deploy a branch to stage via heroku
	@echo
	git push "$(DEPLOY_STAGING_REMOTE)" "$(DEPLOY_STAGING_BRANCH):master"
	@echo
	heroku releases --app "$(DEPLOY_STAGING_APP)" -n 1 2>/dev/null
	heroku open --app "$(DEPLOY_STAGING_APP)" 2>/dev/null

deploy-prod: deploy-check  ## deploy master to production via heroku
	@echo
	heroku pipelines:promote -r "$(DEPLOY_STAGING_REMOTE)"
	@echo
	heroku releases --app "$(DEPLOY_PROD_APP)" -n 1 2>/dev/null
	@echo
	make deploy-check
	heroku open --app "$(DEPLOY_PROD_APP)" 2>/dev/null

.PHONY: docker
docker:
	docker build -t openedx-webhooks:latest .
	docker run --rm -it openedx-webhooks:latest
