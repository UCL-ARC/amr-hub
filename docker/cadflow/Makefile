# -------- settings --------
DOCKER        ?= docker
COMPOSE       ?= docker compose
BUILDER       ?= cadflow-builder

# Images
CONVERT_IMG   ?= cadflow-convert:oda-amd64
PROCESS_IMG   ?= cadflow-processor:latest

# Platforms (local use)
PLAT_CONVERT  ?= linux/amd64
PLAT_PROCESS  ?= linux/amd64

# Host user for file ownership on bind mounts
UID           := $(shell id -u)
GID           := $(shell id -g)

# Paths (relative to repo root)
IN_DIR        ?= $(CURDIR)/in
WORK_DIR      ?= $(CURDIR)/work
OUT_DIR       ?= $(CURDIR)/out

# -------- targets --------
.PHONY: help builder-init builder-use build-converter build-processor build-all \
        up down logs ps clean clean-builders clean-cache dirs up down \
		run-converter run-processor
help:
	@echo "Targets:"
	@echo "  builder-init     Initialise QEMU and a docker-container Buildx builder"
	@echo "  build-converter  Build converter image (DWG->DXF) locally"
	@echo "  build-processor  Build processor image (DXF->GPKG/SHP) locally"
	@echo "  build-all        Build both images"
	@echo "  up               Run full pipeline via docker compose"
	@echo "  down             Stop compose stack"
	@echo "  run-converter    Run converter via docker compose"
	@echo "  run-processor    Run processor via docker compose"
	@echo "  logs             Tail compose logs"
	@echo "  ps               Show compose service status"
	@echo "  clean            Stop stack and remove build artefacts"
	@echo "  clean-builders   Remove non-default Buildx builders and stale BuildKit"
	@echo "  clean-cache      Aggressive: prune all Docker caches/volumes"
	@echo "  dirs             Create local in/work/out directories"

builder-init:
	$(DOCKER) context use default
	unset DOCKER_HOST || true
	$(DOCKER) run --rm --privileged tonistiigi/binfmt --install all
	$(DOCKER) buildx create --driver docker-container --name $(BUILDER) || true
	$(DOCKER) buildx use $(BUILDER)
	$(DOCKER) buildx inspect --bootstrap
	$(DOCKER) buildx ls

builder-use:
	$(DOCKER) context use default
	unset DOCKER_HOST || true
	$(DOCKER) buildx use $(BUILDER)
	$(DOCKER) buildx inspect --bootstrap

build-converter: dirs
	$(DOCKER) buildx build \
	  --platform $(PLAT_CONVERT) \
	  -t $(CONVERT_IMG) \
	  --load \
	  ./converter

build-processor: dirs
	$(DOCKER) buildx build \
	  --platform $(PLAT_PROCESS) \
	  -t $(PROCESS_IMG) \
	  --load \
	  ./processor

build-all: build-converter build-processor

up: dirs
	$(COMPOSE) up --abort-on-container-exit

down:
	$(COMPOSE) down --remove-orphans

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps


# Run only the converter stage
run-converter: dirs
	$(COMPOSE) run --rm \
		-u "$(UID)":"$(GID)" \
		convert

# Run only the processor stage
run-processor: dirs
	$(COMPOSE) run --rm \
		-u "$(UID)":"$(GID)" \
		process

clean:
	-$(COMPOSE) down -v --remove-orphans
	-$(DOCKER) image rm -f $(CONVERT_IMG) $(PROCESS_IMG) >/dev/null 2>&1 || true
	-$(DOCKER) rm -f $$($(DOCKER) ps -aq --filter name=buildx_buildkit) >/dev/null 2>&1 || true

clean-builders:
	@echo "Removing non-default Buildx builders and stale BuildKit…"
	-$(DOCKER) buildx ls | awk 'NR>1 && $$0 !~ /^[[:space:]]/ {print $$1}' | sed 's/\*$$//' | grep -v '^default$$' | while read -r b; do \
	  [ -n "$$b" ] && $(DOCKER) buildx rm -f "$$b" || true ; \
	done
	-$(DOCKER) rm -f $$($(DOCKER) ps -aq --filter name=buildx_buildkit) 2>/dev/null || true
	-$(DOCKER) network prune -f

clean-cache:
	$(DOCKER) system prune -a -f --volumes

dirs:
	mkdir -p "$(IN_DIR)" "$(WORK_DIR)" "$(OUT_DIR)"
