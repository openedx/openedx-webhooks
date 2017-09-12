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
