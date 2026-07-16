.PHONY: help requirements upgrade upgrade-package lint pylint test mypy docs clean
.PHONY: deploy-configure deploy-check deploy-stage deploy-stage-branch deploy-prod

.DEFAULT_GOAL := help

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of the following:"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

clean: ## Clean cache, test, and build directories
	-rm -rf .cache build dist *.egg-info .coverage htmlcov docs/_build prof .pytest_cache

testschema:  ## Install the repo-tools-data-schema version matching the current branch
	uv pip install -U "repo-tools-data-schema @ git+https://github.com/openedx/repo-tools-data-schema.git@$$(git rev-parse --abbrev-ref HEAD)"

test:  ## Run tests
	uv run tox -e py312-test

fulltest:  ## Run tests including flaky GitHub emulation
	uv run pytest -rxefs --cov=openedx_webhooks --cov=tests --cov-report= --cov-config=pyproject.toml
	uv run pytest -rxefs --cov=openedx_webhooks --cov=tests --cov-report= --cov-config=pyproject.toml --cov-append -m flaky_github --disable-warnings --percent-404=1 --count=100
	uv run coverage html

test-html-coverage-report: test  ## Run tests and open coverage report in browser
	open htmlcov/index.html

lint:  ## Run linting checks
	uv run tox -e lint

pylint:  ## Run pylint
	-uv run pylint --rcfile=pylintrc src/openedx_webhooks tests

mypy:  ## Run mypy type checks
	uv run tox -e mypy

docs:  ## Build documentation
	uv run tox -e docs

upgrade:  ## Upgrade and regenerate pinned dependencies
	uv run --with edx-lint edx_lint write_uv_constraints pyproject.toml
	uv lock --upgrade

upgrade-package:  ## Update just one package to the latest usable release
	@test -n "$(package)" || { echo "\nUsage: make upgrade-package package=...\n"; exit 1; }
	uv lock --upgrade-package $(package)

requirements:  ## Sync dev dependencies
	uv sync --group dev
	uv tool install tox --with tox-uv

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
