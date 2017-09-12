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
