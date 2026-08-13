.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

check-pyproject.toml: ## Check setup
	uv run python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('pyproject.toml is valid and parsed successfully')"

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
	-pylint --rcfile=pylintrc openedx_webhooks tests

TYPEABLE = openedx_webhooks tests
mypy: ## Run mypy to check type annotations
	-mypy $(TYPEABLE)

upgrade: ## update python dependencies
	uv run --with edx-lint edx_lint write_uv_constraints pyproject.toml
	uv lock --upgrade

upgrade-package: ## Update just one package to the latest usable release
	@test -n "$(package)" || { echo "\nUsage: make upgrade-package package=...\n"; exit 1; }
	uv lock --upgrade-package $(package)

install-dev-requirements: ## Install development requirements
	uv sync --group dev

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
