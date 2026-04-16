# Makefile – LUMINARK Active Governance Layer
# Meridian Axiom Alignment Technologies (MAAT)

.PHONY: all install build test lint format clean run status help

PYTHON     := python3
PIP        := pip
IMAGE      := luminark-sandbox:latest
BRIDGE_IMG := luminark-bridge:latest
COMPOSE    := docker-compose

##@ General

help: ## Print this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup

install: ## Install project with dev dependencies
	$(PIP) install -e ".[dev]"

install-hooks: ## Install pre-commit hooks
	pre-commit install
	pre-commit install --hook-type commit-msg

##@ Build

build: ## Build the Docker sandbox image (The Crucible)
	docker build -t $(IMAGE) .

build-bridge: ## Build the FastAPI bridge image
	docker build -f Dockerfile.bridge -t $(BRIDGE_IMG) .

build-all: build build-bridge ## Build all Docker images

##@ Development

run: ## Start all services (sandbox + redis + bridge)
	$(COMPOSE) up --build

run-api: ## Start FastAPI bridge only (requires running redis)
	uvicorn main:app --host 0.0.0.0 --port 8080 --reload

run-local: ## Quick local governance test (no Docker required)
	$(PYTHON) luminark_gate.py govern tests/fixtures/sample_code.py

status: ## Check system component status
	$(PYTHON) luminark_gate.py status

##@ Testing

test: ## Run full clinical trial suite
	$(PYTHON) -m pytest tests/ -v --tb=short

test-fast: ## Run tests without slow Hypothesis examples
	$(PYTHON) -m pytest tests/ -v --tb=short -x --hypothesis-seed=0

test-coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=luminark --cov-report=term-missing --cov-report=html

test-bridge: ## Run live bridge integration tests only
	$(PYTHON) -m pytest tests/test_live_bridge.py -v

##@ Quality

lint: ## Run ruff linter
	ruff check .

format: ## Format code with ruff
	ruff format .

format-check: ## Check formatting without modifying files
	ruff format --check .

typecheck: ## Run mypy type checker
	mypy luminark/ --ignore-missing-imports

check: lint format-check typecheck ## Run all quality checks

pre-commit: ## Run all pre-commit hooks
	pre-commit run --all-files

##@ Governance

govern: ## Govern a file: make govern FILE=path/to/code.py
	$(PYTHON) luminark_gate.py govern $(FILE) --mode local

govern-docker: ## Govern a file in Docker sandbox: make govern-docker FILE=path/to/code.py
	$(PYTHON) luminark_gate.py govern $(FILE) --mode docker

report: ## Quick SAP stage report: make report FILE=path/to/code.py
	$(PYTHON) luminark_gate.py report $(FILE)

##@ Infrastructure

redis-up: ## Start Redis telemetry store
	docker run -d --name luminark_redis -p 6379:6379 redis:7-alpine

redis-down: ## Stop Redis
	docker stop luminark_redis && docker rm luminark_redis

redis-cli: ## Open Redis CLI
	docker exec -it luminark_redis redis-cli

##@ Cleanup

clean: ## Remove Python cache and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.py[cod]" -delete 2>/dev/null || true
	find . -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/ .hypothesis/ .ruff_cache/ .mypy_cache/ htmlcov/ dist/ build/

clean-docker: ## Remove all LUMINARK Docker images
	docker rmi $(IMAGE) $(BRIDGE_IMG) 2>/dev/null || true

clean-all: clean clean-docker ## Clean everything
