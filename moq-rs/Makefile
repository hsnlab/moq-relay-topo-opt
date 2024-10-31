export CAROOT ?= $(shell cd dev ; go run filippo.io/mkcert -CAROOT)

.PHONY: run
run: dev/localhost.crt
	@docker-compose up --build --remove-orphans

dev/localhost.crt:
	@dev/cert

.PHONY: config
config:
	@./gen_compose.sh

.PHONY: stop
stop:
	@docker rm -v -f $(docker ps -qa)

.PHONY: clean
clean:
	rm dev/localhost.*
	docker rm -v -f $(docker ps -qa)
	docker system prune -f
