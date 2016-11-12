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


rq-cmd:
	$(eval remote ?= heroku)
	$(cmd) -u $(shell heroku config:get REDIS_URL -r $(remote))


rq-dashboard:
	@$(MAKE) rq-dashboard-open &
	@$(MAKE) cmd="rq-dashboard" rq-cmd


rq-dashboard-open:
	$(eval url ?= http://localhost:9181)
	@until $$(curl -o /dev/null --silent --head --fail $(url)); do\
		sleep 1;\
	done
	open $(url)


rq-requeue-failed:
	@$(MAKE) cmd="rq requeue -a" rq-cmd


rqinfo:
	@$(MAKE) cmd=rqinfo rq-cmd


test:
	py.test --cov=openedx_webhooks


test-html-coverage-report:
	py.test --cov=openedx_webhooks --cov-report=html
	open htmlcov/index.html
