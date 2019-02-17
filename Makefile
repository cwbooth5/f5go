PIP_COMPILE                     ?= pip-compile

define CHECK_PIP_COMPILE
	@if ! which $(PIP_COMPILE) ; then \
		echo "'$(PIP_COMPILE)' command not found. Do you need to install pip-tools?" ;\
		exit 1 ;\
	fi
endef

all:py37-image f5go-app

py37-image:
	docker build -t py37 -f Dockerfile.py37 .

redis:
	docker build -t localhost/redis -f Dockerfile.redis .

# requirements.txt:
# 	$(CHECK_PIP_COMPILE)
# 	$(PIP_COMPILE) --output-file src/requirements.txt src/requirements.in

f5go-app:
	docker build -t localhost/f5go .
	# build user-defined network bridge

run:
	# run detached, remove on exit
	docker run -d --rm -p 6379:6379 --network f5go-net --name f5go-redis localhost/redis
	docker run -d --rm -p 8080:8080 --network f5go-net --name f5go --entrypoint=./go.py localhost/f5go

run-dev:
	# Development mode.
	docker run -d --rm -p 6379:6379 --network f5go-net --name f5go-redis localhost/redis
	# attach to this one to see updates to source and log output.
	docker run --rm -p 8080:8080 --network f5go-net -v src:/opt/f5go --name f5go --entrypoint=./go.py localhost/f5go

run-interactive:
	docker run --rm -p 8080:8080 --entrypoint=./go.py localhost/f5go