PIP_COMPILE                     ?= pip-compile

define CHECK_PIP_COMPILE
	@if ! which $(PIP_COMPILE) ; then \
		echo "'$(PIP_COMPILE)' command not found. Do you need to install pip-tools?" ;\
		exit 1 ;\
	fi
endef

all:py37-image f5go-app
	echo ""

py37-image:
	docker build -t py37 -f Dockerfile.py37 .

# requirements.txt:
# 	$(CHECK_PIP_COMPILE)
# 	$(PIP_COMPILE) --output-file src/requirements.txt src/requirements.in

f5go-app:
	docker build -t localhost/f5go .

run:
	docker run -it --rm -p 8080:8080 --entrypoint=./go.py localhost/f5go

run-interactive:
	docker run --rm -p 8080:8080 --entrypoint=./go.py localhost/f5go